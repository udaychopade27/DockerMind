from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel
from typing import List
from config import API_SECRET
from services.runbook import runbook_engine
from services.notifier import notifier

router = APIRouter(prefix="/runbooks", tags=["runbooks"])


def verify(x_api_key: str = Header(...)):
    if x_api_key != API_SECRET:
        raise HTTPException(401, "Invalid API key")


class CreateRunbookRequest(BaseModel):
    name: str
    description: str = ""
    trigger: str = "manual"      # manual | crash_loop | oom | alert
    steps: List[dict]            # [{type, description, command?}, ...]


class ExecuteRequest(BaseModel):
    slave_id: str = "local"
    container: str


@router.get("")
async def list_runbooks(_=Depends(verify)):
    books = await runbook_engine.list_runbooks()
    return {"runbooks": books, "count": len(books)}


@router.post("")
async def create_runbook(req: CreateRunbookRequest, _=Depends(verify)):
    rb_id = await runbook_engine.create_runbook(
        name=req.name,
        description=req.description,
        trigger=req.trigger,
        steps=req.steps,
    )
    return {"runbook_id": rb_id, "status": "created"}


@router.get("/{runbook_id}")
async def get_runbook(runbook_id: str, _=Depends(verify)):
    rb = await runbook_engine.get_runbook(runbook_id)
    if not rb:
        raise HTTPException(404, f"Runbook '{runbook_id}' not found")
    return rb


@router.post("/{runbook_id}/execute")
async def execute_runbook(runbook_id: str, req: ExecuteRequest, _=Depends(verify)):
    result = await runbook_engine.execute_runbook(
        runbook_id=runbook_id,
        slave_id=req.slave_id,
        container=req.container,
    )
    if not result.get("success"):
        await notifier.notify_alert({
            "severity": "error",
            "container_name": req.container,
            "slave_id": req.slave_id,
            "root_cause": f"Runbook '{runbook_id}' completed with failures",
            "fix": "Review step results below",
        })
    return result