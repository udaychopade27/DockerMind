import time
from typing import List, Optional, Union
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from middleware.auth import get_current_user, require_role
from slave_registry import registry
from services.crash_detector import crash_detector
from services.heal_engine import heal_engine
from services.log_pipeline import log_pipeline
from services.job_dispatcher import job_dispatcher
from services.notifier import notifier
from models.alerts import alert_store
from database import audit

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
    event_type: str
    container_name: str
    container_id: str = ""
    exit_code: int = 0
    detail: str = ""
    ts: float = 0

class MultiDispatchRequest(BaseModel):
    action: str                               # restart | stop | start | exec | log_check
    container: str                            # container name
    targets: Union[List[str], str] = "all"    # "all", or ["slave-local", "slave-1"]
    tags: Optional[List[str]] = None          # e.g. ["prod"]
    payload: Optional[dict] = {}              # e.g. {"command": "ps aux"}

class CircuitBreakerResetRequest(BaseModel):
    slave_id: str = "local"
    container_name: str


# ── Public endpoints — slave agents call these, no auth required ──────────────

@router.post("/register", summary="Slave self-registration (public)")
async def register(req: RegisterRequest):
    await registry.register(
        slave_id=req.slave_id,
        hostname=req.hostname,
        ip=req.ip,
        port=req.port,
        tags=req.tags,
    )
    return {"status": "registered", "slave_id": req.slave_id}


@router.post("/heartbeat", summary="Slave heartbeat (public)")
async def heartbeat(req: HeartbeatRequest):
    ok = await registry.heartbeat(req.slave_id, req.container_count)
    if not ok:
        raise HTTPException(404, "Slave not registered — call /slaves/register first")
    return {"status": "ok"}


@router.post("/logs", summary="Slave log ingestion (public)")
async def receive_logs(req: LogBatchRequest):
    queued = await log_pipeline.push(
        slave_id=req.slave_id,
        container_id=req.container_id,
        container_name=req.container_name,
        logs=req.logs,
    )
    return {"status": "queued" if queued else "dropped", "container": req.container_name}


@router.post("/events", summary="Slave event ingestion (public)")
async def receive_event(req: EventRequest):
    result = {
        "event_type": req.event_type,
        "container": req.container_name,
        "slave_id": req.slave_id,
        "exit_code": req.exit_code,
    }

    # Case 1: OOM Kill Event
    if req.event_type == "oom" or req.exit_code == 137:
        analysis = await crash_detector.record_oom(req.slave_id, req.container_name)
        result["analysis"] = analysis

        # Store explicit OOM alert
        alert = alert_store.add(
            slave_id=req.slave_id,
            container_name=req.container_name,
            severity="critical",
            root_cause=f"Container killed by OOM killer (exit 137). Memory limit exceeded.",
            fix="Increase container memory limit or fix memory leak in application",
            auto_heal=True,
            heal_action="restart",
        )
        await notifier.notify_alert(alert.to_dict())
        await audit("oom_kill", target=req.container_name, slave_id=req.slave_id, result=analysis)

        # Trigger auto-heal with backoff
        heal_result = await heal_engine.heal_container(
            container_name=req.container_name,
            slave_id=req.slave_id,
            action="restart",
            reason="OOM kill detected — memory limit exceeded",
        )
        result["heal_result"] = heal_result

    # Case 2: Container Die Event
    elif req.event_type == "die":
        analysis = await crash_detector.record_die(
            req.slave_id, req.container_name, req.exit_code
        )
        result["analysis"] = analysis

        # Only trigger heal if not a clean exit (code 0)
        if req.exit_code != 0 or analysis.get("is_crash_loop"):
            heal_result = await heal_engine.heal_container(
                container_name=req.container_name,
                slave_id=req.slave_id,
                action=analysis["heal_action"],
                reason=analysis["root_cause"],
            )
            result["heal_result"] = heal_result

            # Send notification on crash or crash loop
            if analysis.get("severity") in ("error", "critical"):
                alert = alert_store.add(
                    slave_id=req.slave_id,
                    container_name=req.container_name,
                    severity=analysis["severity"],
                    root_cause=analysis["root_cause"],
                    fix="Inspect application logs / entrypoint" if not analysis["is_crash_loop"] else "Break crash-loop; check image and configuration",
                    auto_heal=True,
                    heal_action=analysis["heal_action"],
                )
                await notifier.notify_alert(alert.to_dict())
                await audit("container_die", target=req.container_name, slave_id=req.slave_id, result=analysis)

    # Case 3: High Memory / Health Check Warning
    elif req.event_type == "health_fail":
        is_mem = "memory" in req.detail.lower()
        alert = alert_store.add(
            slave_id=req.slave_id,
            container_name=req.container_name,
            severity="warn" if is_mem else "error",
            root_cause=req.detail or "Container resource threshold exceeded",
            fix="Inspect container memory allocation" if is_mem else "Investigate container health",
            auto_heal=False,
            heal_action="none",
        )
        result["alert"] = alert.to_dict()
        await notifier.notify_alert(alert.to_dict())
        await audit("health_warning", target=req.container_name, slave_id=req.slave_id, result={"detail": req.detail})

    return result


# ── Protected endpoints — require JWT ─────────────────────────────────────────

@router.get("", summary="List all slave nodes (viewer+)")
async def list_slaves(user: dict = Depends(get_current_user)):
    from services.host_metrics import get_master_host_stats
    return {
        "slaves": registry.all(),
        "counts": registry.count(),
        "master_host_stats": get_master_host_stats(),
    }


@router.delete("/{slave_id}", summary="Remove a slave (admin only)")
async def deregister(
    slave_id: str,
    user: dict = Depends(require_role("admin")),
):
    await registry.deregister(slave_id)
    return {"status": "removed"}


@router.get("/crash-loops", summary="Active crash loops (viewer+)")
async def crash_loops(user: dict = Depends(get_current_user)):
    return {"crash_loops": crash_detector.summary()}


@router.get("/pipeline/stats", summary="Log pipeline stats (viewer+)")
async def pipeline_stats(user: dict = Depends(get_current_user)):
    return log_pipeline.stats()


@router.post("/dispatch", summary="Dispatch command across multiple slaves (operator+)")
async def dispatch_fleet(
    req: MultiDispatchRequest,
    user: dict = Depends(require_role("operator")),
):
    """
    Dispatch command to multiple or all slave nodes simultaneously.
    """
    result = await job_dispatcher.dispatch_multi(
        action=req.action,
        container=req.container,
        targets=req.targets,
        tags=req.tags,
        payload=req.payload,
        user=user.get("sub", "operator"),
    )
    return result


@router.post("/circuit-breaker/reset", summary="Reset circuit breaker for a container (operator+)")
async def reset_circuit_breaker(
    req: CircuitBreakerResetRequest,
    user: dict = Depends(require_role("operator")),
):
    """
    Clears backoff delay and circuit breaker block for a container.
    """
    heal_engine.reset_backoff(req.slave_id, req.container_name)
    crash_detector.reset(req.slave_id, req.container_name)
    for a in alert_store.unhealed():
        if a.get("container_name") == req.container_name:
            alert_store.mark_healed(a.get("alert_id"))
    await audit("circuit_breaker_reset", target=req.container_name, slave_id=req.slave_id, user=user.get("sub"))
    return {"status": "reset", "slave_id": req.slave_id, "container": req.container_name}
