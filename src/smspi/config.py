from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


def _env(key: str, default: str | None = None) -> str | None:
    value = os.environ.get(key)
    return value if value not in (None, "") else default


@dataclass(frozen=True)
class AppConfig:
    timezone: str
    step_delay_seconds: float
    recovery_wait_seconds: float
    shutdown_grace_seconds: float


@dataclass(frozen=True)
class DatabaseConfig:
    path: Path


@dataclass(frozen=True)
class LoggingConfig:
    level: str
    directory: Path
    max_bytes: int
    backup_count: int


@dataclass(frozen=True)
class ModemConfig:
    poll_interval_seconds: float
    discovery_interval_seconds: float
    mmcli_timeout_seconds: float
    delete_after_store: bool
    operator_filter: str


@dataclass(frozen=True)
class TelegramConfig:
    enabled: bool
    account_name: str
    bot_token: str
    chat_id: str
    send_interval_seconds: float
    request_timeout_seconds: float
    max_retries: int
    retry_base_delay_seconds: float
    failed_retry_interval_seconds: float
    failed_retry_batch_size: int
    max_message_length: int
    parse_mode: str
    show_utc_in_message: bool


@dataclass(frozen=True)
class HealthConfig:
    interval_seconds: float
    modem_stale_seconds: float
    stamp_file: Path | None


@dataclass(frozen=True)
class Config:
    app: AppConfig
    database: DatabaseConfig
    logging: LoggingConfig
    modem: ModemConfig
    telegram: TelegramConfig
    health: HealthConfig
    config_path: Path


def _section(data: dict[str, Any], key: str) -> dict[str, Any]:
    section = data.get(key)
    if not isinstance(section, dict):
        raise ValueError(f"Missing or invalid config section: {key}")
    return section


def load_config(path: Path | None = None) -> Config:
    config_path = path or Path(
        _env("SMSPI_CONFIG", "/app/config/config.yaml") or "config.yaml"
    )
    if not config_path.is_file():
        raise FileNotFoundError(
            f"Config not found: {config_path}. Copy config.example.yaml to config.yaml"
        )

    with config_path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}

    app = _section(raw, "app")
    database = _section(raw, "database")
    logging_cfg = _section(raw, "logging")
    modem = _section(raw, "modem")
    telegram = _section(raw, "telegram")
    health = _section(raw, "health")

    token = _env("SMSPI_TELEGRAM_BOT_TOKEN") or str(telegram.get("bot_token", ""))
    chat_id = _env("SMSPI_TELEGRAM_CHAT_ID") or str(telegram.get("chat_id", ""))
    account_name = _env("SMSPI_TELEGRAM_ACCOUNT_NAME") or str(
        telegram.get("account_name", "primary")
    )

    db_path = Path(_env("SMSPI_DB_PATH") or database["path"])
    log_dir = Path(_env("SMSPI_LOG_DIR") or logging_cfg["directory"])
    stamp_raw = health.get("stamp_file")
    if stamp_raw:
        stamp_file = Path(stamp_raw)
    else:
        stamp_file = db_path.parent / ".health_ok"

    return Config(
        app=AppConfig(
            timezone=str(app.get("timezone", "Europe/Berlin")),
            step_delay_seconds=float(app.get("step_delay_seconds", 0.8)),
            recovery_wait_seconds=float(app.get("recovery_wait_seconds", 5.0)),
            shutdown_grace_seconds=float(app.get("shutdown_grace_seconds", 15.0)),
        ),
        database=DatabaseConfig(path=db_path),
        logging=LoggingConfig(
            level=str(_env("SMSPI_LOG_LEVEL") or logging_cfg.get("level", "INFO")),
            directory=log_dir,
            max_bytes=int(logging_cfg.get("max_bytes", 1_048_576)),
            backup_count=int(logging_cfg.get("backup_count", 3)),
        ),
        modem=ModemConfig(
            poll_interval_seconds=float(modem.get("poll_interval_seconds", 12)),
            discovery_interval_seconds=float(
                modem.get("discovery_interval_seconds", 45)
            ),
            mmcli_timeout_seconds=float(modem.get("mmcli_timeout_seconds", 90)),
            delete_after_store=bool(modem.get("delete_after_store", True)),
            operator_filter=str(modem.get("operator_filter", "")),
        ),
        telegram=TelegramConfig(
            enabled=bool(telegram.get("enabled", True)),
            account_name=account_name,
            bot_token=token,
            chat_id=chat_id,
            send_interval_seconds=float(telegram.get("send_interval_seconds", 2.0)),
            request_timeout_seconds=float(
                telegram.get("request_timeout_seconds", 60)
            ),
            max_retries=int(telegram.get("max_retries", 5)),
            retry_base_delay_seconds=float(
                telegram.get("retry_base_delay_seconds", 3.0)
            ),
            failed_retry_interval_seconds=float(
                telegram.get("failed_retry_interval_seconds", 300.0)
            ),
            failed_retry_batch_size=int(telegram.get("failed_retry_batch_size", 20)),
            max_message_length=int(telegram.get("max_message_length", 4096)),
            parse_mode=str(telegram.get("parse_mode", "HTML")),
            show_utc_in_message=bool(telegram.get("show_utc_in_message", False)),
        ),
        health=HealthConfig(
            interval_seconds=float(health.get("interval_seconds", 300)),
            modem_stale_seconds=float(health.get("modem_stale_seconds", 600)),
            stamp_file=stamp_file,
        ),
        config_path=config_path,
    )
