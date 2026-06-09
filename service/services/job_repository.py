"""
SQLiteJobRepository -- SQLite-backed job persistence.

Uses WAL mode and ``BEGIN IMMEDIATE`` for atomic overlap detection.
Implements :class:`~service.providers.repository.JobRepository`.

Concurrency strategy
--------------------
``BEGIN IMMEDIATE`` acquires SQLite's reserved (write) lock at transaction
start -- not at the first write statement.  Concurrent callers block until
the active transaction commits or rolls back, then see the committed state.
This serializes the overlap-check-then-insert critical section and
guarantees exactly one winner under contention.
"""
from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone

from service import config
from service import constants as C
from service.logger import get_logger

log = get_logger("repository")

_ACTIVE_PLACEHOLDERS = ",".join("?" for _ in C.ACTIVE_STATES)

_SQL_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS jobs (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    asset_id        TEXT NOT NULL,
    operation       TEXT NOT NULL,
    start_time      TEXT NOT NULL,
    end_time        TEXT NOT NULL,
    state           TEXT NOT NULL DEFAULT 'PENDING',
    error_message   TEXT,
    idempotency_key TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    UNIQUE(user_id, idempotency_key)
)
"""

_SQL_FIND_BY_IDEMPOTENCY = (
    "SELECT * FROM jobs WHERE user_id = ? AND idempotency_key = ?"
)

_SQL_COUNT_ACTIVE = (
    f"SELECT COUNT(*) AS c FROM jobs "
    f"WHERE user_id = ? AND state IN ({_ACTIVE_PLACEHOLDERS})"
)

_SQL_CHECK_OVERLAP = (
    f"SELECT 1 FROM jobs "
    f"WHERE asset_id = ? AND state IN ({_ACTIVE_PLACEHOLDERS}) "
    f"AND start_time < ? AND end_time > ?"
)

_SQL_INSERT = (
    "INSERT INTO jobs "
    "(id, user_id, asset_id, operation, start_time, end_time, "
    "state, error_message, idempotency_key, created_at, updated_at) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)

_SQL_FIND_BY_ID = "SELECT * FROM jobs WHERE id = ? AND user_id = ?"
_SQL_FIND_BY_ID_UNSCOPED = "SELECT * FROM jobs WHERE id = ?"
_SQL_LIST_BY_USER = "SELECT * FROM jobs WHERE user_id = ? ORDER BY created_at DESC"
_SQL_UPDATE_STATE = (
    "UPDATE jobs SET state = ?, error_message = ?, updated_at = ? WHERE id = ?"
)


class SQLiteJobRepository:
    """Thread-safe SQLite repository using per-thread connections."""

    def __init__(self) -> None:
        self._local = threading.local()

    def _conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn"):
            conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(f"PRAGMA busy_timeout={C.SQLITE_BUSY_TIMEOUT_MS}")
            self._local.conn = conn
        return self._local.conn

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict:
        return {k: row[k] for k in row.keys()}

    def initialize(self) -> None:
        self._conn().execute(_SQL_CREATE_TABLE)
        self._conn().commit()
        log.info("database initialized")

    def find_by_idempotency_key(self, user_id: str, key: str) -> dict | None:
        row = self._conn().execute(
            _SQL_FIND_BY_IDEMPOTENCY, (user_id, key),
        ).fetchone()
        return self._row_to_dict(row) if row else None

    def count_active_jobs(self, user_id: str) -> int:
        row = self._conn().execute(
            _SQL_COUNT_ACTIVE, (user_id, *C.ACTIVE_STATES),
        ).fetchone()
        return row["c"]

    def insert_if_no_overlap(self, job: dict) -> dict | None:
        conn = self._conn()
        conn.execute("BEGIN IMMEDIATE")
        try:
            overlap = conn.execute(
                _SQL_CHECK_OVERLAP,
                (
                    job[C.FIELD_ASSET_ID],
                    *C.ACTIVE_STATES,
                    job[C.FIELD_END_TIME],
                    job[C.FIELD_START_TIME],
                ),
            ).fetchone()
            if overlap:
                conn.rollback()
                log.info(f"overlap detected for asset={job[C.FIELD_ASSET_ID]}")
                return None
            conn.execute(
                _SQL_INSERT,
                (
                    job["id"], job["user_id"], job[C.FIELD_ASSET_ID],
                    job[C.FIELD_OPERATION], job[C.FIELD_START_TIME],
                    job[C.FIELD_END_TIME], job[C.FIELD_STATE],
                    job[C.FIELD_ERROR_MESSAGE], job["idempotency_key"],
                    job["created_at"], job["updated_at"],
                ),
            )
            conn.commit()
            log.info(f"job created id={job['id']}")
            return job
        except Exception:
            conn.rollback()
            raise

    def find_by_id(self, job_id: str, user_id: str) -> dict | None:
        row = self._conn().execute(
            _SQL_FIND_BY_ID, (job_id, user_id),
        ).fetchone()
        return self._row_to_dict(row) if row else None

    def find_by_id_unscoped(self, job_id: str) -> dict | None:
        row = self._conn().execute(
            _SQL_FIND_BY_ID_UNSCOPED, (job_id,),
        ).fetchone()
        return self._row_to_dict(row) if row else None

    def list_by_user(self, user_id: str) -> list[dict]:
        rows = self._conn().execute(
            _SQL_LIST_BY_USER, (user_id,),
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def update_state(
        self, job_id: str, state: str, error_message: str | None,
    ) -> dict | None:
        now = datetime.now(timezone.utc).strftime(C.TIMESTAMP_FORMAT)
        conn = self._conn()
        conn.execute(_SQL_UPDATE_STATE, (state, error_message, now, job_id))
        conn.commit()
        return self.find_by_id_unscoped(job_id)
