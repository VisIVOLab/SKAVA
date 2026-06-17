"""SQLite-backed registry of files the publisher has already seen.

Schema:

    files
        path           TEXT PRIMARY KEY  -- absolute filesystem path
        size_bytes     INTEGER
        mtime_ns       INTEGER  -- nanosecond mtime, robust to slow FS clocks
        sha256         TEXT     -- nullable when checksum is skipped
        obs_id         TEXT     -- assigned obs_id once published
        first_seen     TEXT     -- ISO-8601 UTC
        last_published TEXT     -- ISO-8601 UTC; null if never published
        last_status    TEXT     -- 'published' | 'failed' | 'pending'
        last_error     TEXT     -- truncated stderr for failed runs

The DB is single-writer (the publisher process). Concurrent runs on
the same state.db would corrupt rows; the watch mode is expected to
hold a flock to prevent that — for v0 we document it instead of
enforcing it, since each publisher instance runs against its own
node's data.
"""
from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

logger = logging.getLogger("skava.publisher.state")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    path           TEXT PRIMARY KEY,
    size_bytes     INTEGER,
    mtime_ns       INTEGER,
    sha256         TEXT,
    obs_id         TEXT,
    first_seen     TEXT,
    last_published TEXT,
    last_status    TEXT DEFAULT 'pending',
    last_error     TEXT
);
CREATE INDEX IF NOT EXISTS idx_files_obs_id  ON files(obs_id);
CREATE INDEX IF NOT EXISTS idx_files_status  ON files(last_status);
"""


class StateStore:
    """Thin wrapper around the SQLite tracking DB."""

    def __init__(self, db_path: Path):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        # Cleanly survive abrupt crashes — single-writer pattern allows
        # WAL without the usual readers-blocked-during-WAL caveat.
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.executescript(_SCHEMA)

    # ── Read ────────────────────────────────────────────────────────────────

    def get(self, path: str) -> sqlite3.Row | None:
        row = self.conn.execute(
            "SELECT * FROM files WHERE path = ?", (path,)
        ).fetchone()
        return row

    def counts(self) -> dict[str, int]:
        cur = self.conn.execute(
            "SELECT last_status, COUNT(*) AS n FROM files GROUP BY last_status"
        )
        return {row["last_status"] or "unknown": int(row["n"]) for row in cur}

    def iter_pending(self) -> Iterator[sqlite3.Row]:
        return iter(self.conn.execute(
            "SELECT * FROM files WHERE last_status IN ('pending','failed') "
            "ORDER BY path"
        ))

    # ── Write ───────────────────────────────────────────────────────────────

    def upsert_seen(
        self, *, path: str, size_bytes: int, mtime_ns: int,
        sha256: str | None,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """
            INSERT INTO files (path, size_bytes, mtime_ns, sha256,
                                first_seen, last_status)
            VALUES (?, ?, ?, ?, ?, 'pending')
            ON CONFLICT(path) DO UPDATE SET
                size_bytes = excluded.size_bytes,
                mtime_ns   = excluded.mtime_ns,
                sha256     = excluded.sha256
            """,
            (path, size_bytes, mtime_ns, sha256, now),
        )

    def mark_published(self, *, path: str, obs_id: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """
            UPDATE files
               SET obs_id = ?, last_published = ?,
                   last_status = 'published', last_error = NULL
             WHERE path = ?
            """,
            (obs_id, now, path),
        )

    def mark_failed(self, *, path: str, error: str) -> None:
        self.conn.execute(
            """
            UPDATE files
               SET last_status = 'failed',
                   last_error = ?
             WHERE path = ?
            """,
            (error[:500], path),
        )

    def needs_extraction(self, path: str, *, mtime_ns: int) -> bool:
        """True when the file is new or has been modified since last seen."""
        row = self.get(path)
        if row is None:
            return True
        return int(row["mtime_ns"] or 0) != mtime_ns or row["last_status"] != "published"

    def close(self) -> None:
        self.conn.close()


@contextmanager
def open_state(db_path: Path) -> Iterator[StateStore]:
    store = StateStore(db_path)
    try:
        yield store
    finally:
        store.close()
