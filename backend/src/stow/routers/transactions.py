from __future__ import annotations

from datetime import date as _date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, col, select
from stow.db import get_session
from stow.models import Account, Entry, FinancialYear, Transaction, TransactionAuditLog

router = APIRouter(prefix="/transactions", tags=["transactions"])

_TYPE_ABBR = {
    "payment": "PAY",
    "receipt": "REC",
    "journal": "JRN",
    "contra": "CTR",
}


class EntryIn(BaseModel):
    account_id: int
    amount: int


class TransactionIn(BaseModel):
    type: str
    date: _date
    narration: str
    fy_id: int
    entries: list[EntryIn]
    tags: Optional[list[str]] = None
    attachment_path: Optional[str] = None


class EntryOut(BaseModel):
    id: Optional[int]
    account_id: int
    account_name: str
    amount: int


class TransactionOut(BaseModel):
    id: int
    number: str
    type: str
    date: _date
    entry_date: _date
    narration: str
    fy_id: int
    tags: Optional[list] = None
    attachment_path: Optional[str] = None
    entries: list[EntryOut]


def _entry_out(entry: Entry, session: Session) -> EntryOut:
    account = session.get(Account, entry.account_id)
    return EntryOut(
        id=entry.id,
        account_id=entry.account_id,
        account_name=account.name if account else f"Account {entry.account_id}",
        amount=entry.amount,
    )


def _next_number(session: Session, fy: FinancialYear, txn_type: str) -> str:
    abbr = _TYPE_ABBR[txn_type]
    fy_year = fy.start_date.year
    existing = session.exec(
        select(Transaction).where(
            Transaction.fy_id == fy.id,
            Transaction.type == txn_type,
        )
    ).all()
    seq = len(existing) + 1
    return f"{abbr}-{fy_year}-{seq:03d}"


def _validate_balance(entries: list[EntryIn]) -> None:
    if sum(e.amount for e in entries) != 0:
        raise HTTPException(status_code=422, detail="Entries must sum to zero")


@router.post("", response_model=TransactionOut, status_code=201)
def create_transaction(data: TransactionIn, session: Session = Depends(get_session)):
    fy = session.get(FinancialYear, data.fy_id)
    if not fy:
        raise HTTPException(status_code=404, detail="Financial year not found")
    if fy.status == "locked":
        raise HTTPException(status_code=403, detail="Financial year is locked")

    _validate_balance(data.entries)

    number = _next_number(session, fy, data.type)
    txn = Transaction(
        number=number,
        type=data.type,
        date=data.date,
        narration=data.narration,
        fy_id=data.fy_id,
        tags=data.tags,
        attachment_path=data.attachment_path,
    )
    session.add(txn)
    session.flush()
    assert txn.id is not None

    entries = [
        Entry(transaction_id=txn.id, account_id=e.account_id, amount=e.amount)
        for e in data.entries
    ]
    for entry in entries:
        session.add(entry)

    if fy.status == "open":
        fy.status = "active"

    session.commit()
    session.refresh(txn)

    return TransactionOut(
        **txn.model_dump(),
        entries=[_entry_out(e, session) for e in entries],
    )


def _get_txn_with_entries(txn_id: int, session: Session) -> TransactionOut:
    txn = session.get(Transaction, txn_id)
    if not txn:
        raise HTTPException(status_code=404)
    entries = session.exec(select(Entry).where(Entry.transaction_id == txn_id)).all()
    return TransactionOut(
        **txn.model_dump(),
        entries=[_entry_out(e, session) for e in entries],
    )


@router.get("", response_model=list[TransactionOut])
def list_transactions(
    type: Optional[str] = None,
    account_id: Optional[int] = None,
    q: Optional[str] = None,
    from_date: Optional[_date] = None,
    to_date: Optional[_date] = None,
    session: Session = Depends(get_session),
):
    stmt = select(Transaction)
    if type:
        stmt = stmt.where(Transaction.type == type)
    if q:
        stmt = stmt.where(col(Transaction.narration).ilike(f"%{q}%"))
    if from_date:
        stmt = stmt.where(Transaction.date >= from_date)
    if to_date:
        stmt = stmt.where(Transaction.date <= to_date)
    if account_id:
        stmt = stmt.join(Entry, col(Entry.transaction_id) == col(Transaction.id)).where(
            Entry.account_id == account_id
        )
    txns = session.exec(stmt).all()
    result = []
    for txn in txns:
        txn_entries = session.exec(select(Entry).where(Entry.transaction_id == txn.id)).all()
        result.append(TransactionOut(
            **txn.model_dump(),
            entries=[_entry_out(e, session) for e in txn_entries],
        ))
    return result


@router.get("/{txn_id}/audit-log")
def get_audit_log(txn_id: int, session: Session = Depends(get_session)):
    if not session.get(Transaction, txn_id):
        raise HTTPException(status_code=404)
    return session.exec(
        select(TransactionAuditLog)
        .where(TransactionAuditLog.transaction_id == txn_id)
        .order_by(col(TransactionAuditLog.edited_at))
    ).all()


@router.get("/{txn_id}", response_model=TransactionOut)
def get_transaction(txn_id: int, session: Session = Depends(get_session)):
    return _get_txn_with_entries(txn_id, session)


@router.delete("/{txn_id}", status_code=204)
def delete_transaction(txn_id: int, session: Session = Depends(get_session)):
    txn = session.get(Transaction, txn_id)
    if not txn:
        raise HTTPException(status_code=404)
    fy = session.get(FinancialYear, txn.fy_id)
    if fy and fy.status == "locked":
        raise HTTPException(status_code=403, detail="Financial year is locked")
    entries = session.exec(select(Entry).where(Entry.transaction_id == txn_id)).all()
    for entry in entries:
        session.delete(entry)
    session.delete(txn)
    session.commit()


class TransactionUpdate(BaseModel):
    narration: Optional[str] = None
    date: Optional[_date] = None
    tags: Optional[list[str]] = None
    entries: Optional[list[EntryIn]] = None


@router.put("/{txn_id}", response_model=TransactionOut)
def update_transaction(
    txn_id: int,
    data: TransactionUpdate,
    session: Session = Depends(get_session),
):
    txn = session.get(Transaction, txn_id)
    if not txn:
        raise HTTPException(status_code=404)

    fy = session.get(FinancialYear, txn.fy_id)
    if fy and fy.status == "locked":
        raise HTTPException(status_code=403, detail="Financial year is locked")

    # Snapshot before edit — use mode='json' so date/datetime become strings
    existing_entries = session.exec(select(Entry).where(Entry.transaction_id == txn_id)).all()
    snapshot = {
        **txn.model_dump(mode="json"),
        "entries": [e.model_dump(mode="json") for e in existing_entries],
    }
    session.add(TransactionAuditLog(transaction_id=txn_id, snapshot=snapshot))

    for field, value in data.model_dump(exclude_unset=True, exclude={"entries"}).items():
        setattr(txn, field, value)

    if data.entries is not None:
        _validate_balance(data.entries)
        for entry in existing_entries:
            session.delete(entry)
        session.flush()
        for entry_in in data.entries:
            session.add(Entry(transaction_id=txn_id, account_id=entry_in.account_id, amount=entry_in.amount))

    session.commit()
    session.refresh(txn)
    return _get_txn_with_entries(txn_id, session)
