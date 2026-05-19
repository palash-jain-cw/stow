from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, col, select

from stow.db import get_session
from stow.investments.prices import PriceRepository
from stow.investments.repository import LotRepository
from stow.investments.schemas import (
    BuyIn, SellIn, LotOut, HoldingOut, CapitalGainsSummary, CapitalGainEntryOut,
    PortfolioItemOut, FdCreateIn, FdOut, FdListItemOut, FdMatureIn, FdMatureOut,
)
from stow.investments.fd import accrued_interest as _accrued_interest
from stow.models import Account, Entry, FinancialYear, FdMetadata, Transaction

_VALID_COMPOUNDING = {"simple", "monthly", "quarterly", "yearly"}

router = APIRouter(prefix="/investments", tags=["investments"])


def _next_journal_number(session: Session, fy_id: int) -> str:
    fy = session.get(FinancialYear, fy_id)
    assert fy is not None
    count = len(session.exec(
        select(Transaction)
        .where(col(Transaction.fy_id) == fy_id)
        .where(col(Transaction.type) == "journal")
    ).all())
    return f"JRN-{fy.start_date.year}-{count + 1:03d}"


@router.post("/fds", response_model=FdOut, status_code=201)
def create_fd(data: FdCreateIn, session: Session = Depends(get_session)):
    from stow.models import AccountGroup

    if data.compounding not in _VALID_COMPOUNDING:
        raise HTTPException(status_code=422, detail=f"compounding must be one of {sorted(_VALID_COMPOUNDING)}")

    fy = session.get(FinancialYear, data.fy_id)
    if fy is None:
        raise HTTPException(status_code=404, detail="Financial year not found")
    if fy.status == "locked":
        raise HTTPException(status_code=403, detail="Cannot post to a locked financial year")
    if fy.status == "open":
        fy.status = "active"

    group = session.exec(select(AccountGroup).where(AccountGroup.name == "Investments")).first()
    if not group:
        raise HTTPException(status_code=500, detail="Investments account group not seeded")

    account = Account(name=data.name, group_id=group.id, investment_subtype="fd")
    session.add(account)
    session.flush()
    assert account.id is not None

    fd = FdMetadata(
        account_id=account.id,
        principal=data.principal,
        interest_rate=data.interest_rate,
        start_date=data.start_date,
        maturity_date=data.maturity_date,
        compounding=data.compounding,
    )
    session.add(fd)

    txn = Transaction(
        number=_next_journal_number(session, data.fy_id),
        type="journal",
        date=data.date,
        narration=data.narration,
        fy_id=data.fy_id,
    )
    session.add(txn)
    session.flush()
    assert txn.id is not None

    session.add(Entry(transaction_id=txn.id, account_id=account.id, amount=data.principal))
    session.add(Entry(transaction_id=txn.id, account_id=data.from_account_id, amount=-data.principal))
    session.commit()

    return FdOut(
        account_id=account.id,
        transaction_id=txn.id,
        name=account.name,
        principal=fd.principal,
        interest_rate=fd.interest_rate,
        start_date=fd.start_date,
        maturity_date=fd.maturity_date,
        compounding=fd.compounding,
        status=fd.status,
    )


@router.post("/fds/{account_id}/mature", response_model=FdMatureOut, status_code=201)
def mature_fd(account_id: int, data: FdMatureIn, session: Session = Depends(get_session)):
    from decimal import Decimal

    fd = session.exec(select(FdMetadata).where(FdMetadata.account_id == account_id)).first()
    if fd is None:
        raise HTTPException(status_code=404, detail="FD not found")
    if fd.status != "active":
        raise HTTPException(status_code=409, detail=f"FD is already {fd.status}")

    fy = session.get(FinancialYear, data.fy_id)
    if fy is None:
        raise HTTPException(status_code=404, detail="Financial year not found")
    if fy.status == "locked":
        raise HTTPException(status_code=403, detail="Cannot post to a locked financial year")
    if fy.status == "open":
        fy.status = "active"

    # Calculate interest to maturity date
    t_days = (fd.maturity_date - fd.start_date).days
    rate = Decimal(fd.interest_rate) / Decimal(10000)
    t_years = Decimal(t_days) / Decimal(365)
    periods = {"simple": None, "monthly": 12, "quarterly": 4, "yearly": 1}
    n = periods.get(fd.compounding)
    if n is None:
        interest = int(Decimal(fd.principal) * rate * t_years)
    else:
        interest = int(Decimal(fd.principal) * ((1 + rate / n) ** (n * t_years) - 1))
    total = fd.principal + interest

    # Look up interest income account
    interest_acc = session.exec(
        select(Account).where(Account.name == "Fixed Deposit Interest Income")
    ).first()
    if interest_acc is None:
        raise HTTPException(status_code=500, detail="'Fixed Deposit Interest Income' account not seeded")
    assert interest_acc.id is not None

    txn = Transaction(
        number=_next_journal_number(session, data.fy_id),
        type="journal",
        date=data.date,
        narration=data.narration,
        fy_id=data.fy_id,
    )
    session.add(txn)
    session.flush()
    assert txn.id is not None

    # Debit receiving account (principal + interest)
    session.add(Entry(transaction_id=txn.id, account_id=data.to_account_id, amount=total))
    # Credit FD account at principal
    session.add(Entry(transaction_id=txn.id, account_id=account_id, amount=-fd.principal))
    # Credit interest income
    if interest > 0:
        session.add(Entry(transaction_id=txn.id, account_id=interest_acc.id, amount=-interest))

    fd.status = "matured"
    session.commit()

    return FdMatureOut(
        transaction_id=txn.id,
        account_id=account_id,
        principal=fd.principal,
        interest=interest,
        total=total,
    )


def _repo(session: Session = Depends(get_session)) -> LotRepository:
    return LotRepository(session)


@router.get("/fds", response_model=list[FdListItemOut])
def list_fds(session: Session = Depends(get_session)):
    from datetime import date

    rows = session.exec(
        select(Account, FdMetadata)
        .where(Account.id == FdMetadata.account_id)
        .where(Account.is_archived == False)  # noqa: E712
        .order_by(FdMetadata.start_date)
    ).all()

    today = date.today()
    return [
        FdListItemOut(
            account_id=account.id,
            name=account.name,
            principal=fd.principal,
            interest_rate=fd.interest_rate,
            start_date=fd.start_date,
            maturity_date=fd.maturity_date,
            compounding=fd.compounding,
            status=fd.status,
            days_to_maturity=(fd.maturity_date - today).days,
            accrued_interest=_accrued_interest(fd.principal, fd.interest_rate, fd.start_date, fd.compounding),
        )
        for account, fd in rows
    ]


@router.get("/fds/maturing-soon", response_model=list[FdListItemOut])
def fds_maturing_soon(days: int = 30, session: Session = Depends(get_session)):
    from datetime import date, timedelta

    today = date.today()
    cutoff = today + timedelta(days=days)
    rows = session.exec(
        select(Account, FdMetadata)
        .where(Account.id == FdMetadata.account_id)
        .where(Account.is_archived == False)  # noqa: E712
        .where(FdMetadata.maturity_date >= today)
        .where(FdMetadata.maturity_date <= cutoff)
        .order_by(FdMetadata.maturity_date)
    ).all()

    return [
        FdListItemOut(
            account_id=account.id,
            name=account.name,
            principal=fd.principal,
            interest_rate=fd.interest_rate,
            start_date=fd.start_date,
            maturity_date=fd.maturity_date,
            compounding=fd.compounding,
            status=fd.status,
            days_to_maturity=(fd.maturity_date - today).days,
            accrued_interest=_accrued_interest(fd.principal, fd.interest_rate, fd.start_date, fd.compounding),
        )
        for account, fd in rows
    ]


@router.post("/{account_id}/buy", response_model=LotOut, status_code=201)
def buy(account_id: int, data: BuyIn, repo: LotRepository = Depends(_repo)):
    try:
        return repo.buy(account_id, data)
    except (ValueError, PermissionError) as e:
        status = 403 if isinstance(e, PermissionError) else 422
        raise HTTPException(status_code=status, detail=str(e))


@router.post("/{account_id}/sell", response_model=list[CapitalGainEntryOut], status_code=201)
def sell(account_id: int, data: SellIn, repo: LotRepository = Depends(_repo)):
    try:
        return repo.sell(account_id, data)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/{account_id}/holdings", response_model=list[HoldingOut])
def holdings(account_id: int, repo: LotRepository = Depends(_repo)):
    return repo.holdings(account_id)


@router.get("/{account_id}/capital-gains", response_model=CapitalGainsSummary)
def capital_gains(account_id: int, fy_id: int, repo: LotRepository = Depends(_repo)):
    try:
        return repo.capital_gains(account_id, fy_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{account_id}/portfolio", response_model=list[PortfolioItemOut])
def portfolio(
    account_id: int,
    repo: LotRepository = Depends(_repo),
    session: Session = Depends(get_session),
):
    holdings = repo.holdings(account_id)
    latest = PriceRepository(session).latest(account_id)
    current_price = latest.price if latest else None
    return [
        PortfolioItemOut(
            lot_id=h.lot_id,
            acquisition_date=h.acquisition_date,
            units=h.units,
            remaining_units=h.remaining_units,
            cost_per_unit=h.cost_per_unit,
            cost_basis=h.cost_basis,
            current_price_per_unit=current_price,
            current_value=h.remaining_units * current_price // 1000 if current_price is not None else None,
            unrealized_gain=(h.remaining_units * current_price // 1000) - h.cost_basis if current_price is not None else None,
        )
        for h in holdings
    ]
