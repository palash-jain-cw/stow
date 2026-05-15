from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, col, select
from stow.db import get_session
from stow.models import Account, Entry, OpeningBalance, Transaction

router = APIRouter(tags=["opening-balances"])


@router.get("/accounts/{account_id}/opening-balance", response_model=OpeningBalance)
def get_opening_balance(account_id: int, fy_id: int, session: Session = Depends(get_session)):
    if not session.get(Account, account_id):
        raise HTTPException(status_code=404, detail="Account not found")
    ob = session.exec(
        select(OpeningBalance)
        .where(OpeningBalance.account_id == account_id)
        .where(OpeningBalance.fy_id == fy_id)
    ).first()
    if not ob:
        return OpeningBalance(account_id=account_id, fy_id=fy_id, amount=0)
    return ob


from pydantic import BaseModel


class OpeningBalanceIn(BaseModel):
    fy_id: int
    amount: int


@router.put("/accounts/{account_id}/opening-balance", response_model=OpeningBalance)
def put_opening_balance(
    account_id: int,
    data: OpeningBalanceIn,
    session: Session = Depends(get_session),
):
    if not session.get(Account, account_id):
        raise HTTPException(status_code=404, detail="Account not found")

    # Reject if any transaction entry exists for this account in the given FY
    txn_in_fy = session.exec(
        select(Transaction).where(Transaction.fy_id == data.fy_id)
    ).all()
    txn_ids = [t.id for t in txn_in_fy]
    if txn_ids:
        entry_exists = session.exec(
            select(Entry)
            .where(Entry.account_id == account_id)
            .where(col(Entry.transaction_id).in_(txn_ids))
        ).first()
        if entry_exists:
            raise HTTPException(status_code=409, detail="Cannot edit opening balance after transactions exist")
    ob = session.exec(
        select(OpeningBalance)
        .where(OpeningBalance.account_id == account_id)
        .where(OpeningBalance.fy_id == data.fy_id)
    ).first()
    if ob:
        ob.amount = data.amount
    else:
        ob = OpeningBalance(account_id=account_id, fy_id=data.fy_id, amount=data.amount)
        session.add(ob)
    session.commit()
    session.refresh(ob)
    return ob
