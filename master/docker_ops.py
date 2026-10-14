import docker
import asyncio
from typing import List, Dict, Optional
from config import DOCKER_SOCKET


def get_client():
    return docker.DockerClient(base_url=DOCKER_SOCKET)


def list_containers(all_containers: bool = False, include_stats: bool = False) -> List[Dict]:
    """Return list of containers on THIS host (master's own docker). Fast non-blocking by default."""
    client = get_client()
    containers = client.containers.list(all=all_containers)
    result = []
    for c in containers:
        stats = {}
        if include_stats:
            try:
                raw = c.stats(stream=False)
                cpu_delta = raw["cpu_stats"]["cpu_usage"]["total_usage"] - \
                            raw["precpu_stats"]["cpu_usage"]["total_usage"]
                sys_delta  = raw["cpu_stats"]["system_cpu_usage"] - \
                             raw["precpu_stats"]["system_cpu_usage"]
                cpu_pct = (cpu_delta / sys_delta) * 100.0 if sys_delta > 0 else 0
                mem_used = raw["memory_stats"].get("usage", 0)
                mem_limit = raw["memory_stats"].get("limit", 1)
                stats = {
                    "cpu_pct": round(cpu_pct, 2),
                    "mem_used_mb": round(mem_used / 1024 / 1024, 1),
                    "mem_limit_mb": round(mem_limit / 1024 / 1024, 1),
                    "mem_pct": round((mem_used / mem_limit) * 100, 1),
                }
            except Exception:
                pass

        result.append({
            "id": c.short_id,
            "name": c.name,
            "image": c.image.tags[0] if c.image.tags else c.image.short_id,
            "status": c.status,
            "created": str(c.attrs.get("Created", ""))[:19],
            "ports": c.ports,
            "stats": stats,
        })
    return result


def get_logs(container_name: str, tail: int = 100) -> str:
    """Fetch last N lines of logs from a container."""
    client = get_client()
    try:
        container = client.containers.get(container_name)
        logs = container.logs(tail=tail, timestamps=True).decode("utf-8", errors="replace")
        return logs
    except docker.errors.NotFound:
        return f"Container '{container_name}' not found"
    except Exception as e:
        return f"Error fetching logs: {e}"


def restart_container(container_name: str) -> Dict:
    """Restart a container and return result."""
    client = get_client()
    try:
        container = client.containers.get(container_name)
        container.restart(timeout=10)
        return {"success": True, "message": f"Container '{container_name}' restarted successfully"}
    except docker.errors.NotFound:
        return {"success": False, "message": f"Container '{container_name}' not found"}
    except Exception as e:
        return {"success": False, "message": str(e)}


def stop_container(container_name: str) -> Dict:
    client = get_client()
    try:
        c = client.containers.get(container_name)
        c.stop(timeout=10)
        return {"success": True, "message": f"Container '{container_name}' stopped"}
    except Exception as e:
        return {"success": False, "message": str(e)}


def start_container(container_name: str) -> Dict:
    client = get_client()
    try:
        c = client.containers.get(container_name)
        c.start()
        return {"success": True, "message": f"Container '{container_name}' started"}
    except Exception as e:
        return {"success": False, "message": str(e)}


def exec_in_container(container_name: str, command: str) -> Dict:
    """Run a command inside a running container."""
    client = get_client()
    try:
        c = client.containers.get(container_name)
        exit_code, output = c.exec_run(command, stderr=True)
        return {
            "success": exit_code == 0,
            "exit_code": exit_code,
            "output": output.decode("utf-8", errors="replace") if output else "",
        }
    except Exception as e:
        return {"success": False, "exit_code": -1, "output": str(e)}


def inspect_container(container_name: str) -> Optional[Dict]:
    client = get_client()
    try:
        c = client.containers.get(container_name)
        return c.attrs
    except Exception:
        return None