import asyncio
import httpx
import json
import os
import smtplib
import time
from email.message import EmailMessage
from typing import Optional
from config import mask_secret


class Notifier:
    """
    Sends alert notifications to webhooks (Slack, Discord, generic HTTP)
    and Email / SMTP (Gmail App Password, SendGrid, etc.).
    Supports persistent configuration in SQLite with zero-downtime hot reloading.
    """

    def __init__(self):
        # Webhooks
        self.slack_url    = os.getenv("SLACK_WEBHOOK_URL", "")
        self.discord_url  = os.getenv("DISCORD_WEBHOOK_URL", "")
        self.webhook_url  = os.getenv("GENERIC_WEBHOOK_URL", "")
        self.min_severity = os.getenv("NOTIFY_MIN_SEVERITY", "warn")  # warn|error|critical
        self._severity_rank = {"ok": 0, "warn": 1, "error": 2, "critical": 3}

        # Email / SMTP
        self.smtp_host     = os.getenv("SMTP_HOST", "")
        self.smtp_port     = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user     = os.getenv("SMTP_USER", "")
        self.smtp_password = os.getenv("SMTP_PASSWORD", "")
        self.smtp_from     = os.getenv("SMTP_FROM", "")
        self.smtp_to       = os.getenv("SMTP_TO", "")
        self.smtp_tls      = os.getenv("SMTP_TLS", "true").lower() in ("true", "1", "yes")

    def _should_notify(self, severity: str) -> bool:
        return self._severity_rank.get(severity, 0) >= self._severity_rank.get(self.min_severity, 1)

    async def notify_alert(self, alert: dict):
        """Send alert to all configured channels (Webhooks + Email)."""
        if not self._should_notify(alert.get("severity", "ok")):
            return
        tasks = []
        if self.slack_url:
            tasks.append(self._send_slack(alert))
        if self.discord_url:
            tasks.append(self._send_discord(alert))
        if self.webhook_url:
            tasks.append(self._send_generic(alert))
        if self.smtp_host and self.smtp_to:
            tasks.append(self._send_email(alert))
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

    async def _send_email(self, alert: dict):
        """Asynchronously dispatch email via standard SMTP."""
        subject = f"[DockerMind Alert - {alert.get('severity', '?').upper()}] {alert.get('container_name', 'System')}"
        body = (
            f"DockerMind Automated Alert Notification\n"
            f"----------------------------------------\n"
            f"Severity:       {alert.get('severity', '?').upper()}\n"
            f"Container:      {alert.get('container_name', 'unknown')}\n"
            f"Node / Slave:   {alert.get('slave_id', 'local')}\n"
            f"Root Cause:     {alert.get('root_cause', 'N/A')}\n"
            f"Recommended Fix:{alert.get('fix', 'N/A')}\n"
            f"Timestamp:      {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}\n"
        )
        await asyncio.to_thread(
            self._sync_send_smtp,
            self.smtp_host,
            self.smtp_port,
            self.smtp_user,
            self.smtp_password,
            self.smtp_from or self.smtp_user,
            self.smtp_to,
            self.smtp_tls,
            subject,
            body
        )

    def _sync_send_smtp(self, host: str, port: int, user: str, password: str,
                        from_addr: str, to_addr: str, use_tls: bool, subject: str, body: str):
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = from_addr or user
        msg["To"] = to_addr
        msg.set_content(body)

        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=12) as server:
                if user and password:
                    server.login(user, password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=12) as server:
                if use_tls:
                    server.starttls()
                if user and password:
                    server.login(user, password)
                server.send_message(msg)

    async def _post(self, url: str, payload: dict):
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code >= 400:
                    print(f"[Notifier] Webhook returned {resp.status_code}: {url}")
        except Exception as e:
            print(f"[Notifier] Failed to send notification: {e}")

    async def load_settings(self):
        """Load webhook and SMTP configuration from database, falling back to env vars."""
        try:
            from database import db_get_all_settings
            stored = await db_get_all_settings()
            
            self.slack_url    = stored.get("slack_webhook_url", os.getenv("SLACK_WEBHOOK_URL", ""))
            self.discord_url  = stored.get("discord_webhook_url", os.getenv("DISCORD_WEBHOOK_URL", ""))
            self.webhook_url  = stored.get("generic_webhook_url", os.getenv("GENERIC_WEBHOOK_URL", ""))
            self.min_severity = stored.get("min_severity", os.getenv("NOTIFY_MIN_SEVERITY", "warn"))

            self.smtp_host     = stored.get("smtp_host", os.getenv("SMTP_HOST", ""))
            self.smtp_port     = int(stored.get("smtp_port", os.getenv("SMTP_PORT", "587")))
            self.smtp_user     = stored.get("smtp_user", os.getenv("SMTP_USER", ""))
            self.smtp_password = stored.get("smtp_password", os.getenv("SMTP_PASSWORD", ""))
            self.smtp_from     = stored.get("smtp_from", os.getenv("SMTP_FROM", ""))
            self.smtp_to       = stored.get("smtp_to", os.getenv("SMTP_TO", ""))
            self.smtp_tls      = str(stored.get("smtp_tls", os.getenv("SMTP_TLS", "true"))).lower() in ("true", "1", "yes")

            print(f"[Notifier] Notification vault loaded. Slack: {bool(self.slack_url)}, Discord: {bool(self.discord_url)}, SMTP: {bool(self.smtp_host and self.smtp_to)}")
        except Exception as e:
            print(f"[Notifier] Could not load settings from DB: {e}")

    def get_config(self) -> dict:
        """Return current notification configuration state with masked secrets."""
        return {
            "slack_configured": bool(self.slack_url),
            "slack_webhook_url": self.slack_url if self.slack_url else "",
            "slack_webhook_url_masked": mask_secret(self.slack_url),
            "discord_configured": bool(self.discord_url),
            "discord_webhook_url": self.discord_url if self.discord_url else "",
            "discord_webhook_url_masked": mask_secret(self.discord_url),
            "generic_configured": bool(self.webhook_url),
            "generic_webhook_url": self.webhook_url if self.webhook_url else "",
            "generic_webhook_url_masked": mask_secret(self.webhook_url),
            "min_severity": self.min_severity,
            "smtp_configured": bool(self.smtp_host and self.smtp_to),
            "smtp_host": self.smtp_host,
            "smtp_port": self.smtp_port,
            "smtp_user": self.smtp_user,
            "smtp_pass_masked": mask_secret(self.smtp_password),
            "smtp_from": self.smtp_from,
            "smtp_to": self.smtp_to,
            "smtp_tls": self.smtp_tls,
        }

    async def update_config(
        self,
        slack_url: Optional[str] = None,
        discord_url: Optional[str] = None,
        generic_url: Optional[str] = None,
        min_severity: Optional[str] = None,
        smtp_host: Optional[str] = None,
        smtp_port: Optional[int] = None,
        smtp_user: Optional[str] = None,
        smtp_password: Optional[str] = None,
        smtp_from: Optional[str] = None,
        smtp_to: Optional[str] = None,
        smtp_tls: Optional[bool] = None,
    ):
        """Update notification configuration and persist to SQLite."""
        from database import db_set_setting
        if slack_url is not None and not ("*" in slack_url and "..." in slack_url):
            self.slack_url = slack_url.strip()
            await db_set_setting("slack_webhook_url", self.slack_url)

        if discord_url is not None and not ("*" in discord_url and "..." in discord_url):
            self.discord_url = discord_url.strip()
            await db_set_setting("discord_webhook_url", self.discord_url)

        if generic_url is not None and not ("*" in generic_url and "..." in generic_url):
            self.webhook_url = generic_url.strip()
            await db_set_setting("generic_webhook_url", self.webhook_url)

        if min_severity is not None and min_severity in ("warn", "error", "critical"):
            self.min_severity = min_severity
            await db_set_setting("min_severity", self.min_severity)

        if smtp_host is not None:
            self.smtp_host = smtp_host.strip()
            await db_set_setting("smtp_host", self.smtp_host)

        if smtp_port is not None:
            self.smtp_port = int(smtp_port)
            await db_set_setting("smtp_port", str(self.smtp_port))

        if smtp_user is not None:
            self.smtp_user = smtp_user.strip()
            await db_set_setting("smtp_user", self.smtp_user)

        if smtp_password is not None and not ("*" in smtp_password and "..." in smtp_password):
            self.smtp_password = smtp_password.strip()
            await db_set_setting("smtp_password", self.smtp_password)

        if smtp_from is not None:
            self.smtp_from = smtp_from.strip()
            await db_set_setting("smtp_from", self.smtp_from)

        if smtp_to is not None:
            self.smtp_to = smtp_to.strip()
            await db_set_setting("smtp_to", self.smtp_to)

        if smtp_tls is not None:
            self.smtp_tls = bool(smtp_tls)
            await db_set_setting("smtp_tls", "true" if self.smtp_tls else "false")

    async def send_test_notification(self, channel: str = "all") -> dict:
        """Send a diagnostic test alert to selected or all configured channels."""
        test_alert = {
            "severity": "warn",
            "container_name": "dockermind-platform",
            "slave_id": "master (local)",
            "root_cause": "Diagnostic ping — delivery verification test",
            "fix": "No action needed. Notifications are operational.",
        }
        results = {}

        # 1. Slack
        if channel in ("all", "slack"):
            if self.slack_url:
                try:
                    await self._send_slack(test_alert)
                    results["slack"] = "sent"
                except Exception as e:
                    results["slack"] = f"error: {str(e)}"
            else:
                results["slack"] = "not_configured"

        # 2. Discord
        if channel in ("all", "discord"):
            if self.discord_url:
                try:
                    await self._send_discord(test_alert)
                    results["discord"] = "sent"
                except Exception as e:
                    results["discord"] = f"error: {str(e)}"
            else:
                results["discord"] = "not_configured"

        # 3. Generic Webhook
        if channel in ("all", "generic"):
            if self.webhook_url:
                try:
                    await self._send_generic(test_alert)
                    results["generic"] = "sent"
                except Exception as e:
                    results["generic"] = f"error: {str(e)}"
            else:
                results["generic"] = "not_configured"

        # 4. Email / SMTP
        if channel in ("all", "email"):
            if self.smtp_host and self.smtp_to:
                try:
                    await self._send_email(test_alert)
                    results["email"] = "sent"
                except Exception as e:
                    results["email"] = f"error: {str(e)}"
            else:
                results["email"] = "not_configured (requires SMTP host & recipient email)"

        return results


# Global singleton
notifier = Notifier()
