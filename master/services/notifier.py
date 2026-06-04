import asyncio
import httpx
import json
import os
import time
from typing import Optional


class Notifier:
    """
    Sends alert notifications to webhooks (Slack, Discord, generic HTTP).
    Configure via environment variables.
    """

    def __init__(self):
        self.slack_url    = os.getenv("SLACK_WEBHOOK_URL", "")
        self.discord_url  = os.getenv("DISCORD_WEBHOOK_URL", "")
        self.webhook_url  = os.getenv("GENERIC_WEBHOOK_URL", "")
        self.min_severity = os.getenv("NOTIFY_MIN_SEVERITY", "error")  # warn|error|critical
        self._severity_rank = {"ok": 0, "warn": 1, "error": 2, "critical": 3}

    def _should_notify(self, severity: str) -> bool:
        return self._severity_rank.get(severity, 0) >= self._severity_rank.get(self.min_severity, 2)

    async def notify_alert(self, alert: dict):
        """Send alert to all configured channels."""
        if not self._should_notify(alert.get("severity", "ok")):
            return
        tasks = []
        if self.slack_url:
            tasks.append(self._send_slack(alert))
        if self.discord_url:
            tasks.append(self._send_discord(alert))
        if self.webhook_url:
            tasks.append(self._send_generic(alert))
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def notify_heal(self, container: str, slave_id: str, action: str, success: bool):
        """Notify when an auto-heal action is taken."""
        msg = {
            "severity": "warn" if success else "error",
            "container_name": container,
            "slave_id": slave_id,
            "root_cause": f"Auto-heal triggered: {action}",
            "fix": "Heal completed" if success else "Heal failed — manual intervention needed",
        }
        await self.notify_alert(msg)

    async def _send_slack(self, alert: dict):
        emoji = {"ok": "✅", "warn": "⚠️", "error": "🔴", "critical": "🚨"}.get(alert.get("severity", "ok"), "ℹ️")
        payload = {
            "text": f"{emoji} *DockerMind Alert*",
            "attachments": [{
                "color": {"ok": "good", "warn": "warning", "error": "danger", "critical": "danger"}.get(alert.get("severity"), "warning"),
                "fields": [
                    {"title": "Container", "value": alert.get("container_name", "unknown"), "short": True},
                    {"title": "Slave",     "value": alert.get("slave_id", "local"),         "short": True},
                    {"title": "Severity",  "value": alert.get("severity", "?").upper(),     "short": True},
                    {"title": "Root Cause","value": alert.get("root_cause", ""),            "short": False},
                    {"title": "Fix",       "value": alert.get("fix", ""),                   "short": False},
                ],
                "footer": f"DockerMind • {time.strftime('%Y-%m-%d %H:%M:%S')}",
            }]
        }
        await self._post(self.slack_url, payload)

    async def _send_discord(self, alert: dict):
        color = {"ok": 0x57F287, "warn": 0xFEE75C, "error": 0xED4245, "critical": 0xED4245}.get(alert.get("severity"), 0xFEE75C)
        payload = {
            "embeds": [{
                "title": f"DockerMind Alert — {alert.get('severity', '?').upper()}",
                "color": color,
                "fields": [
                    {"name": "Container", "value": alert.get("container_name", "unknown"), "inline": True},
                    {"name": "Slave",     "value": alert.get("slave_id", "local"),         "inline": True},
                    {"name": "Root Cause","value": alert.get("root_cause", ""),            "inline": False},
                    {"name": "Fix",       "value": alert.get("fix", ""),                   "inline": False},
                ],
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            }]
        }
        await self._post(self.discord_url, payload)

    async def _send_generic(self, alert: dict):
        await self._post(self.webhook_url, alert)

    async def _post(self, url: str, payload: dict):
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code >= 400:
                    print(f"[Notifier] Webhook returned {resp.status_code}: {url}")
        except Exception as e:
            print(f"[Notifier] Failed to send notification: {e}")


# Global singleton
notifier = Notifier()