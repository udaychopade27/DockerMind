import asyncio
import time
from contextlib import asynccontextmanager
from typing import List, Optional

import uvicorn
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel

import docker_ops
import llm_client
from config import MASTER_HOST, MASTER_PORT
from slave_registry import registry
from database import init_db, audit
from services.log_pipeline import log_pipeline
from services.heal_engine import heal_engine
from services.crash_detector import crash_detector
from models.alerts import alert_store
from services.scheduler import scheduler
from services.job_dispatcher import job_dispatcher
from services.runbook import runbook_engine
from services.notifier import notifier
from middleware.auth import JWTMiddleware, get_current_user, require_role
from routers import slaves as slaves_router
from routers import alerts as alerts_router
from routers import logs as logs_router
from routers import jobs as jobs_router
from routers import runbooks as runbooks_router
from routers import auth as auth_router


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
            "data":  registry.all(),
            "ts":    time.time(),
        })


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("=== DockerMind Master v0.3.0 starting ===")
    await init_db()
    await runbook_engine.seed_builtins()
    llm_ok = await llm_client.check_ollama_health()
    print(f"[LLM] provider={llm_client.LLM_PROVIDER}  reachable={llm_ok}  model=gemini:{llm_client.GEMINI_MODEL} | openrouter:{llm_client.OPENROUTER_MODEL} | ollama:{llm_client.LLM_MODEL}")
    if llm_ok:
        asyncio.create_task(llm_client.ensure_model_loaded())
    log_pipeline.set_broadcast(ws_manager.broadcast)
    asyncio.create_task(log_pipeline.run())
    asyncio.create_task(slave_monitor())
    asyncio.create_task(scheduler.run(job_dispatcher))
    yield
    print("=== DockerMind Master shutting down ===")


# ── App — Swagger configured with OAuth2 Bearer ───────────────────────────────
# The securitySchemes block makes Swagger show an "Authorize" button.
# Users log in via POST /auth/login, paste the access_token, and every
# subsequent "Try it out" call sends "Authorization: Bearer <token>" automatically.

app = FastAPI(
    title="DockerMind Master",
    version="0.3.0",
    description="""
AI-powered DevOps agent — master node.

## Authentication
1. Call **POST /auth/login** with your username + password
2. Copy the `access_token` from the response
3. Click **Authorize** (top right) and paste the token — all endpoints will use it automatically
    """,
    lifespan=lifespan,
    swagger_ui_oauth2_redirect_url="/docs/oauth2-redirect",
    swagger_ui_init_oauth={"usePkceWithAuthorizationCodeGrant": False},
)

# JWT middleware — runs before every request
app.add_middleware(JWTMiddleware)

# CORS — wrap outside JWT so OPTIONS preflights are handled immediately
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_origin_regex=r"https?://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Routers
app.include_router(auth_router.router)
app.include_router(slaves_router.router)
app.include_router(alerts_router.router)
app.include_router(logs_router.router)
app.include_router(jobs_router.router)
app.include_router(runbooks_router.router)


# ── Request / response models ─────────────────────────────────────────────────

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

@app.get("/health", tags=["system"], summary="Health check (public)")
async def health():
    llm_ok = await llm_client.check_ollama_health()
    provider = llm_client.LLM_PROVIDER
    active_model = {
        "local":       llm_client.LLM_MODEL,
        "gemini":      llm_client.GEMINI_MODEL,
        "openrouter":  llm_client.OPENROUTER_MODEL,
        "online":      f"{llm_client.GEMINI_MODEL} → {llm_client.OPENROUTER_MODEL}",
    }.get(provider, provider)
    return {
        "status":    "ok",
        "version":   "0.3.0",
        "llm":       "ready" if llm_ok else "unavailable",
        "llm_provider": provider,
        "llm_model": active_model,
        "slaves":    registry.count(),
        "pipeline":  log_pipeline.stats(),
        "ts":        time.time(),
    }


@app.post("/chat", tags=["ai"], summary="Chat with LLM (viewer+)")
async def chat(req: ChatRequest, user: dict = Depends(get_current_user)):
    try:
        reply = await llm_client.chat(req.message, context=req.context)
        await audit("chat", user=user.get("sub"), result={"msg": req.message[:80]})
        return {"reply": reply, "provider": llm_client.LLM_PROVIDER}
    except Exception as e:
        raise HTTPException(502, f"LLM error: {e}")


@app.get("/containers", tags=["containers"], summary="List containers on master host (viewer+)")
async def list_containers(user: dict = Depends(get_current_user)):
    return {"containers": docker_ops.list_containers(all_containers=True), "host": "master"}


@app.get("/containers/{name}/logs", tags=["containers"], summary="Get container logs (viewer+)")
async def container_logs(name: str, tail: int = 100, user: dict = Depends(get_current_user)):
    logs = docker_ops.get_logs(name, tail=tail)
    return {"container": name, "logs": logs, "lines": logs.count("\n")}


@app.post("/containers/{name}/restart", tags=["containers"], summary="Restart container (operator+)")
async def restart(name: str, user: dict = Depends(require_role("operator"))):
    result = docker_ops.restart_container(name)
    # Clear crash detector state and backoffs upon successful restart
    crash_detector.reset("local", name)
    crash_detector.reset("slave-local", name)
    heal_engine.reset_backoff("local", name)
    heal_engine.reset_backoff("slave-local", name)
    for a in alert_store.unhealed():
        if a.get("container_name") == name:
            alert_store.mark_healed(a.get("alert_id"))
    await audit("restart", container=name, user=user.get("sub"), result=result)
    await ws_manager.broadcast({"event": "container_restarted", "container": name, "result": result})
    return result


@app.post("/containers/{name}/start", tags=["containers"], summary="Start container (operator+)")
async def start(name: str, user: dict = Depends(require_role("operator"))):
    result = docker_ops.start_container(name)
    await audit("start", container=name, user=user.get("sub"), result=result)
    return result


@app.post("/containers/{name}/stop", tags=["containers"], summary="Stop container (operator+)")
async def stop(name: str, user: dict = Depends(require_role("operator"))):
    result = docker_ops.stop_container(name)
    await audit("stop", container=name, user=user.get("sub"), result=result)
    return result


@app.post("/containers/exec", tags=["containers"], summary="Exec command in container (admin only)")
async def exec_cmd(req: ExecRequest, user: dict = Depends(require_role("admin"))):
    result = docker_ops.exec_in_container(req.container_name, req.command)
    await audit("exec", container=req.container_name, user=user.get("sub"),
                result={"cmd": req.command})
    return result


@app.post("/heal", tags=["ai"], summary="Auto-heal container (operator+)")
async def auto_heal(req: HealRequest, user: dict = Depends(require_role("operator"))):
    result = await heal_engine.heal_container(
        container_name=req.container_name,
        slave_id=req.slave_id,
        action=req.action,
    )
    await ws_manager.broadcast({"event": "auto_heal", "result": result, "ts": time.time()})
    await audit("heal", container=req.container_name, slave_id=req.slave_id,
                user=user.get("sub"), result=result)
    if not result.get("success") and not result.get("skipped"):
        await notifier.notify_heal(req.container_name, req.slave_id,
                                   req.action or "auto", False)
    return result


# Called by slave health_reporter — public (no auth, internal traffic only)
@app.post("/slaves/stats", tags=["slaves"], include_in_schema=False)
async def receive_stats(req: StatsRequest):
    await ws_manager.broadcast({
        "event":    "stats_update",
        "slave_id": req.slave_id,
        "stats":    req.stats,
        "ts":       req.ts,
    })
    return {"status": "ok"}


# ── WebSocket — live dashboard feed ──────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws_manager.connect(ws)
    try:
        await ws.send_json({
            "event":      "init",
            "slaves":     registry.all(),
            "containers": docker_ops.list_containers(all_containers=True),
            "ts":         time.time(),
        })
        while True:
            data = await ws.receive_text()
            if data == "ping":
                await ws.send_json({"event": "pong", "ts": time.time()})
    except WebSocketDisconnect:
        ws_manager.disconnect(ws)


if __name__ == "__main__":
    uvicorn.run("main:app", host=MASTER_HOST, port=MASTER_PORT, reload=False, log_level="info")