from __future__ import annotations

import logging
import sys
from pathlib import Path

from smspi.config import load_config
from smspi.db import Database
from smspi.logging_setup import setup_logging
from smspi.mmcli import MmcliClient
from smspi.orchestrator import Orchestrator

logger = logging.getLogger(__name__)


def main() -> int:
    config_path = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    try:
        config = load_config(config_path)
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 1

    setup_logging(config.logging)
    logger.info("Starting smspi %s", __import__("smspi").__version__)

    db = Database(config.database.path)
    mmcli = MmcliClient(config.modem.mmcli_timeout_seconds)
    orchestrator = Orchestrator(config=config, db=db, mmcli=mmcli)

    if config.telegram.enabled and not orchestrator.telegram.validate_config():
        logger.error("Telegram configuration invalid; fix token/chat_id or disable telegram")
        return 1

    try:
        orchestrator.run()
    except KeyboardInterrupt:
        orchestrator.request_stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
