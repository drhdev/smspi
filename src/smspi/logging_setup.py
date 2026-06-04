from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from smspi.config import LoggingConfig


def setup_logging(cfg: LoggingConfig) -> None:
    cfg.directory.mkdir(parents=True, exist_ok=True)
    log_file = cfg.directory / "smspi.log"

    root = logging.getLogger()
    root.setLevel(getattr(logging, cfg.level.upper(), logging.INFO))

    for handler in list(root.handlers):
        root.removeHandler(handler)

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=cfg.max_bytes,
        backupCount=cfg.backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root.addHandler(console)

    logging.getLogger("urllib3").setLevel(logging.WARNING)
