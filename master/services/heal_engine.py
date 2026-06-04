import asyncio
import httpx
import time
from typing import Optional
import docker_ops
import llm_client
from models.alerts import alert_store
from services.crash_detector import crash_detector
from slave_registry import registry


class HealEngine:
    """
    Decides and executes healing actions.
    - Local containers: uses docker_ops directly
    - Slave containers: proxies command via slave's HTTP API
    """

    # Backoff: don't heal the same container more than once per N seconds
    HEAL_COOLDOWN_SECS = 60
    _last_healed: dict = {}

    async def heal_container(self,
                             container_name: str,
                             slave_id: str = "local",
                             action: Optional[str] = None) -> dict:
        """
        Heal a container. If action is None, fetches logs and asks LLM first.
        Returns full result dict.
        """
        key = f"{slave_id}:{container_name}"
        now = time.time()

        # Cooldown check
        if key in self._last_healed:
            elapsed = now - self._last_healed[key]
            if elapsed < self.HEAL_COOLDOWN_SECS:
                return {
                    "success": False,
                    "skipped": True,
                    "reason": f"Cooldown active — healed {int(elapsed)}s ago, wait {self.HEAL_COOLDOWN_SECS - int(elapsed)}s",
                    "container": container_name,
                    "slave_id": slave_id,
                }

        # If no action given, ask LLM
        if action is None:
            logs = self._get_logs(container_name, slave_id)
            analysis = await llm_client.analyze_logs(container_name, logs)
            action = analysis.get("heal_action", "none")
            severity = analysis.get("severity", "warn")
            root_cause = analysis.get("root_cause", "unknown")
            fix = analysis.get("fix", "manual review")
            auto_heal = analysis.get("auto_heal", False)
        else:
            severity = "error"
            root_cause = f"Manual heal triggered: {action}"
            fix = action
            auto_heal = True

        result = {"container": container_name, "slave_id": slave_id,
                  "action": action, "success": False}

        if action == "none" or not auto_heal:
            result["message"] = "No auto-heal action — manual review required"
            return result

        # Execute heal
        if slave_id == "local":
            result.update(self._heal_local(container_name, action))
        else:
            result.update(await self._heal_remote(container_name, slave_id, action))

        if result.get("success"):
            self._last_healed[key] = time.time()
            crash_detector.reset(slave_id, container_name)

        # Store alert
        alert_store.add(
            slave_id=slave_id,
            container_name=container_name,
            severity=severity,
            root_cause=root_cause,
            fix=fix,
            auto_heal=auto_heal,
            heal_action=action,
        )

        return result

    def _get_logs(self, container_name: str, slave_id: str) -> str:
        if slave_id == "local":
            return docker_ops.get_logs(container_name, tail=100)
        # For remote slave — return empty string; log analysis happens via log pipeline
        return ""

    def _heal_local(self, container_name: str, action: str) -> dict:
        if action == "restart":
            return docker_ops.restart_container(container_name)
        if action == "start":
            return docker_ops.start_container(container_name)
        if action == "stop":
            return docker_ops.stop_container(container_name)
        if action == "pull_restart":
            docker_ops.stop_container(container_name)
            inspect = docker_ops.inspect_container(container_name)
            if inspect:
                image = inspect["Config"]["Image"]
                try:
                    import docker
                    docker.DockerClient().images.pull(image)
                except Exception as e:
                    return {"success": False, "message": f"Pull failed: {e}"}
            docker_ops.start_container(container_name)
            return {"success": True, "message": f"Pull+restart done for {container_name}"}
        if action.startswith("exec:"):
            cmd = action[5:]
            return docker_ops.exec_in_container(container_name, cmd)
        return {"success": False, "message": f"Unknown action: {action}"}

    async def _heal_remote(self, container_name: str, slave_id: str, action: str) -> dict:
        node = registry.get(slave_id)
        if not node:
            return {"success": False, "message": f"Slave '{slave_id}' not found in registry"}
        if not node.is_online:
            return {"success": False, "message": f"Slave '{slave_id}' is offline"}

        url = f"http://{node.ip}:{node.port}/command"
        payload = {
            "action": action if not action.startswith("exec:") else "exec",
            "container": container_name,
            "command": action[5:] if action.startswith("exec:") else "",
        }
        headers = {"X-Slave-Token": slave_id}

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                return resp.json()
        except httpx.TimeoutException:
            return {"success": False, "message": "Slave command timed out"}
        except Exception as e:
            return {"success": False, "message": str(e)}


# Global singleton
heal_engine = HealEngine()