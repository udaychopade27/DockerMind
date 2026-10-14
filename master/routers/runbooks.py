from typing import List

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from middleware.auth import get_current_user, require_role
from services.runbook import runbook_engine
from services.notifier import notifier

router = APIRouter(prefix="/runbooks", tags=["runbooks"])


class CreateRunbookRequest(BaseModel):
    name: str
    description: str = ""
    trigger: str = "manual"
    steps: List[dict]


class ExecuteRequest(BaseModel):
    slave_id: str = "local"
    container: str


@router.get("", summary="List all runbooks (viewer+)")
async def list_runbooks(user: dict = Depends(get_current_user)):
    books = await runbook_engine.list_runbooks()
    return {"runbooks": books, "count": len(books)}


@router.post("", summary="Create a runbook (admin only)")
async def create_runbook(
    req: CreateRunbookRequest,
    user: dict = Depends(require_role("admin")),
):
    rb_id = await runbook_engine.create_runbook(
        name=req.name,
        description=req.description,
        trigger=req.trigger,
        steps=req.steps,
    )
    return {"runbook_id": rb_id, "status": "created"}


@router.get("/{runbook_id}", summary="Get runbook details (viewer+)")
async def get_runbook(runbook_id: str, user: dict = Depends(get_current_user)):
    rb = await runbook_engine.get_runbook(runbook_id)
    if not rb:
        raise HTTPException(404, f"Runbook '{runbook_id}' not found")
    return rb


@router.post("/{runbook_id}/execute", summary="Execute a runbook (operator+)")
async def execute_runbook(
    runbook_id: str,
    req: ExecuteRequest,
    user: dict = Depends(require_role("operator")),
):
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
            "fix": "Review step results",
        })
    return result