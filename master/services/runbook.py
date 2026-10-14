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
        "description": "Restart all containers not in running state with verification",
        "trigger": "manual",
        "stop_on_failure": 1,
        "retry_count": 2,
        "steps": json.dumps([
            {"type": "log_check",  "description": "Check logs before restart", "optional": True},
            {"type": "restart",    "description": "Restart the container", "retry_count": 2},
            {"type": "log_check",  "description": "Verify recovery after restart"},
        ]),
    },
    {
        "id": "rb-crash-loop-recover",
        "name": "Crash loop recovery",
        "description": "Graceful stop, pull/recovery execution, and fresh start",
        "trigger": "crash_loop",
        "stop_on_failure": 1,
        "retry_count": 1,
        "steps": json.dumps([
            {"type": "stop",       "description": "Stop the crashing container"},
            {"type": "exec",       "command": "echo recovering", "description": "Log recovery attempt", "optional": True},
            {"type": "start",      "description": "Start fresh", "retry_count": 2},
            {"type": "log_check",  "description": "Check recovery logs"},
        ]),
    },
    {
        "id": "rb-health-check",
        "name": "Full health check",
        "description": "Check logs on all running containers and surface anomalies",
        "trigger": "manual",
        "stop_on_failure": 0,
        "retry_count": 1,
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
                    """INSERT OR IGNORE INTO runbooks(id,name,description,trigger,steps,stop_on_failure,retry_count,created_at)
                       VALUES(?,?,?,?,?,?,?,?)""",
                    (rb["id"], rb["name"], rb["description"],
                     rb["trigger"], rb["steps"], rb.get("stop_on_failure", 1), rb.get("retry_count", 1), time.time())
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
                              trigger: str, steps: list,
                              stop_on_failure: bool = True,
                              retry_count: int = 1) -> str:
        rb_id = f"rb-{str(uuid.uuid4())[:6]}"
        async with get_db() as db:
            await db.execute(
                """INSERT INTO runbooks(id,name,description,trigger,steps,stop_on_failure,retry_count,created_at)
                   VALUES(?,?,?,?,?,?,?,?)""",
                (rb_id, name, description, trigger, json.dumps(steps),
                 1 if stop_on_failure else 0, retry_count, time.time())
            )
            await db.commit()
        return rb_id

    async def execute_runbook(self, runbook_id: str,
                               slave_id: str, container: str,
                               stop_on_failure: Optional[bool] = None,
                               retry_count: Optional[int] = None) -> dict:
        rb = await self.get_runbook(runbook_id)
        if not rb:
            return {"success": False, "error": f"Runbook '{runbook_id}' not found"}
        if not rb["enabled"]:
            return {"success": False, "error": "Runbook is disabled"}

        should_stop = stop_on_failure if stop_on_failure is not None else bool(rb.get("stop_on_failure", 1))
        default_retries = retry_count if retry_count is not None else int(rb.get("retry_count", 1))

        steps = json.loads(rb["steps"])
        results = []
        overall_success = True
        stopped_early = False

        for i, step in enumerate(steps):
            step_retries = step.get("retry_count", default_retries)
            is_optional = step.get("optional", False)
            step_result = None
            attempts_made = 0

            # Step execution loop with retries and exponential backoff
            for attempt in range(step_retries + 1):
                attempts_made = attempt + 1
                step_result = await self._run_step(step, slave_id, container)
                if step_result.get("success", True):
                    break
                if attempt < step_retries:
                    await asyncio.sleep(1.0 * (attempt + 1))

            step_success = step_result.get("success", True) if step_result else False
            results.append({
                "step": i + 1,
                "description": step.get("description", step["type"]),
                "type": step["type"],
                "attempts": attempts_made,
                "optional": is_optional,
                "success": step_success,
                "result": step_result,
            })

            if not step_success:
                if not is_optional:
                    overall_success = False
                    if should_stop:
                        stopped_early = True
                        break

        # Update run stats
        async with get_db() as db:
            await db.execute(
                "UPDATE runbooks SET last_run=?, run_count=run_count+1 WHERE id=?",
                (time.time(), runbook_id)
            )
            await db.commit()

        await audit("runbook_executed", target=runbook_id,
                    slave_id=slave_id, container=container,
                    result={"success": overall_success, "steps_run": len(results), "stopped_early": stopped_early})

        return {
            "runbook_id": runbook_id,
            "runbook_name": rb["name"],
            "slave_id": slave_id,
            "container": container,
            "success": overall_success,
            "stopped_on_failure": stopped_early,
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