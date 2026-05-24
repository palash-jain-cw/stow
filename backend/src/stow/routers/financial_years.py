from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, col, select
from stow.db import get_session
from stow.depreciation import unposted_depreciation
from stow.fy_repair import repair_fy_assignments
from stow.fy_resolution import ensure_fy_for_date
from stow.models import Account, AccountGroup, Entry, FinancialYear, Transaction

router = APIRouter(prefix="/financial-years", tags=["financial-years"])


@router.get("", response_model=list[FinancialYear])
def list_financial_years(session: Session = Depends(get_session)):
    return session.exec(select(FinancialYear).order_by(col(FinancialYear.start_date))).all()


@router.post("", response_model=FinancialYear, status_code=201)
def create_financial_year(fy: FinancialYear, session: Session = Depends(get_session)):
    # Reject date ranges that overlap with any existing financial year
    start = date.fromisoformat(str(fy.start_date))
    end = date.fromisoformat(str(fy.end_date))
    existing = session.exec(select(FinancialYear)).all()
    for ex in existing:
        if start <= ex.end_date and end >= ex.start_date:
            raise HTTPException(
                status_code=422,
                detail=f"Date range overlaps with existing financial year {ex.id}",
            )
    session.add(fy)
    session.commit()
    session.refresh(fy)
    return fy


@router.get("/for-date")
def fy_for_date(
    date: date,
    auto_create: bool = Query(default=False),
    session: Session = Depends(get_session),
):
    try:
        fy, created = ensure_fy_for_date(session, date, auto_create=auto_create)
        if auto_create and created:
            session.commit()
            session.refresh(fy)
        return {"fy": fy, "created": created}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


class RepairSummaryOut(BaseModel):
    moved: int
    dry_run: bool
    skipped_locked: list[dict]
    fys_created: list[dict]
    move_buckets: list[dict]


@router.post("/repair-assignments", response_model=RepairSummaryOut)
def repair_assignments(
    dry_run: bool = Query(default=True),
    session: Session = Depends(get_session),
):
    summary = repair_fy_assignments(session, dry_run=dry_run)
    return RepairSummaryOut(
        moved=summary.moved,
        dry_run=summary.dry_run,
        skipped_locked=[
            {"txn_id": s.txn_id, "reason": s.reason} for s in summary.skipped_locked
        ],
        fys_created=[
            {
                "fy_id": c.fy_id,
                "start_date": c.start_date.isoformat(),
                "end_date": c.end_date.isoformat(),
                "txn_count": c.txn_count,
            }
            for c in summary.fys_created
        ],
        move_buckets=[
            {
                "start_date": b.start_date.isoformat(),
                "end_date": b.end_date.isoformat(),
                "txn_count": b.txn_count,
                "will_create": b.will_create,
            }
            for b in summary.move_buckets
        ],
    )


@router.get("/{fy_id}", response_model=FinancialYear)
def get_financial_year(fy_id: int, session: Session = Depends(get_session)):
    fy = session.get(FinancialYear, fy_id)
    if not fy:
        raise HTTPException(status_code=404)
    return fy


@router.get("/{fy_id}/pre-lock-check")
def pre_lock_check(fy_id: int, session: Session = Depends(get_session)):
    fy = session.get(FinancialYear, fy_id)
    if not fy:
        raise HTTPException(status_code=404)
    return {"unposted_depreciation": unposted_depreciation(session, fy_id)}


@router.post("/{fy_id}/lock", response_model=FinancialYear)
def lock_financial_year(fy_id: int, session: Session = Depends(get_session)):
    fy = session.get(FinancialYear, fy_id)
    if not fy:
        raise HTTPException(status_code=404)
    if fy.status == "locked":
        raise HTTPException(status_code=409, detail="Financial year is already locked")

    # Calculate net profit: sum entries on income/expense accounts in this FY
    pl_natures = {"income", "expense"}
    txn_ids = [
        t.id for t in session.exec(
            select(Transaction).where(Transaction.fy_id == fy_id)
        ).all()
    ]
    net_profit = 0
    if txn_ids:
        entries = session.exec(
            select(Entry).where(col(Entry.transaction_id).in_(txn_ids))
        ).all()
        for entry in entries:
            account = session.get(Account, entry.account_id)
            group = session.get(AccountGroup, account.group_id) if account else None
            if group and group.nature in pl_natures:
                net_profit += entry.amount

    fy.net_profit = net_profit
    fy.status = "locked"
    session.commit()
    session.refresh(fy)
    return fy
