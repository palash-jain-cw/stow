from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlmodel import Session, col, select
from stow.db import get_session
from stow.models import Account, AccountGroup, Entry, FinancialYear, OpeningBalance, Transaction

router = APIRouter(prefix="/accounts", tags=["accounts"])


class AccountOut(BaseModel):
    id: int
    name: str
    group_id: int
    group_name: str
    nature: str  # asset | liability | equity | income | expense
    is_archived: bool
    investment_subtype: Optional[str]
    depreciation_rate: Optional[float]
    accumulated_depreciation_account_id: Optional[int]
    price_source_id: Optional[str]
    currency: str
    balance: int  # paise, signed (positive = Dr). scope=active: OB + entries in FY; scope=position: OB(active) + all entries.


def _entry_map_all_fys(session: Session) -> dict[int, int]:
    """Sum entry amounts per account across all financial years."""
    entry_rows = session.exec(
        select(Entry.account_id, func.sum(Entry.amount).label("total"))
        .join(Transaction, col(Entry.transaction_id) == col(Transaction.id))
        .group_by(Entry.account_id)
    ).all()
    return {row[0]: int(row[1]) for row in entry_rows}


def _entry_map_for_fy(session: Session, fy_id: int) -> dict[int, int]:
    entry_rows = session.exec(
        select(Entry.account_id, func.sum(Entry.amount).label("total"))
        .join(Transaction, col(Entry.transaction_id) == col(Transaction.id))
        .where(Transaction.fy_id == fy_id)
        .group_by(Entry.account_id)
    ).all()
    return {row[0]: int(row[1]) for row in entry_rows}


def _balance_maps(
    session: Session,
    fy_id: int,
    *,
    scope: str = "active",
) -> tuple[dict[int, int], dict[int, int]]:
    """Return (opening_balance_map, entry_sum_map) keyed by account_id."""
    ob_rows = session.exec(
        select(OpeningBalance).where(OpeningBalance.fy_id == fy_id)
    ).all()
    ob_map = {ob.account_id: ob.amount for ob in ob_rows}

    if scope == "position":
        # Current position: active-year OB (carry-forward) + this year's entries.
        # When OB is zero, fall back to all-time entries (pre-reconcile / no chain).
        all_entries = _entry_map_all_fys(session)
        active_entries = _entry_map_for_fy(session, fy_id)
        entry_map = {
            account_id: (
                active_entries.get(account_id, 0)
                if ob_map.get(account_id, 0)
                else all_entries.get(account_id, 0)
            )
            for account_id in set(all_entries) | set(active_entries) | set(ob_map)
        }
    else:
        entry_map = _entry_map_for_fy(session, fy_id)

    return ob_map, entry_map


def _to_out(account: Account, group: AccountGroup, ob_map: dict, entry_map: dict) -> AccountOut:
    balance = ob_map.get(account.id, 0) + entry_map.get(account.id, 0)
    return AccountOut(
        id=account.id,
        name=account.name,
        group_id=account.group_id,
        group_name=group.name,
        nature=group.nature,
        is_archived=account.is_archived,
        investment_subtype=account.investment_subtype,
        depreciation_rate=account.depreciation_rate,
        accumulated_depreciation_account_id=account.accumulated_depreciation_account_id,
        price_source_id=account.price_source_id,
        currency=account.currency,
        balance=balance,
    )


def _resolve_balance_scope(scope: str) -> str:
    if scope not in {"active", "position"}:
        raise HTTPException(status_code=422, detail="scope must be 'active' or 'position'")
    return scope


@router.get("", response_model=list[AccountOut])
def list_accounts(
    include_archived: bool = False,
    scope: str = "active",
    session: Session = Depends(get_session),
):
    scope = _resolve_balance_scope(scope)
    q = select(Account, AccountGroup).join(AccountGroup, col(Account.group_id) == col(AccountGroup.id))
    if not include_archived:
        q = q.where(Account.is_archived == False)  # noqa: E712
    rows = session.exec(q).all()

    active_fy = session.exec(select(FinancialYear).where(FinancialYear.status == "active")).first()
    if active_fy:
        ob_map, entry_map = _balance_maps(session, active_fy.id, scope=scope)
    else:
        ob_map, entry_map = {}, {}

    return [_to_out(account, group, ob_map, entry_map) for account, group in rows]


@router.post("", response_model=Account, status_code=201)
def create_account(account: Account, session: Session = Depends(get_session)):
    session.add(account)
    session.commit()
    session.refresh(account)
    return account


@router.get("/{account_id}", response_model=AccountOut)
def get_account(
    account_id: int,
    scope: str = "active",
    session: Session = Depends(get_session),
):
    scope = _resolve_balance_scope(scope)
    row = session.exec(
        select(Account, AccountGroup)
        .join(AccountGroup, col(Account.group_id) == col(AccountGroup.id))
        .where(Account.id == account_id)
    ).first()
    if not row:
        raise HTTPException(status_code=404)
    account, group = row

    active_fy = session.exec(select(FinancialYear).where(FinancialYear.status == "active")).first()
    if active_fy:
        ob_map, entry_map = _balance_maps(session, active_fy.id, scope=scope)
    else:
        ob_map, entry_map = {}, {}

    return _to_out(account, group, ob_map, entry_map)


@router.put("/{account_id}", response_model=AccountOut)
def update_account(account_id: int, data: Account, session: Session = Depends(get_session)):
    account = session.get(Account, account_id)
    if not account:
        raise HTTPException(status_code=404)
    for field, value in data.model_dump(exclude_unset=True, exclude={"id"}).items():
        setattr(account, field, value)
    session.commit()
    session.refresh(account)
    return get_account(account_id, session=session)


@router.post("/{account_id}/archive", response_model=AccountOut)
def archive_account(account_id: int, session: Session = Depends(get_session)):
    account = session.get(Account, account_id)
    if not account:
        raise HTTPException(status_code=404)
    account.is_archived = True
    session.commit()
    return get_account(account_id, session=session)


@router.post("/{account_id}/unarchive", response_model=AccountOut)
def unarchive_account(account_id: int, session: Session = Depends(get_session)):
    account = session.get(Account, account_id)
    if not account:
        raise HTTPException(status_code=404)
    account.is_archived = False
    session.commit()
    return get_account(account_id, session=session)


@router.get("/{account_id}/ledger")
def get_ledger(
    account_id: int,
    session: Session = Depends(get_session),
    fy_id: int = Query(default=None),
):
    account = session.get(Account, account_id)
    if not account:
        raise HTTPException(status_code=404)
    # Resolve financial year: use provided fy_id or active FY
    if fy_id is None:
        active_fy = session.exec(
            select(FinancialYear).where(FinancialYear.status == "active")
        ).first()
        if active_fy:
            fy_id = active_fy.id
    # Get opening balance for this account in this FY
    ob = session.exec(
        select(OpeningBalance)
        .where(OpeningBalance.account_id == account_id)
        .where(OpeningBalance.fy_id == fy_id)
    ).first()
    opening_balance = ob.amount if ob else 0
    # Get entries filtered by FY (if resolved)
    query = (
        select(Entry)
        .where(Entry.account_id == account_id)
        .join(Transaction, col(Transaction.id) == col(Entry.transaction_id))
        .order_by(col(Transaction.date), col(Transaction.id))
    )
    if fy_id is not None:
        query = query.where(Transaction.fy_id == fy_id)
    entries = session.exec(query).all()
    running_balance = opening_balance
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
            "debit": entry.amount if entry.amount > 0 else 0,
            "credit": abs(entry.amount) if entry.amount < 0 else 0,
            "balance": running_balance,
        })
    return {
        "account_name": account.name,
        "opening_balance": opening_balance,
        "entries": list(reversed(result)),
    }
