from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta

from sqlmodel import Session, col, select

from stow.fy_resolution import find_fy_for_date
from stow.models import (
    Entry, RecurringQueueItem, RecurringSchedule, Transaction,
)
from stow.transaction_numbers import next_transaction_number


def _advance_next_due_date(schedule: RecurringSchedule) -> date:
    d = schedule.next_due_date
    if schedule.frequency == "daily":
        return d + timedelta(days=1)
    if schedule.frequency == "weekly":
        return d + timedelta(weeks=1)
    if schedule.frequency == "yearly":
        return d.replace(year=d.year + 1)
    # monthly
    month = d.month + 1 if d.month < 12 else 1
    year = d.year + 1 if d.month == 12 else d.year
    target_day = schedule.day_of_period or d.day
    last_day = monthrange(year, month)[1]
    return date(year, month, min(target_day, last_day))


def create_queue_entries_for_today(session: Session, today: date | None = None) -> list[RecurringQueueItem]:
    today = today or date.today()
    schedules = session.exec(
        select(RecurringSchedule)
        .where(RecurringSchedule.is_active == True)  # noqa: E712
        .where(RecurringSchedule.next_due_date <= today)
        .where(
            (RecurringSchedule.end_date == None) |  # noqa: E711
            (RecurringSchedule.end_date >= today)
        )
    ).all()

    created = []
    for schedule in schedules:
        item = RecurringQueueItem(schedule_id=schedule.id, due_date=today)
        session.add(item)
        schedule.next_due_date = _advance_next_due_date(schedule)
        created.append(item)

    session.commit()
    return created


def auto_post_pending(session: Session, today: date | None = None) -> list[RecurringQueueItem]:
    today = today or date.today()
    items = session.exec(
        select(RecurringQueueItem)
        .where(RecurringQueueItem.due_date == today)
        .where(RecurringQueueItem.status == "pending")
    ).all()

    posted = []
    for item in items:
        schedule = session.get(RecurringSchedule, item.schedule_id)
        txn = _clone_transaction(session, schedule.template_transaction_id, today)
        if txn:
            item.status = "auto-posted"
            item.posted_transaction_id = txn.id
            posted.append(item)

    session.commit()
    return posted


def _clone_transaction(session: Session, template_id: int, new_date: date,
                        narration: str | None = None) -> Transaction | None:
    template = session.get(Transaction, template_id)
    if not template:
        return None
    fy = find_fy_for_date(session, new_date)
    if not fy:
        return None

    number = next_transaction_number(session, fy, template.type)

    txn = Transaction(
        number=number,
        type=template.type,
        date=new_date,
        narration=narration or template.narration,
        fy_id=fy.id,
        tags=template.tags,
    )
    session.add(txn)
    session.flush()

    entries = session.exec(select(Entry).where(Entry.transaction_id == template_id)).all()
    for e in entries:
        session.add(Entry(transaction_id=txn.id, account_id=e.account_id, amount=e.amount))

    session.commit()
    session.refresh(txn)
    return txn
