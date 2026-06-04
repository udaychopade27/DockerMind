import time
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from slave_registry import registry
from services.crash_detector import crash_detector
from services.heal_engine import heal_engine
from services.log_pipeline import log_pipeline

router = APIRouter(prefix="/slaves", tags=["slaves"])


# ── Request models ─────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    slave_id: str
    hostname: str
    ip: str
    port: int
    tags: list = []

class HeartbeatRequest(BaseModel):
    slave_id: str
    container_count: int = 0

class LogBatchRequest(BaseModel):
    slave_id: str
    container_id: str
    container_name: str
    logs: str
    ts: float = 0

class EventRequest(BaseModel):
    slave_id: str
    event_type: str           # start | stop | die | oom | kill
    container_name: str
    container_id: str = ""
    exit_code: int = 0
    detail: str = ""
    ts: float = 0


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/register")
async def register(req: RegisterRequest):
    node = await registry.register(
        slave_id=req.slave_id,
        hostname=req.hostname,
        ip=req.ip,
        port=req.port,
        tags=req.tags,
    )
    return {"status": "registered", "slave_id": req.slave_id}


@router.post("/heartbeat")
async def heartbeat(req: HeartbeatRequest):
    ok = await registry.heartbeat(req.slave_id, req.container_count)
    if not ok:
        raise HTTPException(404, "Slave not registered — call /slaves/register first")
    return {"status": "ok"}


@router.get("")
async def list_slaves():
    return {"slaves": registry.all(), "counts": registry.count()}


@router.delete("/{slave_id}")
async def deregister(slave_id: str):
    await registry.deregister(slave_id)
    return {"status": "removed"}


@router.post("/logs")
async def receive_logs(req: LogBatchRequest):
    """
    Slave pushes log batches here every 60s.
    We enqueue for async LLM analysis — never blocks the slave.
    """
    queued = await log_pipeline.push(
        slave_id=req.slave_id,
        container_id=req.container_id,
        container_name=req.container_name,
        logs=req.logs,
    )
    return {"status": "queued" if queued else "dropped", "slave_id": req.slave_id}


@router.post("/events")
async def receive_event(req: EventRequest):
    """
    Slave pushes container lifecycle events (die, oom, start) here immediately.
    We run crash detection and trigger auto-heal if needed.
    """
    result = {"event_type": req.event_type, "container": req.container_name}

    if req.event_type == "oom":
        analysis = await crash_detector.record_oom(req.slave_id, req.container_name)
        result["analysis"] = analysis
        # OOM always triggers immediate heal
        heal_result = await heal_engine.heal_container(
            container_name=req.container_name,
            slave_id=req.slave_id,
            action="restart",
        )
        result["heal_result"] = heal_result

    elif req.event_type == "die":
        analysis = await crash_detector.record_die(
            req.slave_id, req.container_name, req.exit_code
        )
        result["analysis"] = analysis

        if analysis["is_crash_loop"] or analysis["is_oom"]:
            heal_result = await heal_engine.heal_container(
                container_name=req.container_name,
                slave_id=req.slave_id,
                action=analysis["heal_action"],
            )
            result["heal_result"] = heal_result

    return result


@router.get("/crash-loops")
async def crash_loops():
    return {"crash_loops": crash_detector.summary()}


@router.get("/pipeline/stats")
async def pipeline_stats():
    return log_pipeline.stats()