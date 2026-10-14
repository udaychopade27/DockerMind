import asyncio
import json
import time
from typing import List, Union, Optional
import httpx
from database import get_db, audit
from slave_registry import registry
from config import API_SECRET
import docker_ops


class JobDispatcher:
    """
    Executes single-slave and multi-slave fleet commands.
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
        headers = {"X-Slave-Token": API_SECRET}

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=body, headers=headers)
            resp.raise_for_status()
            return resp.json()

    async def dispatch_multi(self,
                             action: str,
                             container: str,
                             targets: Union[List[str], str] = "all",
                             tags: Optional[List[str]] = None,
                             payload: Optional[dict] = None,
                             user: str = "operator") -> dict:
        """
        Dispatch a Docker action (restart/stop/start/exec/logs) across multiple slave nodes concurrently.
        """
        payload = payload or {}
        target_slave_ids = []

        all_slaves = registry.all()
        slave_map = {s["slave_id"]: s for s in all_slaves}

        if targets == "all":
            target_slave_ids = [s["slave_id"] for s in all_slaves if s["is_online"]]
            target_slave_ids.append("local")
        elif isinstance(targets, list):
            target_slave_ids = targets
        elif isinstance(targets, str):
            target_slave_ids = [targets]

        if tags:
            tag_set = set(tags)
            filtered = []
            for sid in target_slave_ids:
                if sid == "local":
                    filtered.append(sid)
                elif sid in slave_map:
                    node_tags = set(slave_map[sid].get("tags", []))
                    if tag_set.intersection(node_tags):
                        filtered.append(sid)
            target_slave_ids = filtered

        # Remove duplicates
        target_slave_ids = list(dict.fromkeys(target_slave_ids))

        if not target_slave_ids:
            return {
                "action": action,
                "container": container,
                "total": 0,
                "successful": 0,
                "failed": 0,
                "nodes": {},
                "message": "No matching active slave nodes found",
            }

        async def _execute_on_slave(sid: str):
            try:
                res = await self._dispatch(action, sid, container, payload)
                return sid, res
            except Exception as e:
                return sid, {"success": False, "error": str(e)}

        tasks = [_execute_on_slave(sid) for sid in target_slave_ids]
        raw_results = await asyncio.gather(*tasks)

        nodes_result = {}
        success_count = 0
        fail_count = 0

        for sid, res in raw_results:
            nodes_result[sid] = res
            if res.get("success", False):
                success_count += 1
            else:
                fail_count += 1

        summary = {
            "action": action,
            "container": container,
            "total": len(target_slave_ids),
            "successful": success_count,
            "failed": fail_count,
            "nodes": nodes_result,
            "ts": time.time(),
        }

        await audit("multi_dispatch", target=container, user=user, result=summary)
        return summary

    async def _set_status(self, job_id: str, status: str,
                          started_at: float = None, finished_at: float = None,
                          result: dict = None):
        async with get_db() as db:
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
