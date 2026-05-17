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


def _build_digest_text(items: list) -> str:
    """Build a plain-text recurring digest for Telegram."""
    lines = ["📋 *Today's recurring transactions:*\n"]
    for i, item in enumerate(items, 1):
        amount_inr = item.amount_paise / 100
        # Format with Indian comma style
        amount_str = f"₹{amount_inr:,.2f}".replace(",", "X").replace(".", ".").replace("X", ",")
        lines.append(
            f"{i}. {item.narration} — {amount_str}\n"
            f"   From: {item.from_account_name} → {item.to_account_name}\n"
        )
    lines.append('\nReply "/recurring" to confirm or skip each item.')
    return "\n".join(lines)


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


async def _job_recurring_digest():
    """Send a Telegram DM digest of today's pending recurring transactions at 08:00 IST."""
    try:
        from datetime import date
        from sqlmodel import select
        from stow.models import Account, Entry, RecurringQueueItem, RecurringSchedule, TelegramUser, Transaction

        with Session(engine) as session:
            today = date.today()
            items = session.exec(
                select(RecurringQueueItem)
                .where(RecurringQueueItem.due_date == today)
                .where(RecurringQueueItem.status == "pending")
            ).all()
            if not items:
                return

            # Enrich each item with template transaction details
            class _Item:
                pass

            enriched = []
            for item in items:
                schedule = session.get(RecurringSchedule, item.schedule_id)
                txn = session.get(Transaction, schedule.template_transaction_id)
                entries = session.exec(
                    select(Entry).where(Entry.transaction_id == schedule.template_transaction_id)
                ).all()
                credit = next((e for e in entries if e.amount < 0), None)
                debit = next((e for e in entries if e.amount > 0), None)
                from_acc = session.get(Account, credit.account_id) if credit else None
                to_acc = session.get(Account, debit.account_id) if debit else None

                obj = _Item()
                obj.narration = txn.narration if txn else "Recurring"  # type: ignore[attr-defined]
                obj.amount_paise = abs(credit.amount) if credit else 0  # type: ignore[attr-defined]
                obj.from_account_name = from_acc.name if from_acc else ""  # type: ignore[attr-defined]
                obj.to_account_name = to_acc.name if to_acc else ""  # type: ignore[attr-defined]
                enriched.append(obj)

            text = _build_digest_text(enriched)
            telegram_users = session.exec(select(TelegramUser)).all()

        from agent.transport.telegram.bot import get_bot
        bot = get_bot()
        if bot is None:
            log.info("Recurring digest: Telegram bot not running, skipping push")
            return

        for user in telegram_users:
            try:
                await bot.send_message(chat_id=user.telegram_user_id, text=text, parse_mode="Markdown")
            except Exception:
                log.exception("Failed to send digest to telegram_user_id=%s", user.telegram_user_id)

    except Exception:
        log.exception("Scheduler job 'recurring_digest' failed")


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
    "recurring_digest": _job_recurring_digest,
    "fetch_prices_evening": _job_fetch_prices,
    "fetch_prices_morning": _job_fetch_prices,
}

SCHEDULES = [
    ("generate_recurring", _job_generate_recurring, CronTrigger(hour=0, minute=5, timezone=IST)),
    ("auto_post", _job_auto_post, CronTrigger(hour=0, minute=10, timezone=IST)),
    ("recurring_digest", _job_recurring_digest, CronTrigger(hour=8, minute=0, timezone=IST)),
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
