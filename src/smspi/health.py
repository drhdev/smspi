from __future__ import annotations

import json
import logging
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone

from smspi.config import Config
from smspi.db import Database
from smspi.mmcli import MmcliClient, MmcliError
from smspi.modem_service import ModemService
from smspi.timeutil import now_utc_iso

logger = logging.getLogger(__name__)


@dataclass
class HealthChecker:
    config: Config
    db: Database
    mmcli: MmcliClient
    modem_service: ModemService

    def run_check(self) -> bool:
        results: dict[str, str] = {}
        ok = True

        if not shutil.which("mmcli"):
            results["mmcli"] = "missing"
            ok = False
        else:
            results["mmcli"] = "ok"

        try:
            self.mmcli.run("-L", retries=0)
            results["modem_manager"] = "ok"
        except MmcliError as exc:
            results["modem_manager"] = f"error: {exc}"
            ok = False

        modems = self.modem_service.refresh_modems()
        results["modem_count"] = str(len(modems))
        if not modems:
            ok = False

        pending = self.db.count_pending_telegram()
        results["telegram_pending"] = str(pending)

        stale_limit = self.config.health.modem_stale_seconds
        if stale_limit > 0:
            last_seen = self.db.latest_modem_seen_at()
            if not last_seen:
                results["modem_stale"] = "no data"
                ok = False
            else:
                try:
                    seen = datetime.fromisoformat(last_seen)
                    age = (
                        datetime.now(timezone.utc) - seen.astimezone(timezone.utc)
                    ).total_seconds()
                    results["modem_last_seen_age_s"] = str(int(age))
                    if age > stale_limit:
                        results["modem_stale"] = "yes"
                        ok = False
                    else:
                        results["modem_stale"] = "no"
                except ValueError:
                    results["modem_stale"] = "parse error"
                    ok = False

        status = "ok" if ok else "degraded"
        details = json.dumps(results, ensure_ascii=False)
        self.db.record_health("self_check", status, details)
        self._write_stamp(ok)

        if ok:
            logger.info("Health check OK: %s", details)
        else:
            logger.warning("Health check DEGRADED: %s", details)

        return ok

    def _write_stamp(self, ok: bool) -> None:
        stamp = self.config.health.stamp_file
        if stamp is None:
            return
        try:
            stamp.parent.mkdir(parents=True, exist_ok=True)
            if ok:
                stamp.write_text(now_utc_iso(), encoding="utf-8")
            elif stamp.exists():
                stamp.unlink()
        except OSError as exc:
            logger.warning("Could not update health stamp %s: %s", stamp, exc)
