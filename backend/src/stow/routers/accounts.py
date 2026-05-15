from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, col, select
from stow.db import get_session
from stow.models import Account, Entry, Transaction

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.get("", response_model=list[Account])
def list_accounts(
    include_archived: bool = False,
    session: Session = Depends(get_session),
):
    q = select(Account)
    if not include_archived:
        q = q.where(Account.is_archived == False)  # noqa: E712
    return session.exec(q).all()


@router.post("", response_model=Account, status_code=201)
def create_account(account: Account, session: Session = Depends(get_session)):
    session.add(account)
    session.commit()
    session.refresh(account)
    return account


@router.get("/{account_id}", response_model=Account)
def get_account(account_id: int, session: Session = Depends(get_session)):
    account = session.get(Account, account_id)
    if not account:
        raise HTTPException(status_code=404)
    return account


@router.put("/{account_id}", response_model=Account)
def update_account(account_id: int, data: Account, session: Session = Depends(get_session)):
    account = session.get(Account, account_id)
    if not account:
        raise HTTPException(status_code=404)
    for field, value in data.model_dump(exclude_unset=True, exclude={"id"}).items():
        setattr(account, field, value)
    session.commit()
    session.refresh(account)
    return account


@router.post("/{account_id}/archive", response_model=Account)
def archive_account(account_id: int, session: Session = Depends(get_session)):
    account = session.get(Account, account_id)
    if not account:
        raise HTTPException(status_code=404)
    account.is_archived = True
    session.commit()
    session.refresh(account)
    return account


@router.post("/{account_id}/unarchive", response_model=Account)
def unarchive_account(account_id: int, session: Session = Depends(get_session)):
    account = session.get(Account, account_id)
    if not account:
        raise HTTPException(status_code=404)
    account.is_archived = False
    session.commit()
    session.refresh(account)
    return account


@router.get("/{account_id}/ledger")
def get_ledger(account_id: int, session: Session = Depends(get_session)):
    if not session.get(Account, account_id):
        raise HTTPException(status_code=404)
    entries = session.exec(
        select(Entry)
        .where(Entry.account_id == account_id)
        .join(Transaction, col(Transaction.id) == col(Entry.transaction_id))
        .order_by(col(Transaction.date), col(Transaction.id))
    ).all()
    running_balance = 0
    result = []
    for entry in entries:
        txn = session.get(Transaction, entry.transaction_id)
        assert txn is not None
        running_balance += entry.amount
        result.append({
            "transaction_id": entry.transaction_id,
            "date": txn.date,
            "narration": txn.narration,
            "amount": entry.amount,
            "running_balance": running_balance,
        })
    return result
