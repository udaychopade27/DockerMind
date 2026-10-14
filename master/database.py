import aiosqlite
import json
import time
import os
from typing import Optional

DB_PATH = os.getenv("DB_PATH", "/app/data/dockermind.db")


class DBContextManager:
    """
    Context manager that automatically opens the aiosqlite connection,
    configures aiosqlite.Row row_factory, and enables WAL mode.
    """
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn = None

    async def __aenter__(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        return self._conn

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._conn:
            await self._conn.close()


def get_db():
    return DBContextManager(DB_PATH)


async def configure_db(db):
    """Kept for backward compatibility."""
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")


async def init_db():
    async with get_db() as db:
        await db.executescript("""
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            slave_id TEXT,
            container TEXT,
            payload TEXT,
            result TEXT,
            created_at REAL NOT NULL,
            started_at REAL,
            finished_at REAL,
            scheduled_at REAL
        );

        CREATE TABLE IF NOT EXISTS runbooks (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            description TEXT,
            trigger TEXT NOT NULL,
            steps TEXT NOT NULL,
            enabled INTEGER DEFAULT 1,
            created_at REAL NOT NULL,
            last_run REAL,
            run_count INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT NOT NULL,
            target TEXT,
            slave_id TEXT,
            container TEXT,
            result TEXT,
            user TEXT DEFAULT 'system',
            ts REAL NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
        CREATE INDEX IF NOT EXISTS idx_jobs_slave ON jobs(slave_id);
        CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log(ts DESC);
        CREATE INDEX IF NOT EXISTS idx_audit_container ON audit_log(container);
        """)
        await db.commit()

    print(f"[DB] Initialized: {DB_PATH}")


async def audit(
    action: str,
    target: Optional[str] = None,
    slave_id: Optional[str] = None,
    container: Optional[str] = None,
    result=None,
    user: str = "system",
):
    async with get_db() as db:
        if isinstance(result, dict):
            result = json.dumps(result)

        await db.execute(
            """
            INSERT INTO audit_log(
                action,
                target,
                slave_id,
                container,
                result,
                user,
                ts
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                action,
                target,
                slave_id,
                container,
                result,
                user,
                time.time(),
            ),
        )
        await db.commit()
