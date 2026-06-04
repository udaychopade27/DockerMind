import time
from fastapi import APIRouter, HTTPException, Depends, Query, Header
from pydantic import BaseModel
from typing import Optional
from config import API_SECRET
from services.scheduler import scheduler
from services.job_dispatcher import job_dispatcher
from database import get_db, audit

router = APIRouter(prefix="/jobs", tags=["jobs"])


def verify(x_api_key: str = Header(...)):
    if x_api_key != API_SECRET:
        raise HTTPException(401, "Invalid API key")


class CreateJobRequest(BaseModel):
    name: str
    type: str                    # restart | stop | start | exec | log_check
    slave_id: str = "local"
    container: str = ""
    payload: dict = {}
    run_at: Optional[float] = None   # unix timestamp; None = run now


@router.post("")
async def create_job(req: CreateJobRequest, _=Depends(verify)):
    job_id = await scheduler.schedule(
        name=req.name,
        job_type=req.type,
        slave_id=req.slave_id,
        container=req.container,
        payload=req.payload,
        run_at=req.run_at,
    )
    # If run_at is now or past — dispatch immediately
    if not req.run_at or req.run_at <= time.time():
        job = await scheduler.get_job(job_id)
        if job:
            import asyncio
            asyncio.create_task(job_dispatcher.execute_job(job))

    await audit("job_created", target=job_id,
                slave_id=req.slave_id, container=req.container)
    return {"job_id": job_id, "status": "queued"}


@router.get("")
async def list_jobs(
    status: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    _=Depends(verify),
):
    jobs = await scheduler.list_jobs(status=status, limit=limit)
    return {"jobs": jobs, "count": len(jobs)}


@router.get("/{job_id}")
async def get_job(job_id: str, _=Depends(verify)):
    job = await scheduler.get_job(job_id)
    if not job:
        raise HTTPException(404, f"Job '{job_id}' not found")
    return job


@router.delete("/{job_id}")
async def cancel_job(job_id: str, _=Depends(verify)):
    ok = await scheduler.cancel_job(job_id)
    if not ok:
        raise HTTPException(400, "Job not found or already running/done")
    return {"status": "cancelled", "job_id": job_id}


@router.get("/audit/log")
async def audit_log(
    limit: int = Query(50, le=200),
    container: Optional[str] = Query(None),
    _=Depends(verify),
):
    async with await get_db() as db:
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