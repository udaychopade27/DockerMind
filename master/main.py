import asyncio
import time
from contextlib import asynccontextmanager
from typing import List

import uvicorn
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

import docker_ops
import llm_client
from config import MASTER_HOST, MASTER_PORT, API_SECRET
from slave_registry import registry
from database import init_db, audit
from services.log_pipeline import log_pipeline
from services.heal_engine import heal_engine
from services.scheduler import scheduler
from services.job_dispatcher import job_dispatcher
from services.runbook import runbook_engine
from services.notifier import notifier
from middleware.auth import RBACMiddleware
from routers import slaves as slaves_router
from routers import alerts as alerts_router
from routers import logs as logs_router
from routers import jobs as jobs_router
from routers import runbooks as runbooks_router


# ── WebSocket manager ─────────────────────────────────────────────────────────
class ConnectionManager:
    def __init__(self):
        self.active: List[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)

    async def broadcast(self, message: dict):
        dead = []
        for ws in self.active:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


ws_manager = ConnectionManager()


# ── Background tasks ──────────────────────────────────────────────────────────
async def slave_monitor():
    while True:
        await asyncio.sleep(10)
        await ws_manager.broadcast({
            "event": "slave_status",
            "data": registry.all(),
            "ts": time.time(),
        })


# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("=== DockerMind Master v0.3.0 starting ===")
    await init_db()
    await runbook_engine.seed_builtins()
    llm_ok = await llm_client.check_ollama_health()
    print(f"[LLM] Ollama reachable: {llm_ok} — model: {llm_client.LLM_MODEL}")
    if llm_ok:
        asyncio.create_task(llm_client.ensure_model_loaded())
    log_pipeline.set_broadcast(ws_manager.broadcast)
    asyncio.create_task(log_pipeline.run())
    asyncio.create_task(slave_monitor())
    asyncio.create_task(scheduler.run(job_dispatcher))
    yield
    print("=== DockerMind Master shutting down ===")


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="DockerMind Master",
    version="0.3.0",
    description="AI-powered DevOps agent — master node",
    lifespan=lifespan,
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.add_middleware(RBACMiddleware)

app.include_router(slaves_router.router)
app.include_router(alerts_router.router)
app.include_router(logs_router.router)
app.include_router(jobs_router.router)
app.include_router(runbooks_router.router)


# ── Request models ────────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    message: str
    context: str = ""

class HealRequest(BaseModel):
    container_name: str
    slave_id: str = "local"
    action: Optional[str] = None

class ExecRequest(BaseModel):
    container_name: str
    command: str
    slave_id: str = "local"

class StatsRequest(BaseModel):
    slave_id: str
    stats: list
    ts: float = 0


# ── Core routes ───────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    llm_ok = await llm_client.check_ollama_health()
    return {
        "status": "ok",
        "version": "0.3.0",
        "llm": "ready" if llm_ok else "unavailable",
        "llm_model": llm_client.LLM_MODEL,
        "slaves": registry.count(),
        "pipeline": log_pipeline.stats(),
        "ts": time.time(),
    }


@app.post("/chat")
async def chat(req: ChatRequest):
    try:
        reply = await llm_client.chat(req.message, context=req.context)
        await audit("chat", result={"message": req.message[:100]})
        return {"reply": reply, "model": llm_client.LLM_MODEL}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM error: {e}")


@app.get("/containers")
async def list_containers():
    return {"containers": docker_ops.list_containers(all_containers=True), "host": "master"}


@app.post("/containers/{name}/restart")
async def restart(name: str):
    result = docker_ops.restart_container(name)
    await audit("restart", container=name, result=result)
    await ws_manager.broadcast({"event": "container_restarted", "container": name, "result": result})
    return result


@app.post("/containers/{name}/start")
async def start(name: str):
    result = docker_ops.start_container(name)
    await audit("start", container=name, result=result)
    return result


@app.post("/containers/{name}/stop")
async def stop(name: str):
    result = docker_ops.stop_container(name)
    await audit("stop", container=name, result=result)
    return result


@app.post("/containers/exec")
async def exec_cmd(req: ExecRequest):
    result = docker_ops.exec_in_container(req.container_name, req.command)
    await audit("exec", container=req.container_name, result={"cmd": req.command})
    return result


@app.post("/heal")
async def auto_heal(req: HealRequest):
    result = await heal_engine.heal_container(
        container_name=req.container_name,
        slave_id=req.slave_id,
        action=req.action,
    )
    await ws_manager.broadcast({"event": "auto_heal", "result": result, "ts": time.time()})
    await audit("heal", container=req.container_name, slave_id=req.slave_id, result=result)
    if not result.get("success") and not result.get("skipped"):
        await notifier.notify_heal(req.container_name, req.slave_id,
                                   req.action or "auto", False)
    return result


@app.post("/slaves/stats")
async def receive_stats(req: StatsRequest):
    await ws_manager.broadcast({
        "event": "stats_update",
        "slave_id": req.slave_id,
        "stats": req.stats,
        "ts": req.ts,
    })
    return {"status": "ok"}


# ── WebSocket ─────────────────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws_manager.connect(ws)
    try:
        await ws.send_json({
            "event": "init",
            "slaves": registry.all(),
            "containers": docker_ops.list_containers(all_containers=True),
            "ts": time.time(),
        })
        while True:
            data = await ws.receive_text()
            if data == "ping":
                await ws.send_json({"event": "pong", "ts": time.time()})
    except WebSocketDisconnect:
        ws_manager.disconnect(ws)


if __name__ == "__main__":
    uvicorn.run("main:app", host=MASTER_HOST, port=MASTER_PORT, reload=False, log_level="info")