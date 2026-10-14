import asyncio
import time
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel

from middleware.auth import get_current_user, require_role
from services.scheduler import scheduler
from services.job_dispatcher import job_dispatcher
from database import get_db, audit

router = APIRouter(prefix="/jobs", tags=["jobs"])


class CreateJobRequest(BaseModel):
    name: str
    type: str              # restart | stop | start | exec | log_check
    slave_id: str = "local"
    container: str = ""
    payload: dict = {}
    run_at: Optional[float] = None   # unix timestamp; None = run immediately


@router.post("", summary="Schedule a job (operator+)")
async def create_job(
    req: CreateJobRequest,
    user: dict = Depends(require_role("operator")),
):
    job_id = await scheduler.schedule(
        name=req.name,
        job_type=req.type,
        slave_id=req.slave_id,
        container=req.container,
        payload=req.payload,
        run_at=req.run_at,
    )
    if not req.run_at or req.run_at <= time.time():
        job = await scheduler.get_job(job_id)
        if job:
            asyncio.create_task(job_dispatcher.execute_job(job))

    await audit("job_created", target=job_id, slave_id=req.slave_id,
                container=req.container, user=user.get("sub"))
    return {"job_id": job_id, "status": "queued"}


@router.get("", summary="List jobs (viewer+)")
async def list_jobs(
    status: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    user: dict = Depends(get_current_user),
):
    jobs = await scheduler.list_jobs(status=status, limit=limit)
    return {"jobs": jobs, "count": len(jobs)}


@router.get("/audit/log", summary="View audit log (viewer+)")
async def audit_log(
    limit: int = Query(50, le=200),
    container: Optional[str] = Query(None),
    user: dict = Depends(require_role("viewer")),
):
    async with get_db() as db:
        if container:
            async with db.execute(
                "SELECT * FROM audit_log WHERE container=? ORDER BY ts DESC LIMIT ?",
                (container, limit)
            ) as cur:
                rows = await cur.fetchall()
        else:
            async with db.execute(
                "SELECT * FROM audit_log ORDER BY ts DESC LIMIT ?", (limit,)
            ) as cur:
                rows = await cur.fetchall()
    return {"audit_log": [dict(r) for r in rows]}


@router.get("/{job_id}", summary="Get job details (viewer+)")
async def get_job(job_id: str, user: dict = Depends(get_current_user)):
    job = await scheduler.get_job(job_id)
    if not job:
        raise HTTPException(404, f"Job '{job_id}' not found")
    return job


@router.delete("/{job_id}", summary="Cancel a pending job (operator+)")
async def cancel_job(
    job_id: str,
    user: dict = Depends(require_role("operator")),
):
    ok = await scheduler.cancel_job(job_id)
    if not ok:
        raise HTTPException(400, "Job not found or already running/completed")
    return {"status": "cancelled", "job_id": job_id}