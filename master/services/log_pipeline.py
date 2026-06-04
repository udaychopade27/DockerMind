import asyncio
import time
from dataclasses import dataclass
from typing import Callable, Awaitable
import llm_client
from models.alerts import alert_store


@dataclass
class LogJob:
    slave_id: str
    container_id: str
    container_name: str
    logs: str
    ts: float


class LogPipeline:
    """
    Async queue that receives log batches from slaves,
    runs LLM analysis one-at-a-time (LLM semaphore already handles this),
    and calls the broadcast callback with alerts.
    """

    def __init__(self):
        self._queue: asyncio.Queue[LogJob] = asyncio.Queue(maxsize=50)
        self._broadcast_cb: Callable[[dict], Awaitable[None]] | None = None
        self._running = False
        self._processed = 0
        self._dropped = 0

    def set_broadcast(self, cb: Callable[[dict], Awaitable[None]]):
        """Register the WebSocket broadcast function."""
        self._broadcast_cb = cb

    async def push(self, slave_id: str, container_id: str,
                   container_name: str, logs: str) -> bool:
        """
        Add a log batch to the analysis queue.
        Returns False if queue is full (drops gracefully — don't block slave heartbeats).
        """
        job = LogJob(
            slave_id=slave_id,
            container_id=container_id,
            container_name=container_name,
            logs=logs,
            ts=time.time(),
        )
        try:
            self._queue.put_nowait(job)
            return True
        except asyncio.QueueFull:
            self._dropped += 1
            return False

    async def run(self):
        """Worker loop — runs as a background task."""
        self._running = True
        print("[LogPipeline] Worker started")
        while self._running:
            try:
                job = await asyncio.wait_for(self._queue.get(), timeout=5.0)
                await self._process(job)
                self._queue.task_done()
                self._processed += 1
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                print(f"[LogPipeline] Worker error: {e}")

    async def _process(self, job: LogJob):
        """Run LLM analysis on one log batch and fire alert if needed."""
        analysis = await llm_client.analyze_logs(job.container_name, job.logs)
        severity = analysis.get("severity", "ok")

        # Only store + broadcast if there's something worth alerting on
        if severity in ("warn", "error", "critical"):
            alert = alert_store.add(
                slave_id=job.slave_id,
                container_name=job.container_name,
                severity=severity,
                root_cause=analysis.get("root_cause", "unknown"),
                fix=analysis.get("fix", "review logs"),
                auto_heal=analysis.get("auto_heal", False),
                heal_action=analysis.get("heal_action", "none"),
            )
            if self._broadcast_cb:
                await self._broadcast_cb({
                    "event": "alert",
                    "alert": alert.to_dict(),
                    "analysis": analysis,
                    "slave_id": job.slave_id,
                    "container": job.container_name,
                    "ts": time.time(),
                })

    def stats(self) -> dict:
        return {
            "queue_size": self._queue.qsize(),
            "processed": self._processed,
            "dropped": self._dropped,
            "running": self._running,
        }


# Global singleton
log_pipeline = LogPipeline()