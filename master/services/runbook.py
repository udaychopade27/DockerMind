import asyncio
import json
import time
import uuid
from typing import Optional
from database import get_db, audit
from services.job_dispatcher import job_dispatcher


# ── Built-in runbooks installed on first run ──────────────────────────────────

BUILTIN_RUNBOOKS = [
    {
        "id": "rb-restart-unhealthy",
        "name": "Restart unhealthy containers",
        "description": "Restart all containers not in running state",
        "trigger": "manual",
        "steps": json.dumps([
            {"type": "log_check",  "description": "Check logs before restart"},
            {"type": "restart",    "description": "Restart the container"},
            {"type": "log_check",  "description": "Verify recovery after restart"},
        ]),
    },
    {
        "id": "rb-crash-loop-recover",
        "name": "Crash loop recovery",
        "description": "Pull latest image and restart on crash loop",
        "trigger": "crash_loop",
        "steps": json.dumps([
            {"type": "stop",       "description": "Stop the crashing container"},
            {"type": "exec",       "command": "echo recovering", "description": "Log recovery attempt"},
            {"type": "start",      "description": "Start fresh"},
            {"type": "log_check",  "description": "Check recovery logs"},
        ]),
    },
    {
        "id": "rb-health-check",
        "name": "Full health check",
        "description": "Check logs on all running containers and surface anomalies",
        "trigger": "manual",
        "steps": json.dumps([
            {"type": "log_check", "description": "Analyze recent logs"},
        ]),
    },
]


class RunbookEngine:

    async def seed_builtins(self):
        """Insert built-in runbooks if they don't exist yet."""
        async with get_db() as db:
            for rb in BUILTIN_RUNBOOKS:
                await db.execute(
                    """INSERT OR IGNORE INTO runbooks(id,name,description,trigger,steps,created_at)
                       VALUES(?,?,?,?,?,?)""",
                    (rb["id"], rb["name"], rb["description"],
                     rb["trigger"], rb["steps"], time.time())
                )
            await db.commit()

    async def list_runbooks(self) -> list:
        async with get_db() as db:
            async with db.execute(
                "SELECT * FROM runbooks ORDER BY name") as cur:
                rows = await cur.fetchall()

                columns = [
                    desc[0]
                    for desc in cur.description
                ]

                return [
                    dict(zip(columns, row))
                    for row in rows
                ]


    async def get_runbook(self, runbook_id: str) -> Optional[dict]:
        async with get_db() as db:
            async with db.execute("SELECT * FROM runbooks WHERE id=?", (runbook_id,)) as cur:
                row = await cur.fetchone()
                return dict(row) if row else None

    async def create_runbook(self, name: str, description: str,
                              trigger: str, steps: list) -> str:
        rb_id = f"rb-{str(uuid.uuid4())[:6]}"
        async with get_db() as db:
            await db.execute(
                "INSERT INTO runbooks(id,name,description,trigger,steps,created_at) VALUES(?,?,?,?,?,?)",
                (rb_id, name, description, trigger, json.dumps(steps), time.time())
            )
            await db.commit()
        return rb_id

    async def execute_runbook(self, runbook_id: str,
                               slave_id: str, container: str) -> dict:
        rb = await self.get_runbook(runbook_id)
        if not rb:
            return {"success": False, "error": f"Runbook '{runbook_id}' not found"}
        if not rb["enabled"]:
            return {"success": False, "error": "Runbook is disabled"}

        steps = json.loads(rb["steps"])
        results = []
        success = True

        for i, step in enumerate(steps):
            step_result = await self._run_step(step, slave_id, container)
            results.append({
                "step": i + 1,
                "description": step.get("description", step["type"]),
                "type": step["type"],
                "result": step_result,
            })
            if not step_result.get("success", True):
                success = False
                # Continue on failure — collect all results

        # Update run stats
        async with get_db() as db:
            await db.execute(
                "UPDATE runbooks SET last_run=?, run_count=run_count+1 WHERE id=?",
                (time.time(), runbook_id)
            )
            await db.commit()

        await audit("runbook_executed", target=runbook_id,
                    slave_id=slave_id, container=container,
                    result={"success": success, "steps_run": len(results)})

        return {
            "runbook_id": runbook_id,
            "runbook_name": rb["name"],
            "slave_id": slave_id,
            "container": container,
            "success": success,
            "steps": results,
            "ts": time.time(),
        }

    async def _run_step(self, step: dict, slave_id: str, container: str) -> dict:
        job_type = step["type"]
        payload = {}
        if "command" in step:
            payload["command"] = step["command"]

        # Re-use job dispatcher for each step
        job = {
            "id": f"rb-step-{uuid.uuid4().hex[:6]}",
            "type": job_type,
            "slave_id": slave_id,
            "container": container,
            "payload": json.dumps(payload),
            "status": "pending",
        }
        try:
            result = await job_dispatcher._dispatch(job_type, slave_id, container, payload)
            return result
        except Exception as e:
            return {"success": False, "error": str(e)}


# Global singleton
runbook_engine = RunbookEngine()