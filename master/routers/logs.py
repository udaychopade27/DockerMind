from fastapi import APIRouter, Query, Depends
from middleware.auth import get_current_user, require_role
import docker_ops
import llm_client

router = APIRouter(prefix="/logs", tags=["logs"])


@router.get("/{container_name}", summary="Get container logs (viewer+)")
async def get_logs(
    container_name: str,
    tail: int = Query(100, le=500),
    user: dict = Depends(get_current_user),
):
    logs = docker_ops.get_logs(container_name, tail=tail)
    return {"container": container_name, "logs": logs, "lines": logs.count("\n")}


@router.get("/{container_name}/analyze", summary="LLM log analysis (viewer+)")
async def analyze_logs(
    container_name: str,
    tail: int = Query(100, le=500),
    user: dict = Depends(require_role("viewer")),
):
    logs = docker_ops.get_logs(container_name, tail=tail)
    analysis = await llm_client.analyze_logs(container_name, logs)
    return {
        "container":  container_name,
        "analysis":   analysis,
        "log_lines":  logs.count("\n"),
    }