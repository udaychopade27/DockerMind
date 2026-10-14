import asyncio
import httpx
import time
from typing import Optional, Dict
import docker_ops
import llm_client
from models.alerts import alert_store
from services.crash_detector import crash_detector
from slave_registry import registry
from services.notifier import notifier


class HealEngine:
    """
    Decides and executes healing actions with Exponential Backoff and Circuit Breaker.
    - Local containers: uses docker_ops directly
    - Slave containers: proxies command via slave's HTTP API
    - Exponential backoff: 10s, 30s, 60s, 120s, 300s
    - Circuit breaker: stops auto-restart after MAX_AUTO_RESTARTS to prevent thrashing
    """

    MAX_AUTO_RESTARTS = 5
    BACKOFF_DELAYS = [10, 30, 60, 120, 300]

    def __init__(self):
        # (slave_id, container_name) -> timestamp of last heal attempt
        self._last_healed: Dict[str, float] = {}
        # (slave_id, container_name) -> number of consecutive auto-heals
        self._attempt_counts: Dict[str, int] = {}
        # set of (slave_id, container_name) currently blocked by circuit breaker
        self._circuit_broken: set = set()

    def _get_backoff_delay(self, attempts: int) -> int:
        idx = min(max(0, attempts - 1), len(self.BACKOFF_DELAYS) - 1)
        return self.BACKOFF_DELAYS[idx]

    def is_circuit_broken(self, slave_id: str, container_name: str) -> bool:
        return f"{slave_id}:{container_name}" in self._circuit_broken

    def reset_backoff(self, slave_id: str, container_name: str):
        """Explicitly reset backoff and clear circuit breaker (e.g. after manual fix)."""
        key = f"{slave_id}:{container_name}"
        self._last_healed.pop(key, None)
        self._attempt_counts.pop(key, None)
        self._circuit_broken.discard(key)
        crash_detector.reset(slave_id, container_name)

    async def heal_container(self,
                             container_name: str,
                             slave_id: str = "local",
                             action: Optional[str] = None,
                             reason: Optional[str] = None) -> dict:
        """
        Heal a container with backoff and circuit-breaker protection.
        """
        key = f"{slave_id}:{container_name}"
        now = time.time()

        # Check circuit breaker
        if key in self._circuit_broken:
            return {
                "success": False,
                "skipped": True,
                "circuit_breaker": True,
                "reason": f"Circuit breaker tripped for {container_name}. Exceeded {self.MAX_AUTO_RESTARTS} restart attempts. Manual intervention required.",
                "container": container_name,
                "slave_id": slave_id,
            }

        attempts = self._attempt_counts.get(key, 0)
        cooldown = self._get_backoff_delay(attempts)

        # Check backoff cooldown
        if key in self._last_healed:
            elapsed = now - self._last_healed[key]
            if elapsed < cooldown:
                return {
                    "success": False,
                    "skipped": True,
                    "reason": f"Backoff active (attempt {attempts}) — healed {int(elapsed)}s ago, cooldown {cooldown}s (wait {int(cooldown - elapsed)}s)",
                    "container": container_name,
                    "slave_id": slave_id,
                    "attempt": attempts,
                }

        # Check if next restart trips circuit breaker
        if attempts >= self.MAX_AUTO_RESTARTS:
            self._circuit_broken.add(key)
            alert = alert_store.add(
                slave_id=slave_id,
                container_name=container_name,
                severity="critical",
                root_cause=f"Circuit breaker tripped — container crashed {attempts} times consecutively",
                fix="Auto-restarts halted to avoid infinite loop. Inspect application configuration or image.",
                auto_heal=False,
                heal_action="none",
            )
            await notifier.notify_alert(alert.to_dict())
            return {
                "success": False,
                "skipped": True,
                "circuit_breaker": True,
                "reason": f"Circuit breaker tripped after {attempts} attempts. Auto-restarts suspended.",
                "container": container_name,
                "slave_id": slave_id,
            }

        # If no action given, ask LLM
        if action is None:
            logs = self._get_logs(container_name, slave_id)
            analysis = await llm_client.analyze_logs(container_name, logs)
            action = analysis.get("heal_action", "none")
            severity = analysis.get("severity", "warn")
            root_cause = reason or analysis.get("root_cause", "unknown")
            fix = analysis.get("fix", "manual review")
            auto_heal = analysis.get("auto_heal", False)
        else:
            severity = "error"
            root_cause = reason or f"Auto-heal triggered: {action}"
            fix = action
            auto_heal = True

        result = {
            "container": container_name,
            "slave_id": slave_id,
            "action": action,
            "success": False,
            "attempt": attempts + 1,
        }

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
            self._attempt_counts[key] = attempts + 1
            # Note: Do NOT clear crash_detector history so crash-loop frequency remains accurate

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
                image = inspect.get("Config", {}).get("Image")
                try:
                    client = docker_ops.get_client()
                    client.images.pull(image)
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
