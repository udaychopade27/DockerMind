from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime
import time


class ContainerEvent(BaseModel):
    slave_id: str
    container_id: str
    container_name: str
    event_type: Literal["start", "stop", "die", "kill", "oom", "crash_loop", "restart", "health_fail"]
    exit_code: Optional[int] = None
    detail: Optional[str] = None
    ts: float = Field(default_factory=time.time)

    @property
    def datetime(self) -> datetime:
        return datetime.fromtimestamp(self.ts)


class LogBatch(BaseModel):
    slave_id: str
    container_id: str
    container_name: str
    logs: str
    ts: float = Field(default_factory=time.time)


class Alert(BaseModel):
    alert_id: str
    slave_id: str
    container_name: str
    severity: Literal["ok", "warn", "error", "critical"]
    root_cause: str
    fix: str
    auto_heal: bool
    heal_action: str
    healed: bool = False
    ts: float = Field(default_factory=time.time)

    @property
    def datetime(self) -> datetime:
        return datetime.fromtimestamp(self.ts)

    def to_dict(self) -> dict:
        return {
            "alert_id": self.alert_id,
            "slave_id": self.slave_id,
            "container_name": self.container_name,
            "severity": self.severity,
            "root_cause": self.root_cause,
            "fix": self.fix,
            "auto_heal": self.auto_heal,
            "heal_action": self.heal_action,
            "healed": self.healed,
            "ts": self.ts,
            "datetime": self.datetime.isoformat(),
        }