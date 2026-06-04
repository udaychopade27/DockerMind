import time
import asyncio
from typing import Dict, Tuple
from collections import defaultdict


class CrashDetector:
    """
    Tracks container die/restart events per slave.
    Fires crash-loop alert when a container dies N times within a time window.
    """

    CRASH_LOOP_THRESHOLD = 3      # restarts within window = crash loop
    CRASH_LOOP_WINDOW    = 300    # 5 minute window
    OOM_IMMEDIATE_ALERT  = True   # OOM kill always fires alert immediately

    def __init__(self):
        # {(slave_id, container_name): [(timestamp, exit_code), ...]}
        self._events: Dict[Tuple[str, str], list] = defaultdict(list)
        self._oom_counts: Dict[Tuple[str, str], int] = defaultdict(int)
        self._lock = asyncio.Lock()

    async def record_die(self, slave_id: str, container_name: str, exit_code: int) -> dict:
        """Record a container death. Returns analysis dict."""
        key = (slave_id, container_name)
        now = time.time()

        async with self._lock:
            self._events[key].append((now, exit_code))
            # Trim events outside window
            self._events[key] = [
                (ts, ec) for ts, ec in self._events[key]
                if now - ts <= self.CRASH_LOOP_WINDOW
            ]
            recent = self._events[key]

        crash_count = len(recent)
        is_crash_loop = crash_count >= self.CRASH_LOOP_THRESHOLD

        return {
            "container": container_name,
            "slave_id": slave_id,
            "exit_code": exit_code,
            "restarts_in_window": crash_count,
            "is_crash_loop": is_crash_loop,
            "is_oom": exit_code == 137,
            "window_secs": self.CRASH_LOOP_WINDOW,
            "severity": "critical" if is_crash_loop else ("error" if exit_code != 0 else "warn"),
            "root_cause": self._diagnose(exit_code, is_crash_loop, crash_count),
            "heal_action": "restart" if not is_crash_loop else "pull_restart",
        }

    async def record_oom(self, slave_id: str, container_name: str) -> dict:
        """Record an OOM kill event."""
        key = (slave_id, container_name)
        async with self._lock:
            self._oom_counts[key] += 1
            count = self._oom_counts[key]

        return {
            "container": container_name,
            "slave_id": slave_id,
            "oom_count": count,
            "severity": "critical",
            "root_cause": f"Container killed by OOM killer (total OOM events: {count}). Memory limit exceeded.",
            "fix": "Increase container memory limit or fix memory leak",
            "heal_action": "restart",
        }

    def get_restart_count(self, slave_id: str, container_name: str) -> int:
        return len(self._events.get((slave_id, container_name), []))

    def get_oom_count(self, slave_id: str, container_name: str) -> int:
        return self._oom_counts.get((slave_id, container_name), 0)

    def reset(self, slave_id: str, container_name: str):
        """Call when container is intentionally stopped/restarted by the agent."""
        key = (slave_id, container_name)
        self._events.pop(key, None)

    def summary(self) -> list:
        """Return containers with active crash patterns."""
        result = []
        now = time.time()
        for (slave_id, name), events in self._events.items():
            recent = [(ts, ec) for ts, ec in events if now - ts <= self.CRASH_LOOP_WINDOW]
            if recent:
                result.append({
                    "slave_id": slave_id,
                    "container": name,
                    "restarts_in_window": len(recent),
                    "is_crash_loop": len(recent) >= self.CRASH_LOOP_THRESHOLD,
                    "oom_count": self._oom_counts.get((slave_id, name), 0),
                })
        return result

    @staticmethod
    def _diagnose(exit_code: int, is_crash_loop: bool, count: int) -> str:
        if is_crash_loop:
            return f"Crash loop detected — container restarted {count}x in 5 minutes"
        if exit_code == 137:
            return "OOM kill (exit 137) — container exceeded memory limit"
        if exit_code == 1:
            return "Container exited with error code 1 — check application logs"
        if exit_code == 2:
            return "Container exited with code 2 — misuse of shell builtins or config error"
        if exit_code == 125:
            return "Docker daemon error — container failed to start"
        if exit_code == 126:
            return "Permission denied — cannot invoke command in container"
        if exit_code == 127:
            return "Command not found inside container"
        if exit_code > 128:
            sig = exit_code - 128
            signals = {9: "SIGKILL", 15: "SIGTERM", 11: "SIGSEGV", 6: "SIGABRT"}
            sig_name = signals.get(sig, f"signal {sig}")
            return f"Container killed by {sig_name} (exit {exit_code})"
        return f"Container exited with code {exit_code}"


# Global singleton
crash_detector = CrashDetector()