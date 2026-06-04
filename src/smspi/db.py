from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from smspi.timeutil import now_utc_iso

logger = logging.getLogger(__name__)

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;

CREATE TABLE IF NOT EXISTS modem_registry (
    stable_id TEXT PRIMARY KEY,
    imei TEXT,
    iccid TEXT,
    own_number TEXT,
    manufacturer TEXT,
    model TEXT,
    operator_name TEXT,
    usb_id TEXT,
    last_mm_index INTEGER,
    last_mm_path TEXT,
    last_state TEXT,
    last_signal REAL,
    last_seen_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sms_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    modem_stable_id TEXT NOT NULL,
    mm_sms_path TEXT NOT NULL UNIQUE,
    sender_number TEXT,
    sender_name TEXT,
    recipient_number TEXT,
    body TEXT NOT NULL,
    received_at_utc TEXT NOT NULL,
    received_date_berlin TEXT NOT NULL,
    received_time_berlin TEXT NOT NULL,
    raw_mmcli TEXT,
    created_at TEXT NOT NULL,
    telegram_status TEXT NOT NULL DEFAULT 'pending',
    telegram_account_name TEXT,
    telegram_chat_id TEXT,
    telegram_sent_at TEXT,
    telegram_message_id TEXT,
    telegram_error TEXT,
    FOREIGN KEY (modem_stable_id) REFERENCES modem_registry(stable_id)
);

CREATE INDEX IF NOT EXISTS idx_sms_telegram_status
    ON sms_messages(telegram_status);

CREATE TABLE IF NOT EXISTS health_checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    checked_at TEXT NOT NULL,
    component TEXT NOT NULL,
    status TEXT NOT NULL,
    details TEXT
);
"""


@dataclass(frozen=True)
class SmsRow:
    id: int
    modem_stable_id: str
    mm_sms_path: str
    sender_number: str | None
    sender_name: str | None
    recipient_number: str | None
    body: str
    received_at_utc: str
    received_date_berlin: str
    received_time_berlin: str


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self.connection() as conn:
            conn.executescript(SCHEMA)
        logger.info("SQLite ready at %s", self.path)

    def upsert_modem(
        self,
        *,
        stable_id: str,
        imei: str | None,
        iccid: str | None,
        own_number: str | None,
        manufacturer: str | None,
        model: str | None,
        operator_name: str | None,
        usb_id: str | None,
        last_mm_index: int,
        last_mm_path: str,
        last_state: str | None,
        last_signal: float | None,
    ) -> None:
        now = now_utc_iso()
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO modem_registry (
                    stable_id, imei, iccid, own_number, manufacturer, model,
                    operator_name, usb_id, last_mm_index, last_mm_path,
                    last_state, last_signal, last_seen_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(stable_id) DO UPDATE SET
                    imei=excluded.imei,
                    iccid=excluded.iccid,
                    own_number=excluded.own_number,
                    manufacturer=excluded.manufacturer,
                    model=excluded.model,
                    operator_name=excluded.operator_name,
                    usb_id=excluded.usb_id,
                    last_mm_index=excluded.last_mm_index,
                    last_mm_path=excluded.last_mm_path,
                    last_state=excluded.last_state,
                    last_signal=excluded.last_signal,
                    last_seen_at=excluded.last_seen_at,
                    updated_at=excluded.updated_at
                """,
                (
                    stable_id,
                    imei,
                    iccid,
                    own_number,
                    manufacturer,
                    model,
                    operator_name,
                    usb_id,
                    last_mm_index,
                    last_mm_path,
                    last_state,
                    last_signal,
                    now,
                    now,
                ),
            )

    def insert_sms_if_new(
        self,
        *,
        modem_stable_id: str,
        mm_sms_path: str,
        sender_number: str | None,
        sender_name: str | None,
        recipient_number: str | None,
        body: str,
        received_at_utc: str,
        received_date_berlin: str,
        received_time_berlin: str,
        raw_mmcli: str,
    ) -> int | None:
        now = now_utc_iso()
        with self.connection() as conn:
            try:
                cursor = conn.execute(
                    """
                    INSERT INTO sms_messages (
                        modem_stable_id, mm_sms_path, sender_number, sender_name,
                        recipient_number, body, received_at_utc,
                        received_date_berlin, received_time_berlin,
                        raw_mmcli, created_at, telegram_status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
                    """,
                    (
                        modem_stable_id,
                        mm_sms_path,
                        sender_number,
                        sender_name,
                        recipient_number,
                        body,
                        received_at_utc,
                        received_date_berlin,
                        received_time_berlin,
                        raw_mmcli,
                        now,
                    ),
                )
                return int(cursor.lastrowid)
            except sqlite3.IntegrityError as exc:
                message = str(exc).lower()
                if "mm_sms_path" in message or "unique" in message:
                    return None
                raise

    def fetch_pending_telegram(self, limit: int = 1) -> list[SmsRow]:
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT id, modem_stable_id, mm_sms_path, sender_number, sender_name,
                       recipient_number, body, received_at_utc,
                       received_date_berlin, received_time_berlin
                FROM sms_messages
                WHERE telegram_status = 'pending'
                ORDER BY id ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [SmsRow(**dict(row)) for row in rows]

    def mark_telegram_sent(
        self,
        sms_id: int,
        *,
        account_name: str,
        chat_id: str,
        message_id: str | None,
    ) -> None:
        with self.connection() as conn:
            conn.execute(
                """
                UPDATE sms_messages SET
                    telegram_status = 'sent',
                    telegram_account_name = ?,
                    telegram_chat_id = ?,
                    telegram_sent_at = ?,
                    telegram_message_id = ?,
                    telegram_error = NULL
                WHERE id = ?
                """,
                (account_name, chat_id, now_utc_iso(), message_id, sms_id),
            )

    def mark_telegram_failed(self, sms_id: int, error: str) -> None:
        with self.connection() as conn:
            conn.execute(
                """
                UPDATE sms_messages SET
                    telegram_status = 'failed',
                    telegram_error = ?
                WHERE id = ?
                """,
                (error[:2000], sms_id),
            )

    def reset_failed_to_pending(self, max_rows: int = 20) -> int:
        with self.connection() as conn:
            cursor = conn.execute(
                """
                UPDATE sms_messages SET telegram_status = 'pending', telegram_error = NULL
                WHERE id IN (
                    SELECT id FROM sms_messages
                    WHERE telegram_status = 'failed'
                    ORDER BY id ASC
                    LIMIT ?
                )
                """,
                (max_rows,),
            )
            return cursor.rowcount

    def record_health(self, component: str, status: str, details: str | None) -> None:
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO health_checks (checked_at, component, status, details)
                VALUES (?, ?, ?, ?)
                """,
                (now_utc_iso(), component, status, details),
            )

    def count_pending_telegram(self) -> int:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM sms_messages WHERE telegram_status = 'pending'"
            ).fetchone()
        return int(row["c"]) if row else 0

    def list_modems(self) -> list[dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM modem_registry ORDER BY stable_id"
            ).fetchall()
        return [dict(row) for row in rows]

    def latest_modem_seen_at(self) -> str | None:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT MAX(last_seen_at) AS ts FROM modem_registry"
            ).fetchone()
        if row and row["ts"]:
            return str(row["ts"])
        return None
