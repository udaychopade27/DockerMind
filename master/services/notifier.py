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



    async def load_settings(self):
        """Load webhook configuration from database, falling back to env vars."""
        try:
            from database import db_get_all_settings
            stored = await db_get_all_settings()
            self.slack_url = stored.get("slack_webhook_url", os.getenv("SLACK_WEBHOOK_URL", ""))
            self.discord_url = stored.get("discord_webhook_url", os.getenv("DISCORD_WEBHOOK_URL", ""))
            self.webhook_url = stored.get("generic_webhook_url", os.getenv("GENERIC_WEBHOOK_URL", ""))
            self.min_severity = stored.get("min_severity", os.getenv("NOTIFY_MIN_SEVERITY", "warn"))
            print(f"[Notifier] Webhook settings loaded. Slack configured: {bool(self.slack_url)}, Discord configured: {bool(self.discord_url)}, Min Severity: {self.min_severity}")
        except Exception as e:
            print(f"[Notifier] Could not load settings from DB: {e}")

    def get_config(self) -> dict:
        """Return current webhook configuration state."""
        return {
            "slack_configured": bool(self.slack_url),
            "discord_configured": bool(self.discord_url),
            "generic_configured": bool(self.webhook_url),
            "slack_webhook_url": self.slack_url if self.slack_url else "",
            "discord_webhook_url": self.discord_url if self.discord_url else "",
            "generic_webhook_url": self.webhook_url if self.webhook_url else "",
            "min_severity": self.min_severity,
        }

    async def update_config(self, slack_url: Optional[str] = None, discord_url: Optional[str] = None,
                            generic_url: Optional[str] = None, min_severity: Optional[str] = None):
        """Update webhook configuration and persist to SQLite."""
        from database import db_set_setting
        if slack_url is not None:
            self.slack_url = slack_url.strip()
            await db_set_setting("slack_webhook_url", self.slack_url)
        if discord_url is not None:
            self.discord_url = discord_url.strip()
            await db_set_setting("discord_webhook_url", self.discord_url)
        if generic_url is not None:
            self.webhook_url = generic_url.strip()
            await db_set_setting("generic_webhook_url", self.webhook_url)
        if min_severity is not None and min_severity in ("warn", "error", "critical"):
            self.min_severity = min_severity
            await db_set_setting("min_severity", self.min_severity)

    async def send_test_notification(self) -> dict:
        """Send a diagnostic test alert to all configured webhooks."""
        test_alert = {
            "severity": "warn",
            "container_name": "dockermind-platform",
            "slave_id": "master (local)",
            "root_cause": "Diagnostic ping — webhook delivery verification test",
            "fix": "No action needed. Notifications are operational.",
        }
        results = {}
        if self.slack_url:
            try:
                await self._send_slack(test_alert)
                results["slack"] = "sent"
            except Exception as e:
                results["slack"] = f"error: {str(e)}"
        else:
            results["slack"] = "not_configured"

        if self.discord_url:
            try:
                await self._send_discord(test_alert)
                results["discord"] = "sent"
            except Exception as e:
                results["discord"] = f"error: {str(e)}"
        else:
            results["discord"] = "not_configured"

        return results

# Global singleton
notifier = Notifier()