import uuid
import time
import asyncio
from collections import deque
from typing import List, Optional
from models.events import Alert


class AlertStore:
    """Thread-safe alert store backed by SQLite for persistence across restarts."""

    def __init__(self, maxlen: int = 500):
        self._alerts: deque[Alert] = deque(maxlen=maxlen)

    async def load_from_db(self):
        """Pre-populate alerts from SQLite on master startup."""
        try:
            from database import db_load_recent_alerts
            rows = await db_load_recent_alerts(limit=500)
            self._alerts.clear()
            for r in rows:
                try:
                    alert = Alert(
                        alert_id=r["alert_id"],
                        slave_id=r["slave_id"],
                        container_name=r["container_name"],
                        severity=r["severity"],
                        root_cause=r["root_cause"],
                        fix=r["fix"],
                        auto_heal=r["auto_heal"],
                        heal_action=r["heal_action"],
                        healed=r["healed"],
                        ts=r.get("created_at", time.time()),
                    )
                    self._alerts.append(alert)
                except Exception:
                    pass
            print(f"[AlertStore] Loaded {len(self._alerts)} persistent alerts from SQLite database")
        except Exception as e:
            print(f"[AlertStore] Error loading alerts from DB: {e}")

    def add(self,
            slave_id: str,
            container_name: str,
            severity: str,
            root_cause: str,
            fix: str,
            auto_heal: bool,
            heal_action: str) -> Alert:
        alert = Alert(
            alert_id=str(uuid.uuid4())[:8],
            slave_id=slave_id,
            container_name=container_name,
            severity=severity,
            root_cause=root_cause,
            fix=fix,
            auto_heal=auto_heal,
            heal_action=heal_action,
        )
        self._alerts.appendleft(alert)
        
        # Persist asynchronously to SQLite
        try:
            loop = asyncio.get_running_loop()
            from database import db_save_alert
            loop.create_task(db_save_alert(alert.to_dict()))
        except RuntimeError:
            pass

        return alert

    def mark_healed(self, alert_id: str) -> bool:
        for alert in self._alerts:
            if alert.alert_id == alert_id:
                alert.healed = True
                try:
                    loop = asyncio.get_running_loop()
                    from database import db_mark_alert_healed
                    loop.create_task(db_mark_alert_healed(alert_id, time.time()))
                except RuntimeError:
                    pass
                return True
        return False

    def all(self, limit: int = 100) -> List[dict]:
        return [a.to_dict() for a in list(self._alerts)[:limit]]

    def by_severity(self, severity: str) -> List[dict]:
        return [a.to_dict() for a in self._alerts if a.severity == severity]

    def by_container(self, container_name: str) -> List[dict]:
        return [a.to_dict() for a in self._alerts if a.container_name == container_name]

    def unhealed(self) -> List[dict]:
        return [a.to_dict() for a in self._alerts
                if not a.healed and a.severity in ("error", "critical")]

    def counts(self) -> dict:
        alerts = list(self._alerts)
        return {
            "total": len(alerts),
            "critical": sum(1 for a in alerts if a.severity == "critical"),
            "error":    sum(1 for a in alerts if a.severity == "error"),
            "warn":     sum(1 for a in alerts if a.severity == "warn"),
            "ok":       sum(1 for a in alerts if a.severity == "ok"),
            "unhealed": sum(1 for a in alerts if not a.healed and a.severity in ("error", "critical")),
        }


# Global singleton
alert_store = AlertStore()
