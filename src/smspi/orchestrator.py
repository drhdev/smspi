from __future__ import annotations

import logging
import signal
import threading
import time
from dataclasses import dataclass, field

from smspi.config import Config
from smspi.db import Database
from smspi.health import HealthChecker
from smspi.mmcli import MmcliClient
from smspi.modem_service import ModemService
from smspi.sms_poller import SmsPoller
from smspi.telegram_sender import TelegramSender

logger = logging.getLogger(__name__)


@dataclass
class Orchestrator:
    config: Config
    db: Database
    mmcli: MmcliClient
    _stop: threading.Event = field(default_factory=threading.Event)
    _workers: list[threading.Thread] = field(default_factory=list)
    _last_failed_retry: float = field(default=0.0)

    def __post_init__(self) -> None:
        self.modem_service = ModemService(self.config, self.db, self.mmcli)
        self.sms_poller = SmsPoller(self.config, self.db, self.mmcli, self.modem_service)
        self.telegram = TelegramSender(self.config, self.db)
        self.health = HealthChecker(self.config, self.db, self.mmcli, self.modem_service)

    def request_stop(self) -> None:
        self._stop.set()

    def bootstrap(self) -> None:
        logger.info("Bootstrap: waiting for ModemManager")
        self.mmcli.wait_for_manager(max_wait_seconds=180.0)
        time.sleep(self.config.app.recovery_wait_seconds)

        logger.info("Bootstrap: modem discovery")
        self.modem_service.discover_and_prepare()
        time.sleep(self.config.app.step_delay_seconds)

        logger.info("Bootstrap: initial SMS scan")
        self.sms_poller.poll_all()
        time.sleep(self.config.app.step_delay_seconds)

        retried = self.db.reset_failed_to_pending(
            self.config.telegram.failed_retry_batch_size
        )
        if retried:
            logger.info("Re-queued %s failed Telegram deliveries", retried)
        self._last_failed_retry = time.monotonic()

        logger.info("Bootstrap: drain pending Telegram")
        self.telegram.process_pending()

        self.health.run_check()
        logger.info("Bootstrap complete")

    def run(self) -> None:
        signal.signal(signal.SIGTERM, lambda *_: self.request_stop())
        signal.signal(signal.SIGINT, lambda *_: self.request_stop())

        self.bootstrap()

        self._workers = [
            threading.Thread(
                target=self._loop_sms,
                name="sms-poller",
                daemon=False,
            ),
            threading.Thread(
                target=self._loop_telegram,
                name="telegram",
                daemon=False,
            ),
            threading.Thread(
                target=self._loop_discovery,
                name="modem-discovery",
                daemon=False,
            ),
            threading.Thread(
                target=self._loop_health,
                name="health",
                daemon=False,
            ),
        ]
        for thread in self._workers:
            thread.start()

        logger.info("All worker threads started")
        while not self._stop.wait(2.0):
            pass

        grace = self.config.app.shutdown_grace_seconds
        logger.info("Shutdown requested, draining workers (up to %.0fs)", grace)
        for thread in self._workers:
            thread.join(timeout=grace)
        logger.info("Shutdown complete")

    def _maybe_retry_failed_telegram(self) -> None:
        interval = self.config.telegram.failed_retry_interval_seconds
        if interval <= 0:
            return
        if time.monotonic() - self._last_failed_retry < interval:
            return
        retried = self.db.reset_failed_to_pending(
            self.config.telegram.failed_retry_batch_size
        )
        self._last_failed_retry = time.monotonic()
        if retried:
            logger.info("Re-queued %s failed Telegram deliveries", retried)

    def _loop_sms(self) -> None:
        interval = self.config.modem.poll_interval_seconds
        while not self._stop.wait(interval):
            try:
                count = self.sms_poller.poll_all()
                if count:
                    logger.info("Poller stored %s new SMS", count)
            except Exception:
                logger.exception("SMS poller error")
                time.sleep(self.config.app.recovery_wait_seconds)

    def _loop_telegram(self) -> None:
        interval = max(
            self.config.telegram.send_interval_seconds,
            self.config.app.step_delay_seconds,
        )
        while not self._stop.wait(interval):
            try:
                self._maybe_retry_failed_telegram()
                sent = self.telegram.process_pending()
                if sent:
                    logger.info("Telegram worker sent %s message(s)", sent)
            except Exception:
                logger.exception("Telegram worker error")
                time.sleep(self.config.app.recovery_wait_seconds)

    def _loop_discovery(self) -> None:
        interval = self.config.modem.discovery_interval_seconds
        while not self._stop.wait(interval):
            try:
                modems = self.modem_service.discover_and_prepare()
                logger.debug("Discovery refresh: %s modem(s)", len(modems))
            except Exception:
                logger.exception("Modem discovery error")
                time.sleep(self.config.app.recovery_wait_seconds)

    def _loop_health(self) -> None:
        interval = self.config.health.interval_seconds
        while not self._stop.wait(interval):
            try:
                self.health.run_check()
            except Exception:
                logger.exception("Health check error")
