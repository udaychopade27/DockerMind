import time
import asyncio
from typing import Dict, Optional
from dataclasses import dataclass, field
from config import SLAVE_TIMEOUT_SECS


@dataclass
class SlaveNode:
    slave_id: str
    hostname: str
    ip: str
    port: int
    registered_at: float = field(default_factory=time.time)
    last_heartbeat: float = field(default_factory=time.time)
    container_count: int = 0
    tags: list = field(default_factory=list)

    @property
    def is_online(self) -> bool:
        return (time.time() - self.last_heartbeat) < SLAVE_TIMEOUT_SECS

    @property
    def status(self) -> str:
        return "online" if self.is_online else "offline"

    def to_dict(self) -> dict:
        return {
            "slave_id": self.slave_id,
            "hostname": self.hostname,
            "ip": self.ip,
            "port": self.port,
            "status": self.status,
            "container_count": self.container_count,
            "registered_at": self.registered_at,
            "last_heartbeat": self.last_heartbeat,
            "tags": self.tags,
            "seconds_since_ping": round(time.time() - self.last_heartbeat, 1),
        }


class SlaveRegistry:
    def __init__(self):
        self._slaves: Dict[str, SlaveNode] = {}
        self._lock = asyncio.Lock()

    async def register(self, slave_id: str, hostname: str, ip: str, port: int, tags: list = None) -> SlaveNode:
        async with self._lock:
            node = SlaveNode(
                slave_id=slave_id,
                hostname=hostname,
                ip=ip,
                port=port,
                tags=tags or [],
            )
            self._slaves[slave_id] = node
            print(f"[Registry] Slave registered: {slave_id} @ {ip}:{port} ({hostname})")
            return node

    async def heartbeat(self, slave_id: str, container_count: int = 0) -> bool:
        async with self._lock:
            if slave_id not in self._slaves:
                return False
            self._slaves[slave_id].last_heartbeat = time.time()
            self._slaves[slave_id].container_count = container_count
            return True

    async def deregister(self, slave_id: str):
        async with self._lock:
            if slave_id in self._slaves:
                del self._slaves[slave_id]
                print(f"[Registry] Slave deregistered: {slave_id}")

    def get(self, slave_id: str) -> Optional[SlaveNode]:
        return self._slaves.get(slave_id)

    def all(self) -> list:
        return [s.to_dict() for s in self._slaves.values()]

    def online(self) -> list:
        return [s.to_dict() for s in self._slaves.values() if s.is_online]

    def count(self) -> dict:
        total = len(self._slaves)
        online = sum(1 for s in self._slaves.values() if s.is_online)
        return {"total": total, "online": online, "offline": total - online}


# Global singleton
registry = SlaveRegistry()