from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from smspi.config import Config
from smspi.db import Database
from smspi.mmcli import MmcliClient, MmcliError, ModemInfo, SmsInfo
from smspi.modem_service import ModemService
from smspi.timeutil import berlin_parts

logger = logging.getLogger(__name__)

RECEIVED_STATES = {"received", "stored", "unknown"}


@dataclass
class SmsPoller:
    config: Config
    db: Database
    mmcli: MmcliClient
    modem_service: ModemService

    def poll_all(self) -> int:
        modems = self.modem_service.refresh_modems()
        stored = 0
        for modem in modems:
            time.sleep(self.config.app.step_delay_seconds)
            try:
                stored += self._poll_modem(modem)
            except MmcliError as exc:
                logger.error("SMS poll failed for %s: %s", modem.stable_id, exc)
        return stored

    def _poll_modem(self, modem: ModemInfo) -> int:
        paths = self.mmcli.list_sms_paths(modem.index)
        count = 0
        for sms_path in paths:
            time.sleep(self.config.app.step_delay_seconds)
            try:
                sms = self.mmcli.get_sms(sms_path)
            except MmcliError as exc:
                logger.warning("Cannot read SMS %s: %s", sms_path, exc)
                continue

            if not self._is_incoming(sms):
                continue

            if self._store_sms(modem, sms):
                count += 1
                if self.config.modem.delete_after_store:
                    time.sleep(self.config.app.step_delay_seconds)
                    try:
                        self.mmcli.delete_sms(modem.index, sms.path)
                        logger.debug("Deleted SMS from modem: %s", sms.path)
                    except MmcliError as exc:
                        logger.warning(
                            "Could not delete SMS %s (dedup still safe): %s",
                            sms.path,
                            exc,
                        )
        return count

    @staticmethod
    def _is_incoming(sms: SmsInfo) -> bool:
        state = (sms.state or "").lower()
        if state in RECEIVED_STATES:
            return bool(sms.body or sms.sender_number)
        if state in {"sending", "sent"}:
            return False
        return bool(sms.body and sms.sender_number)

    def _store_sms(self, modem: ModemInfo, sms: SmsInfo) -> bool:
        body = (sms.body or "").strip()
        if not body and not sms.sender_number:
            return False

        received_dt = sms.timestamp or datetime.now(timezone.utc)
        utc_iso, date_berlin, time_berlin = berlin_parts(
            received_dt, self.config.app.timezone
        )
        recipient = modem.own_number

        row_id = self.db.insert_sms_if_new(
            modem_stable_id=modem.stable_id,
            mm_sms_path=sms.path,
            sender_number=sms.sender_number,
            sender_name=sms.sender_name,
            recipient_number=recipient,
            body=body or "(empty)",
            received_at_utc=utc_iso,
            received_date_berlin=date_berlin,
            received_time_berlin=time_berlin,
            raw_mmcli=sms.raw,
        )
        if row_id is None:
            return False

        logger.info(
            "Stored SMS id=%s modem=%s from=%s at %s %s",
            row_id,
            modem.stable_id,
            sms.sender_number,
            date_berlin,
            time_berlin,
        )
        return True
