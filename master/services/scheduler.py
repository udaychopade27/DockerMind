import asyncio
import json
import time
import uuid
from typing import Optional
import aiosqlite
from database import get_db, audit


class Scheduler:
    """
    Simple async scheduler — runs pending jobs at their scheduled_at time.
    Backed by SQLite so jobs survive restarts.
    """

    def __init__(self):
        self._running = False
        self._tick_secs = 10  # check for due jobs every 10s

    async def schedule(self,
                       name: str,
                       job_type: str,
                       slave_id: str,
                       container: str,
                       payload: dict,
                       run_at: Optional[float] = None) -> str:
        """
        Create a scheduled job. run_at = unix timestamp; None = run immediately.
        Returns job_id.
        """
        job_id = str(uuid.uuid4())[:8]
        scheduled_at = run_at or time.time()

        async with get_db() as db:
            await db.execute(
                """INSERT INTO jobs(id,name,type,status,slave_id,container,payload,created_at,scheduled_at)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                (job_id, name, job_type, "pending", slave_id, container,
                 json.dumps(payload), time.time(), scheduled_at)
            )
            await db.commit()

        return job_id

    async def get_job(self, job_id: str) -> Optional[dict]:
        async with get_db() as db:
            async with db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)) as cur:
                row = await cur.fetchone()
                return dict(row) if row else None

    async def list_jobs(self, status: str = None, limit: int = 50) -> list:
        async with get_db() as db:
            if status:
                async with db.execute(
                    "SELECT * FROM jobs WHERE status=? ORDER BY created_at DESC LIMIT ?",
                    (status, limit)
                ) as cur:
                    rows = await cur.fetchall()
            else:
                async with db.execute(
                    "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
                ) as cur:
                    rows = await cur.fetchall()
            return [dict(r) for r in rows]

    async def cancel_job(self, job_id: str) -> bool:
        async with get_db() as db:
            cur = await db.execute(
                "UPDATE jobs SET status='cancelled' WHERE id=? AND status='pending'",
                (job_id,)
            )
            await db.commit()
            return cur.rowcount > 0

    async def run(self, job_dispatcher):
        """Background loop that picks up due jobs."""
        self._running = True
        print("[Scheduler] Started")
        while self._running:
            await asyncio.sleep(self._tick_secs)
            await self._tick(job_dispatcher)

    async def _tick(self, dispatcher):
        """Find all pending jobs that are due and dispatch them."""
        now = time.time()
        async with get_db() as db:
            async with db.execute(
                "SELECT * FROM jobs WHERE status='pending' AND scheduled_at<=? LIMIT 10",
                (now,)
            ) as cur:
                rows = await cur.fetchall()

        for row in rows:
            job = dict(row)
            asyncio.create_task(dispatcher.execute_job(job))


# Global singleton
scheduler = Scheduler()