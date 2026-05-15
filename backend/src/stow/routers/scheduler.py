from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from stow.scheduler import JOB_REGISTRY, trigger_job

router = APIRouter(prefix="/scheduler", tags=["scheduler"])


def _get_scheduler(request: Request):
    return request.app.state.scheduler


class JobOut(BaseModel):
    id: str
    next_fire_time: str | None
    paused: bool


@router.get("/jobs", response_model=list[JobOut])
async def list_jobs(scheduler=Depends(_get_scheduler)):
    schedules = await scheduler.get_schedules()
    return [
        JobOut(
            id=s.id,
            next_fire_time=s.next_fire_time.isoformat() if s.next_fire_time else None,
            paused=s.paused,
        )
        for s in schedules
    ]


@router.post("/jobs/{job_id}/trigger", status_code=204)
async def trigger_job_endpoint(job_id: str, scheduler=Depends(_get_scheduler)):
    if job_id not in JOB_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Unknown job: {job_id!r}")
    await trigger_job(scheduler, job_id)
    return Response(status_code=204)
