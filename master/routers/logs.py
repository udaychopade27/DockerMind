from fastapi import APIRouter, Query, Depends
from fastapi.security import APIKeyHeader
from fastapi import HTTPException
import docker_ops
import llm_client
from config import API_SECRET

router = APIRouter(prefix="/logs", tags=["logs"])

api_key_header = APIKeyHeader(name="X-Api-Key", auto_error=False)

def verify(key: str = Depends(api_key_header)):
    if key != API_SECRET:
        raise HTTPException(401, "Invalid API key")


@router.get("/{container_name}")
async def get_logs(
    container_name: str,
    tail: int = Query(100, le=500),
    _=Depends(verify),
):
    logs = docker_ops.get_logs(container_name, tail=tail)
    return {"container": container_name, "logs": logs, "lines": logs.count("\n")}


@router.get("/{container_name}/analyze")
async def analyze_logs(
    container_name: str,
    tail: int = Query(100, le=500),
    _=Depends(verify),
):
    logs = docker_ops.get_logs(container_name, tail=tail)
    analysis = await llm_client.analyze_logs(container_name, logs)
    return {
        "container": container_name,
        "analysis": analysis,
        "log_lines": logs.count("\n"),
    }