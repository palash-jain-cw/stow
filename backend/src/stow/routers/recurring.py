from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from stow.db import get_session
from stow.models import Account, Entry, RecurringQueueItem, RecurringSchedule, Transaction
from stow.recurring import _clone_transaction, create_queue_entries_for_today

router = APIRouter(prefix="/recurring", tags=["recurring"])


class ScheduleIn(BaseModel):
    template_transaction_id: int
    frequency: str
    day_of_period: Optional[int] = None
    first_due_date: date
    end_date: Optional[date] = None


class ScheduleOut(BaseModel):
    id: int
    template_transaction_id: int
    frequency: str
    day_of_period: Optional[int]
    end_date: Optional[date]
    next_due_date: date
    is_active: bool


class QueueItemOut(BaseModel):
    id: int
    schedule_id: int
    due_date: date
    status: str
    posted_transaction_id: Optional[int]


class QueueItemDetailOut(BaseModel):
    id: int
    schedule_id: int
    due_date: date
    status: str
    narration: str
    txn_type: str
    amount_paise: int
    from_account_id: int
    from_account_name: str
    to_account_id: int
    to_account_name: str


_VALID_FREQUENCIES = {"daily", "weekly", "monthly", "yearly"}


@router.post("/schedules", response_model=ScheduleOut, status_code=201)
def create_schedule(data: ScheduleIn, session: Session = Depends(get_session)):
    if data.frequency not in _VALID_FREQUENCIES:
        raise HTTPException(status_code=422, detail=f"frequency must be one of {sorted(_VALID_FREQUENCIES)}")
    if not session.get(Transaction, data.template_transaction_id):
        raise HTTPException(status_code=404, detail="Template transaction not found")

    schedule = RecurringSchedule(
        template_transaction_id=data.template_transaction_id,
        frequency=data.frequency,
        day_of_period=data.day_of_period,
        end_date=data.end_date,
        next_due_date=data.first_due_date,
    )
    session.add(schedule)
    session.commit()
    session.refresh(schedule)
    return schedule


@router.get("/schedules", response_model=list[ScheduleOut])
def list_schedules(session: Session = Depends(get_session)):
    return session.exec(
        select(RecurringSchedule).where(RecurringSchedule.is_active == True)  # noqa: E712
    ).all()


@router.put("/schedules/{schedule_id}", response_model=ScheduleOut)
def update_schedule(schedule_id: int, data: ScheduleIn, session: Session = Depends(get_session)):
    schedule = session.get(RecurringSchedule, schedule_id)
    if not schedule:
        raise HTTPException(status_code=404)
    schedule.frequency = data.frequency
    schedule.day_of_period = data.day_of_period
    schedule.end_date = data.end_date
    session.commit()
    session.refresh(schedule)
    return schedule


@router.delete("/schedules/{schedule_id}", status_code=204)
def delete_schedule(schedule_id: int, session: Session = Depends(get_session)):
    schedule = session.get(RecurringSchedule, schedule_id)
    if not schedule:
        raise HTTPException(status_code=404)
    schedule.is_active = False
    session.commit()


def _enrich_queue_item(session: Session, item: RecurringQueueItem) -> QueueItemDetailOut:
    schedule = session.get(RecurringSchedule, item.schedule_id)
    txn = session.get(Transaction, schedule.template_transaction_id)
    entries = session.exec(
        select(Entry).where(Entry.transaction_id == schedule.template_transaction_id)
    ).all()

    # Credit entry (negative amount) = money leaving = "from" account
    # Debit entry (positive amount)  = money arriving = "to" account
    credit = next((e for e in entries if e.amount < 0), entries[0] if entries else None)
    debit = next((e for e in entries if e.amount > 0), entries[-1] if entries else None)

    from_acc = session.get(Account, credit.account_id) if credit else None
    to_acc = session.get(Account, debit.account_id) if debit else None
    amount = abs(credit.amount) if credit else (debit.amount if debit else 0)

    return QueueItemDetailOut(
        id=item.id,
        schedule_id=item.schedule_id,
        due_date=item.due_date,
        status=item.status,
        narration=txn.narration if txn else "",
        txn_type=txn.type if txn else "",
        amount_paise=amount,
        from_account_id=credit.account_id if credit else 0,
        from_account_name=from_acc.name if from_acc else "",
        to_account_id=debit.account_id if debit else 0,
        to_account_name=to_acc.name if to_acc else "",
    )


@router.get("/due-today", response_model=list[QueueItemDetailOut])
def due_today(session: Session = Depends(get_session)):
    today = date.today()
    items = session.exec(
        select(RecurringQueueItem)
        .where(RecurringQueueItem.due_date == today)
        .where(RecurringQueueItem.status == "pending")
    ).all()
    return [_enrich_queue_item(session, item) for item in items]


class ConfirmIn(BaseModel):
    date: Optional[date] = None
    narration: Optional[str] = None


@router.post("/queue/{item_id}/confirm", response_model=QueueItemOut)
def confirm_queue_item(item_id: int, data: ConfirmIn = ConfirmIn(), session: Session = Depends(get_session)):
    item = session.get(RecurringQueueItem, item_id)
    if not item or item.status != "pending":
        raise HTTPException(status_code=404, detail="Pending queue item not found")

    schedule = session.get(RecurringSchedule, item.schedule_id)
    post_date = data.date or item.due_date
    txn = _clone_transaction(session, schedule.template_transaction_id, post_date, data.narration)
    if not txn:
        raise HTTPException(status_code=422, detail="No active financial year covers this date")

    item.status = "confirmed"
    item.posted_transaction_id = txn.id
    session.commit()
    session.refresh(item)
    return item


@router.post("/queue/{item_id}/skip", response_model=QueueItemOut)
def skip_queue_item(item_id: int, session: Session = Depends(get_session)):
    item = session.get(RecurringQueueItem, item_id)
    if not item or item.status != "pending":
        raise HTTPException(status_code=404, detail="Pending queue item not found")
    item.status = "skipped"
    session.commit()
    session.refresh(item)
    return item
