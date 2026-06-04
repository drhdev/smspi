from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from smspi.db import SmsRow
from smspi.telegram_format import (
    build_sms_telegram_message,
    escape_html,
    utf16_len,
    utf16_truncate,
)


def _row(**kwargs) -> SmsRow:
    defaults = {
        "id": 1,
        "modem_stable_id": "352099001761481",
        "mm_sms_path": "/org/freedesktop/ModemManager1/SMS/1",
        "sender_number": "+491701234567",
        "sender_name": "Max",
        "recipient_number": "+491609876543",
        "body": "Hallo <test> & Co",
        "received_at_utc": "2026-06-04T12:00:00+00:00",
        "received_date_berlin": "2026-06-04",
        "received_time_berlin": "14:00:00",
    }
    defaults.update(kwargs)
    return SmsRow(**defaults)


def test_escape_html() -> None:
    assert escape_html("a & b <c>") == "a &amp; b &lt;c&gt;"


def test_utf16_truncate() -> None:
    text = "äöü"  # multi-byte, UTF-16 units == len for BMP
    assert utf16_len(text) == 3
    assert utf16_truncate(text, 2) == "äö"


def test_html_message_contains_labels() -> None:
    msg = build_sms_telegram_message(
        _row(),
        timezone_label="Europe/Berlin",
        parse_mode="HTML",
        show_utc=False,
        max_length=4096,
    )
    assert msg.parse_mode == "HTML"
    assert "<b>📩 New SMS</b>" in msg.text
    assert "&lt;test&gt;" in msg.text
    assert "+491701234567" in msg.text


def test_truncation_respects_limit() -> None:
    long_body = "X" * 5000
    msg = build_sms_telegram_message(
        _row(body=long_body),
        timezone_label="Europe/Berlin",
        parse_mode="HTML",
        show_utc=False,
        max_length=500,
    )
    assert utf16_len(msg.text) <= 500
    assert "truncated" in msg.text
