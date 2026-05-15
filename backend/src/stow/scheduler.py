from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from sqlmodel import Session

from stow.db import engine
from stow.recurring import auto_post_pending, create_queue_entries_for_today

IST = ZoneInfo("Asia/Kolkata")
log = logging.getLogger(__name__)


async def _job_generate_recurring():
    try:
        with Session(engine) as session:
            create_queue_entries_for_today(session)
    except Exception:
        log.exception("Scheduler job 'generate_recurring' failed")


async def _job_auto_post():
    try:
        with Session(engine) as session:
            auto_post_pending(session)
    except Exception:
        log.exception("Scheduler job 'auto_post' failed")


async def _job_fetch_prices():
    try:
        from stow.investments.prices import PriceRepository
        with Session(engine) as session:
            await PriceRepository(session).fetch_all()
    except Exception:
        log.exception("Scheduler job 'fetch_prices' failed")


JOB_REGISTRY: dict[str, object] = {
    "generate_recurring": _job_generate_recurring,
    "auto_post": _job_auto_post,
    "fetch_prices_evening": _job_fetch_prices,
    "fetch_prices_morning": _job_fetch_prices,
}

SCHEDULES = [
    ("generate_recurring", _job_generate_recurring, CronTrigger(hour=0, minute=5, timezone=IST)),
    ("auto_post", _job_auto_post, CronTrigger(hour=0, minute=10, timezone=IST)),
    ("fetch_prices_evening", _job_fetch_prices, CronTrigger(hour=23, minute=50, timezone=IST)),
    ("fetch_prices_morning", _job_fetch_prices, CronTrigger(hour=9, minute=0, timezone=IST)),
]


async def register_schedules(scheduler) -> None:
    for job_id, fn, trigger in SCHEDULES:
        await scheduler.add_schedule(fn, trigger, id=job_id)


async def trigger_job(scheduler, job_id: str) -> bool:
    fn = JOB_REGISTRY.get(job_id)
    if fn is None:
        return False
    now_utc = datetime.now(timezone.utc)
    await scheduler.add_schedule(fn, DateTrigger(now_utc), id=f"{job_id}__manual__{uuid4()}")
    return True
