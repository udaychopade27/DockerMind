import asyncio
import json
import time
import httpx
from database import get_db, audit
from slave_registry import registry
import docker_ops


class JobDispatcher:
    """
    Executes scheduled and on-demand jobs.
    Updates job status in SQLite in real time.
    """

    async def execute_job(self, job: dict):
        job_id = job["id"]
        await self._set_status(job_id, "running", started_at=time.time())

        try:
            payload = json.loads(job.get("payload") or "{}")
            result = await self._dispatch(job["type"], job.get("slave_id", "local"),
                                          job.get("container", ""), payload)
            await self._set_status(job_id, "done", finished_at=time.time(), result=result)
            await audit("job_done", target=job_id, slave_id=job.get("slave_id"),
                        container=job.get("container"), result=result)
        except Exception as e:
            err = {"success": False, "error": str(e)}
            await self._set_status(job_id, "failed", finished_at=time.time(), result=err)
            await audit("job_failed", target=job_id, result=err)

    async def _dispatch(self, job_type: str, slave_id: str, container: str, payload: dict) -> dict:
        if slave_id == "local":
            return self._run_local(job_type, container, payload)
        return await self._run_remote(job_type, slave_id, container, payload)

    def _run_local(self, job_type: str, container: str, payload: dict) -> dict:
        if job_type == "restart":
            return docker_ops.restart_container(container)
        if job_type == "stop":
            return docker_ops.stop_container(container)
        if job_type == "start":
            return docker_ops.start_container(container)
        if job_type == "exec":
            return docker_ops.exec_in_container(container, payload.get("command", "echo ok"))
        if job_type == "log_check":
            logs = docker_ops.get_logs(container, tail=50)
            return {"success": True, "log_lines": logs.count("\n"), "output": logs[-1000:]}
        return {"success": False, "error": f"Unknown job type: {job_type}"}

    async def _run_remote(self, job_type: str, slave_id: str, container: str, payload: dict) -> dict:
        node = registry.get(slave_id)
        if not node:
            return {"success": False, "error": f"Slave '{slave_id}' not registered"}
        if not node.is_online:
            return {"success": False, "error": f"Slave '{slave_id}' is offline"}

        url = f"http://{node.ip}:{node.port}/command"
        body = {"action": job_type, "container": container, **payload}
        headers = {"X-Slave-Token": slave_id}

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=body, headers=headers)
            resp.raise_for_status()
            return resp.json()

    async def _set_status(self, job_id: str, status: str,
                          started_at: float = None, finished_at: float = None,
                          result: dict = None):
        async with await get_db() as db:
            await db.execute(
                """UPDATE jobs SET status=?,
                   started_at=COALESCE(?,started_at),
                   finished_at=COALESCE(?,finished_at),
                   result=COALESCE(?,result)
                   WHERE id=?""",
                (status, started_at, finished_at,
                 json.dumps(result) if result else None, job_id)
            )
            await db.commit()


# Global singleton
job_dispatcher = JobDispatcher()