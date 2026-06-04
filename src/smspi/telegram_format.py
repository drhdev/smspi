from __future__ import annotations

import re
from dataclasses import dataclass

from smspi.db import SmsRow

_TRUNC_SUFFIX_PLAIN = "\n\n… (truncated)"
_TRUNC_SUFFIX_HTML = "\n\n<i>… (truncated)</i>"
_BODY_MARKER = "──────────────"


def utf16_len(text: str) -> int:
    """Telegram counts message length in UTF-16 code units."""
    return len(text.encode("utf-16-le")) // 2


def utf16_truncate(text: str, max_units: int) -> str:
    if max_units <= 0:
        return ""
    if utf16_len(text) <= max_units:
        return text
    low, high = 0, len(text)
    while low < high:
        mid = (low + high + 1) // 2
        if utf16_len(text[:mid]) <= max_units:
            low = mid
        else:
            high = mid - 1
    return text[:low]


def escape_html(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _display(value: str | None, *, empty: str = "—") -> str:
    if value is None:
        return empty
    stripped = value.strip()
    return stripped if stripped else empty


def shorten_modem_id(stable_id: str) -> str:
    cleaned = stable_id.strip()
    if len(cleaned) <= 14:
        return cleaned
    return f"…{cleaned[-8:]}"


def _format_phone(value: str | None) -> str:
    raw = _display(value)
    if raw == "—":
        return raw
    return re.sub(r"\s+", "", raw)


@dataclass(frozen=True)
class TelegramMessage:
    text: str
    parse_mode: str | None


def build_sms_telegram_message(
    row: SmsRow,
    *,
    timezone_label: str,
    parse_mode: str | None,
    show_utc: bool,
    max_length: int,
) -> TelegramMessage:
    mode = (parse_mode or "").strip().upper() or None
    if mode == "HTML":
        prefix, body = _html_parts(row, timezone_label=timezone_label, show_utc=show_utc)
        text = _assemble(prefix, escape_html(body), _TRUNC_SUFFIX_HTML, max_length)
        return TelegramMessage(text=text, parse_mode="HTML")

    prefix, body = _plain_parts(row, timezone_label=timezone_label, show_utc=show_utc)
    text = _assemble(prefix, body, _TRUNC_SUFFIX_PLAIN, max_length)
    return TelegramMessage(text=text, parse_mode=None)


def _assemble(prefix: str, body: str, suffix: str, max_length: int) -> str:
    reserve = utf16_len(suffix)
    limit = max(0, max_length - reserve)
    prefix_units = utf16_len(prefix)
    body_budget = max(0, limit - prefix_units)
    if utf16_len(body) > body_budget:
        body = utf16_truncate(body, body_budget)
    return prefix + body + suffix


def _html_parts(
    row: SmsRow, *, timezone_label: str, show_utc: bool
) -> tuple[str, str]:
    sender = escape_html(_format_phone(row.sender_number))
    name = _display(row.sender_name)
    recipient = escape_html(_format_phone(row.recipient_number))
    modem = escape_html(shorten_modem_id(row.modem_stable_id))
    when = (
        f"{escape_html(row.received_date_berlin)}, "
        f"{escape_html(row.received_time_berlin)}"
    )
    header_lines = [
        "<b>📩 New SMS</b>",
        "",
        "<b>From</b>",
        f"<code>{sender}</code>",
    ]
    if name not in ("—", "-"):
        header_lines.append(f"<i>{escape_html(name)}</i>")
    header_lines.extend(
        [
            "",
            "<b>Received on</b>",
            f"<code>{recipient}</code>",
            "",
            f"<b>Modem</b> <code>{modem}</code>",
            f"<b>Time</b> {when} <i>({escape_html(timezone_label)})</i>",
        ]
    )
    if show_utc:
        header_lines.append(f"<i>UTC {escape_html(row.received_at_utc)}</i>")
    prefix = "\n".join(header_lines) + f"\n\n{_BODY_MARKER}\n"
    return prefix, row.body


def _plain_parts(
    row: SmsRow, *, timezone_label: str, show_utc: bool
) -> tuple[str, str]:
    sender = _format_phone(row.sender_number)
    name = _display(row.sender_name)
    recipient = _format_phone(row.recipient_number)
    modem = shorten_modem_id(row.modem_stable_id)
    header_lines = [
        "📩 New SMS",
        "",
        f"From: {sender}",
    ]
    if name not in ("—", "-"):
        header_lines.append(f"Name: {name}")
    header_lines.extend(
        [
            f"Received on: {recipient}",
            f"Modem: {modem}",
            f"Time: {row.received_date_berlin}, {row.received_time_berlin} ({timezone_label})",
        ]
    )
    if show_utc:
        header_lines.append(f"UTC: {row.received_at_utc}")
    prefix = "\n".join(header_lines) + f"\n\n{_BODY_MARKER}\n"
    return prefix, row.body
