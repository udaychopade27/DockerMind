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

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'viewer',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);

        CREATE TABLE IF NOT EXISTS metrics_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slave_id TEXT NOT NULL,
            container_name TEXT NOT NULL,
            cpu_pct REAL NOT NULL,
            mem_pct REAL NOT NULL,
            mem_used_mb REAL NOT NULL,
            mem_limit_mb REAL NOT NULL,
            ts REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_metrics_container_ts ON metrics_history(container_name, ts DESC);
        CREATE INDEX IF NOT EXISTS idx_metrics_ts ON metrics_history(ts DESC);

        CREATE TABLE IF NOT EXISTS host_metrics_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            node_id TEXT NOT NULL,
            cpu_pct REAL NOT NULL,
            mem_pct REAL NOT NULL,
            mem_used_gb REAL NOT NULL,
            mem_total_gb REAL NOT NULL,
            disk_pct REAL NOT NULL,
            ts REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_host_metrics_node_ts ON host_metrics_history(node_id, ts DESC);
        CREATE INDEX IF NOT EXISTS idx_host_metrics_ts ON host_metrics_history(ts DESC);
        """)

        # Safely migrate runbooks table to add stop_on_failure and retry_count if not present
        try:
            await db.execute("ALTER TABLE runbooks ADD COLUMN stop_on_failure INTEGER DEFAULT 1")
        except Exception:
            pass

        try:
            await db.execute("ALTER TABLE runbooks ADD COLUMN retry_count INTEGER DEFAULT 1")
        except Exception:
            pass

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


async def db_get_setting(key: str, default: Optional[str] = None) -> Optional[str]:
    """Retrieve a key-value setting from SQLite."""
    try:
        async with get_db() as db:
            async with db.execute("SELECT value FROM settings WHERE key=?", (key,)) as cur:
                row = await cur.fetchone()
                return row["value"] if row else default
    except Exception as e:
        print(f"[DB] Error getting setting {key}: {e}")
        return default


async def db_set_setting(key: str, value: str):
    """Persist a key-value setting to SQLite."""
    try:
        async with get_db() as db:
            await db.execute(
                "INSERT OR REPLACE INTO settings(key, value, updated_at) VALUES(?, ?, ?)",
                (key, value, time.time())
            )
            await db.commit()
    except Exception as e:
        print(f"[DB] Error saving setting {key}: {e}")


async def db_get_all_settings() -> dict:
    """Retrieve all settings as a dict from SQLite."""
    try:
        async with get_db() as db:
            async with db.execute("SELECT key, value FROM settings") as cur:
                rows = await cur.fetchall()
                return {r["key"]: r["value"] for r in rows}
    except Exception as e:
        print(f"[DB] Error getting all settings: {e}")
        return {}


async def db_record_container_metrics(slave_id: str, stats_list: list, ts: float = 0):
    """Persist a batch of container telemetry snapshots."""
    if not stats_list:
        return
    ts = ts or time.time()
    rows = []
    for s in stats_list:
        rows.append((
            slave_id,
            s.get("name", ""),
            float(s.get("cpu_pct", 0.0)),
            float(s.get("mem_pct", 0.0)),
            float(s.get("mem_used_mb", 0.0)),
            float(s.get("mem_limit_mb", 0.0)),
            ts
        ))
    try:
        async with get_db() as db:
            await db.executemany(
                """INSERT INTO metrics_history (slave_id, container_name, cpu_pct, mem_pct, mem_used_mb, mem_limit_mb, ts)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                rows
            )
            await db.commit()
    except Exception as e:
        print(f"[DB] Error recording container metrics: {e}")


async def db_record_host_metrics(node_id: str, host_stats: dict, ts: float = 0):
    """Persist a host node telemetry snapshot."""
    if not host_stats:
        return
    ts = ts or time.time()
    try:
        async with get_db() as db:
            await db.execute(
                """INSERT INTO host_metrics_history (node_id, cpu_pct, mem_pct, mem_used_gb, mem_total_gb, disk_pct, ts)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    node_id,
                    float(host_stats.get("cpu_pct", 0.0)),
                    float(host_stats.get("mem_pct", 0.0)),
                    float(host_stats.get("mem_used_gb", 0.0)),
                    float(host_stats.get("mem_total_gb", 0.0)),
                    float(host_stats.get("disk_pct", 0.0)),
                    ts
                )
            )
            await db.commit()
    except Exception as e:
        print(f"[DB] Error recording host metrics: {e}")


async def db_get_container_metrics(container_name: str, limit: int = 30) -> list:
    """Retrieve chronological telemetry points for a specific container."""
    try:
        async with get_db() as db:
            async with db.execute(
                """SELECT cpu_pct, mem_pct, mem_used_mb, mem_limit_mb, ts
                   FROM metrics_history
                   WHERE container_name = ?
                   ORDER BY ts DESC LIMIT ?""",
                (container_name, limit)
            ) as cur:
                rows = await cur.fetchall()
                return [dict(r) for r in reversed(rows)]
    except Exception as e:
        print(f"[DB] Error retrieving container metrics: {e}")
        return []


async def db_get_metrics_summary(points: int = 20) -> dict:
    """Retrieve rolling sparkline metrics and leak detection for all active containers and hosts."""
    summary = {"containers": {}, "hosts": {}}
    try:
        async with get_db() as db:
            cutoff = time.time() - 86400  # last 24h
            async with db.execute("SELECT DISTINCT container_name FROM metrics_history WHERE ts > ?", (cutoff,)) as cur:
                cnames = [r[0] for r in await cur.fetchall()]

            for cname in cnames:
                async with db.execute(
                    """SELECT cpu_pct, mem_pct, mem_used_mb, ts
                       FROM metrics_history
                       WHERE container_name = ?
                       ORDER BY ts DESC LIMIT ?""",
                    (cname, points)
                ) as cur:
                    rows = list(reversed(await cur.fetchall()))
                    if rows:
                        cpu_series = [round(r["cpu_pct"], 1) for r in rows]
                        mem_series = [round(r["mem_used_mb"], 1) for r in rows]
                        mem_pct_series = [round(r["mem_pct"], 1) for r in rows]

                        leak_risk = False
                        mem_trend_mb_hr = 0.0
                        if len(mem_series) >= 4:
                            half = len(mem_series) // 2
                            first_half_avg = sum(mem_series[:half]) / half
                            second_half_avg = sum(mem_series[half:]) / (len(mem_series) - half)
                            time_span_hr = max(0.01, (rows[-1]["ts"] - rows[0]["ts"]) / 3600.0)
                            mem_trend_mb_hr = round((second_half_avg - first_half_avg) / time_span_hr, 1)
                            if mem_trend_mb_hr > 5.0 and second_half_avg > first_half_avg:
                                leak_risk = True

                        summary["containers"][cname] = {
                            "cpu": cpu_series,
                            "mem": mem_series,
                            "mem_pct": mem_pct_series,
                            "leak_risk": leak_risk,
                            "mem_trend_mb_hr": mem_trend_mb_hr,
                        }

            async with db.execute("SELECT DISTINCT node_id FROM host_metrics_history WHERE ts > ?", (cutoff,)) as cur:
                nodes = [r[0] for r in await cur.fetchall()]

            for node in nodes:
                async with db.execute(
                    """SELECT cpu_pct, mem_pct, ts
                       FROM host_metrics_history
                       WHERE node_id = ?
                       ORDER BY ts DESC LIMIT ?""",
                    (node, points)
                ) as cur:
                    rows = list(reversed(await cur.fetchall()))
                    if rows:
                        summary["hosts"][node] = {
                            "cpu": [round(r["cpu_pct"], 1) for r in rows],
                            "mem_pct": [round(r["mem_pct"], 1) for r in rows],
                        }
    except Exception as e:
        print(f"[DB] Error getting metrics summary: {e}")
    return summary


async def db_prune_old_metrics(retention_hours: int = 24):
    """Prune metric snapshots older than retention threshold."""
    try:
        cutoff = time.time() - (retention_hours * 3600)
        async with get_db() as db:
            await db.execute("DELETE FROM metrics_history WHERE ts < ?", (cutoff,))
            await db.execute("DELETE FROM host_metrics_history WHERE ts < ?", (cutoff,))
            await db.commit()
    except Exception as e:
        print(f"[DB] Error pruning metrics: {e}")


# ── User Directory & RBAC Persistence ─────────────────────────────────────────

async def db_get_user(username: str) -> Optional[dict]:
    try:
        async with get_db() as db:
            async with db.execute(
                "SELECT username, password_hash, role, created_at, updated_at FROM users WHERE username = ?",
                (username,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return dict(row)
                return None
    except Exception as e:
        print(f"[DB] Error fetching user '{username}': {e}")
        return None


async def db_list_users() -> list:
    try:
        async with get_db() as db:
            async with db.execute(
                "SELECT username, role, created_at, updated_at FROM users ORDER BY created_at ASC"
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]
    except Exception as e:
        print(f"[DB] Error listing users: {e}")
        return []


async def db_create_user(username: str, password_hash: str, role: str) -> Optional[dict]:
    now = time.time()
    try:
        async with get_db() as db:
            await db.execute(
                "INSERT INTO users (username, password_hash, role, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (username, password_hash, role, now, now)
            )
            await db.commit()
        return {"username": username, "role": role, "created_at": now, "updated_at": now}
    except Exception as e:
        print(f"[DB] Error creating user '{username}': {e}")
        return None


async def db_update_user(username: str, role: Optional[str] = None, password_hash: Optional[str] = None) -> Optional[dict]:
    now = time.time()
    try:
        async with get_db() as db:
            if role is not None and password_hash is not None:
                await db.execute(
                    "UPDATE users SET role = ?, password_hash = ?, updated_at = ? WHERE username = ?",
                    (role, password_hash, now, username)
                )
            elif role is not None:
                await db.execute(
                    "UPDATE users SET role = ?, updated_at = ? WHERE username = ?",
                    (role, now, username)
                )
            elif password_hash is not None:
                await db.execute(
                    "UPDATE users SET password_hash = ?, updated_at = ? WHERE username = ?",
                    (password_hash, now, username)
                )
            else:
                return None
            await db.commit()
        return await db_get_user(username)
    except Exception as e:
        print(f"[DB] Error updating user '{username}': {e}")
        return None


async def db_delete_user(username: str) -> bool:
    try:
        async with get_db() as db:
            cursor = await db.execute("DELETE FROM users WHERE username = ?", (username,))
            await db.commit()
            return cursor.rowcount > 0
    except Exception as e:
        print(f"[DB] Error deleting user '{username}': {e}")
        return False


async def db_seed_initial_users(default_admin_password: str, env_users_str: str, pwd_hasher_fn):
    now = time.time()
    try:
        async with get_db() as db:
            async with db.execute("SELECT COUNT(*) as cnt FROM users") as cursor:
                row = await cursor.fetchone()
                count = row["cnt"] if row else 0

            if count == 0:
                admin_hash = pwd_hasher_fn(default_admin_password)
                await db.execute(
                    "INSERT OR IGNORE INTO users (username, password_hash, role, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                    ("admin", admin_hash, "admin", now, now)
                )
                if env_users_str:
                    for entry in env_users_str.split(","):
                        parts = [p.strip() for p in entry.split(":")]
                        if len(parts) == 3:
                            u, p, r = parts
                            if r not in ("admin", "operator", "viewer"):
                                r = "viewer"
                            h = pwd_hasher_fn(p)
                            await db.execute(
                                "INSERT OR IGNORE INTO users (username, password_hash, role, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                                (u, h, r, now, now)
                            )
                await db.commit()
                print("[DB] Initial users seeded successfully.")
    except Exception as e:
        print(f"[DB] Error seeding initial users: {e}")
