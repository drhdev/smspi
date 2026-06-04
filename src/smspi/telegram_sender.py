from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import requests

from smspi.config import Config
from smspi.db import Database, SmsRow
from smspi.telegram_format import TelegramMessage, build_sms_telegram_message

logger = logging.getLogger(__name__)

# Do not retry permanent configuration / permission errors (Telegram Bot API).
_NON_RETRYABLE_CODES = frozenset({400, 401, 403, 404})


@dataclass
class TelegramSender:
    config: Config
    db: Database
    _session: requests.Session = field(default_factory=requests.Session)

    def validate_config(self) -> bool:
        """Optional startup check: token valid and bot can reach Telegram."""
        cfg = self.config.telegram
        if not cfg.enabled:
            return True
        if not cfg.bot_token:
            logger.error("Telegram enabled but bot_token missing")
            return False
        if not cfg.chat_id:
            logger.error("Telegram enabled but chat_id missing")
            return False
        try:
            response = self._session.get(
                f"https://api.telegram.org/bot{cfg.bot_token}/getMe",
                timeout=min(cfg.request_timeout_seconds, 30.0),
            )
            data = response.json()
            if response.ok and data.get("ok"):
                username = (data.get("result") or {}).get("username", "?")
                logger.info("Telegram bot OK: @%s", username)
                return True
            logger.error(
                "Telegram getMe failed: %s",
                data.get("description", response.text),
            )
        except requests.RequestException as exc:
            logger.error("Telegram getMe request failed: %s", exc)
        return False

    def process_pending(self) -> int:
        if not self.config.telegram.enabled:
            return 0

        if not self.config.telegram.bot_token or not self.config.telegram.chat_id:
            logger.error("Telegram enabled but bot_token or chat_id missing")
            return 0

        sent = 0
        pending = self.db.fetch_pending_telegram(limit=5)
        for row in pending:
            time.sleep(self.config.app.step_delay_seconds)
            if self._send_one(row):
                sent += 1
            time.sleep(self.config.telegram.send_interval_seconds)
        return sent

    def _send_one(self, row: SmsRow) -> bool:
        message = build_sms_telegram_message(
            row,
            timezone_label=self.config.app.timezone,
            parse_mode=self.config.telegram.parse_mode,
            show_utc=self.config.telegram.show_utc_in_message,
            max_length=self.config.telegram.max_message_length,
        )
        message_id, error = self._api_send(message)
        if (
            message_id is None
            and message.parse_mode == "HTML"
            and error
            and "parse" in error.lower()
        ):
            logger.warning("Telegram HTML parse failed, retrying as plain text")
            plain = build_sms_telegram_message(
                row,
                timezone_label=self.config.app.timezone,
                parse_mode=None,
                show_utc=self.config.telegram.show_utc_in_message,
                max_length=self.config.telegram.max_message_length,
            )
            message_id, error = self._api_send(plain)

        if message_id is None:
            self.db.mark_telegram_failed(row.id, error or "telegram send failed")
            return False

        self.db.mark_telegram_sent(
            row.id,
            account_name=self.config.telegram.account_name,
            chat_id=self.config.telegram.chat_id,
            message_id=message_id,
        )
        logger.info(
            "Telegram sent sms_id=%s account=%s chat=%s message_id=%s",
            row.id,
            self.config.telegram.account_name,
            self.config.telegram.chat_id,
            message_id,
        )
        return True

    def _api_send(self, message: TelegramMessage) -> tuple[str | None, str | None]:
        cfg = self.config.telegram
        url = f"https://api.telegram.org/bot{cfg.bot_token}/sendMessage"
        payload: dict[str, str | bool] = {
            "chat_id": cfg.chat_id,
            "text": message.text,
            "disable_web_page_preview": True,
        }
        if message.parse_mode:
            payload["parse_mode"] = message.parse_mode

        last_error: str | None = None
        attempt = 0

        while attempt < cfg.max_retries:
            try:
                response = self._session.post(
                    url,
                    json=payload,
                    timeout=cfg.request_timeout_seconds,
                )
                try:
                    data = response.json()
                except ValueError:
                    data = {}

                if response.ok and data.get("ok"):
                    result = data.get("result") or {}
                    return str(result.get("message_id", "")), None

                error_code = int(data.get("error_code", response.status_code or 0))
                last_error = str(data.get("description", response.text))

                if error_code in _NON_RETRYABLE_CODES:
                    logger.error("Telegram permanent error %s: %s", error_code, last_error)
                    return None, last_error

                if error_code == 429:
                    params = data.get("parameters") or {}
                    wait = float(params.get("retry_after", cfg.retry_base_delay_seconds))
                    logger.warning(
                        "Telegram rate limit, waiting %.0fs before retry", wait
                    )
                    time.sleep(wait)
                    continue

                logger.warning(
                    "Telegram API attempt %s failed (%s): %s",
                    attempt + 1,
                    error_code,
                    last_error,
                )
            except requests.RequestException as exc:
                last_error = str(exc)
                logger.warning(
                    "Telegram request attempt %s failed: %s", attempt + 1, exc
                )

            attempt += 1
            time.sleep(cfg.retry_base_delay_seconds * attempt)

        return None, last_error
