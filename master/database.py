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

        CREATE TABLE IF NOT EXISTS alerts (
            alert_id TEXT PRIMARY KEY,
            slave_id TEXT NOT NULL,
            container_name TEXT NOT NULL,
            severity TEXT NOT NULL,
            root_cause TEXT NOT NULL,
            fix TEXT,
            auto_heal INTEGER DEFAULT 0,
            heal_action TEXT DEFAULT 'none',
            healed INTEGER DEFAULT 0,
            created_at REAL NOT NULL,
            healed_at REAL
        );

        CREATE INDEX IF NOT EXISTS idx_alerts_healed ON alerts(healed);
        CREATE INDEX IF NOT EXISTS idx_alerts_severity ON alerts(severity);
        CREATE INDEX IF NOT EXISTS idx_alerts_container ON alerts(container_name);
        CREATE INDEX IF NOT EXISTS idx_alerts_created ON alerts(created_at DESC);
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


async def db_save_alert(alert: dict):
    """Persist an alert to SQLite."""
    try:
        async with get_db() as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO alerts(
                    alert_id, slave_id, container_name, severity, root_cause,
                    fix, auto_heal, heal_action, healed, created_at, healed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    alert.get("alert_id"),
                    alert.get("slave_id", "local"),
                    alert.get("container_name", ""),
                    alert.get("severity", "warn"),
                    alert.get("root_cause", ""),
                    alert.get("fix", ""),
                    1 if alert.get("auto_heal") else 0,
                    alert.get("heal_action", "none"),
                    1 if alert.get("healed") else 0,
                    alert.get("created_at", time.time()),
                    alert.get("healed_at"),
                )
            )
            await db.commit()
    except Exception as e:
        print(f"[DB] Error saving alert {alert.get('alert_id')}: {e}")


async def db_mark_alert_healed(alert_id: str, healed_at: float = None):
    """Mark an alert as healed in SQLite."""
    try:
        async with get_db() as db:
            await db.execute(
                """
                UPDATE alerts SET healed=1, healed_at=? WHERE alert_id=?
                """,
                (healed_at or time.time(), alert_id)
            )
            await db.commit()
    except Exception as e:
        print(f"[DB] Error updating alert {alert_id}: {e}")


async def db_load_recent_alerts(limit: int = 500) -> list:
    """Load recent alerts from SQLite on startup."""
    try:
        async with get_db() as db:
            async with db.execute(
                """
                SELECT * FROM alerts ORDER BY created_at DESC LIMIT ?
                """,
                (limit,)
            ) as cur:
                rows = await cur.fetchall()
                results = []
                for r in rows:
                    results.append({
                        "alert_id": r["alert_id"],
                        "slave_id": r["slave_id"],
                        "container_name": r["container_name"],
                        "severity": r["severity"],
                        "root_cause": r["root_cause"],
                        "fix": r["fix"],
                        "auto_heal": bool(r["auto_heal"]),
                        "heal_action": r["heal_action"],
                        "healed": bool(r["healed"]),
                        "created_at": r["created_at"],
                        "healed_at": r["healed_at"],
                    })
                return results
    except Exception as e:
        print(f"[DB] Error loading alerts: {e}")
        return []
