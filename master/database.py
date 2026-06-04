import aiosqlite
import json
import time
import os
from typing import Optional

DB_PATH = os.getenv("DB_PATH", "/app/data/dockermind.db")


async def get_db() -> aiosqlite.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")  # safe concurrent writes
    return db


async def init_db():
    """Create all tables on startup."""
    async with await get_db() as db:
        await db.executescript("""
        CREATE TABLE IF NOT EXISTS jobs (
            id          TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            type        TEXT NOT NULL,
            status      TEXT NOT NULL DEFAULT 'pending',
            slave_id    TEXT,
            container   TEXT,
            payload     TEXT,
            result      TEXT,
            created_at  REAL NOT NULL,
            started_at  REAL,
            finished_at REAL,
            scheduled_at REAL
        );

        CREATE TABLE IF NOT EXISTS runbooks (
            id          TEXT PRIMARY KEY,
            name        TEXT NOT NULL UNIQUE,
            description TEXT,
            trigger     TEXT NOT NULL,
            steps       TEXT NOT NULL,
            enabled     INTEGER NOT NULL DEFAULT 1,
            created_at  REAL NOT NULL,
            last_run    REAL,
            run_count   INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS audit_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            action      TEXT NOT NULL,
            target      TEXT,
            slave_id    TEXT,
            container   TEXT,
            result      TEXT,
            user        TEXT DEFAULT 'system',
            ts          REAL NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_jobs_status    ON jobs(status);
        CREATE INDEX IF NOT EXISTS idx_jobs_slave     ON jobs(slave_id);
        CREATE INDEX IF NOT EXISTS idx_audit_ts       ON audit_log(ts DESC);
        CREATE INDEX IF NOT EXISTS idx_audit_container ON audit_log(container);
        """)
        await db.commit()
    print(f"[DB] Initialized at {DB_PATH}")


async def audit(action: str, target: str = None, slave_id: str = None,
                container: str = None, result: str = None, user: str = "system"):
    """Write an audit log entry."""
    async with await get_db() as db:
        await db.execute(
            "INSERT INTO audit_log(action,target,slave_id,container,result,user,ts) VALUES(?,?,?,?,?,?,?)",
            (action, target, slave_id, container,
             json.dumps(result) if isinstance(result, dict) else result,
             user, time.time())
        )
        await db.commit()