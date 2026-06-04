from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo


def berlin_parts(dt: datetime, tz_name: str) -> tuple[str, str, str]:
    """Return (iso_utc, date_berlin, time_berlin)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    utc = dt.astimezone(timezone.utc)
    local = dt.astimezone(ZoneInfo(tz_name))
    return (
        utc.isoformat(),
        local.strftime("%Y-%m-%d"),
        local.strftime("%H:%M:%S"),
    )


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
