from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from smspi.config import Config
from smspi.db import Database
from smspi.mmcli import MmcliClient, MmcliError, ModemInfo

logger = logging.getLogger(__name__)


@dataclass
class ModemService:
    config: Config
    db: Database
    mmcli: MmcliClient

    def discover_and_prepare(self) -> list[ModemInfo]:
        """Find modems, enable them, persist stable identity (IMEI-based)."""
        return self._scan_modems(enable=True)

    def refresh_modems(self) -> list[ModemInfo]:
        """Refresh modem list and DB registry without re-enabling (for SMS poll)."""
        return self._scan_modems(enable=False)

    def _scan_modems(self, *, enable: bool) -> list[ModemInfo]:
        operator_filter = self.config.modem.operator_filter.strip().lower()
        modems: list[ModemInfo] = []

        try:
            paths = self.mmcli.list_modem_paths()
        except MmcliError as exc:
            logger.error("Modem scan failed: %s", exc)
            return modems

        if not paths:
            logger.warning("No modems reported by ModemManager")
            return modems

        for path in paths:
            time.sleep(self.config.app.step_delay_seconds)
            try:
                info = self.mmcli.get_modem(path)
            except MmcliError as exc:
                logger.error("Cannot read modem %s: %s", path, exc)
                continue

            if operator_filter and (info.operator_name or "").lower().find(
                operator_filter
            ) < 0:
                logger.info(
                    "Skipping modem %s (operator %s does not match filter)",
                    info.stable_id,
                    info.operator_name,
                )
                continue

            if enable:
                try:
                    self.mmcli.enable_modem(info.index)
                    time.sleep(self.config.app.step_delay_seconds)
                    info = self.mmcli.get_modem(path)
                except MmcliError as exc:
                    logger.warning("Enable modem %s: %s", info.stable_id, exc)

            self.db.upsert_modem(
                stable_id=info.stable_id,
                imei=info.imei,
                iccid=info.iccid,
                own_number=info.own_number,
                manufacturer=info.manufacturer,
                model=info.model,
                operator_name=info.operator_name,
                usb_id=info.usb_id,
                last_mm_index=info.index,
                last_mm_path=info.path,
                last_state=info.state,
                last_signal=info.signal,
            )
            modems.append(info)
            if enable:
                logger.info(
                    "Modem ready: id=%s index=%s state=%s signal=%s number=%s",
                    info.stable_id,
                    info.index,
                    info.state,
                    info.signal,
                    info.own_number,
                )
            else:
                logger.debug(
                    "Modem refreshed: id=%s index=%s state=%s",
                    info.stable_id,
                    info.index,
                    info.state,
                )

        return modems
