from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlmodel import Session

from stow.db import get_session
from stow.reports.repository import ReportRepository
from stow.reports.schemas import (
    TrialBalanceReport,
    ProfitLossReport,
    BalanceSheetReport,
    CashFlowReport,
)

router = APIRouter(prefix="/reports", tags=["reports"])


def _repo(session: Session = Depends(get_session)) -> ReportRepository:
    return ReportRepository(session)


def _get_format(format: str = "json") -> str:
    return format


@router.get("/trial-balance", response_model=TrialBalanceReport)
def trial_balance(fy_id: int, format: str = "json", repo: ReportRepository = Depends(_repo)):
    try:
        report = repo.trial_balance(fy_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    if format == "pdf":
        from stow.reports.pdf import render_pdf
        return Response(content=render_pdf("trial_balance", report), media_type="application/pdf")
    return report


@router.get("/profit-loss", response_model=ProfitLossReport)
def profit_loss(fy_id: int, format: str = "json", repo: ReportRepository = Depends(_repo)):
    try:
        report = repo.profit_loss(fy_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    if format == "pdf":
        from stow.reports.pdf import render_pdf
        return Response(content=render_pdf("profit_loss", report), media_type="application/pdf")
    return report


@router.get("/balance-sheet", response_model=BalanceSheetReport)
def balance_sheet(fy_id: int, format: str = "json", repo: ReportRepository = Depends(_repo)):
    try:
        report = repo.balance_sheet(fy_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    if format == "pdf":
        from stow.reports.pdf import render_pdf
        return Response(content=render_pdf("balance_sheet", report), media_type="application/pdf")
    return report


@router.get("/cash-flow", response_model=CashFlowReport)
def cash_flow(fy_id: int, format: str = "json", repo: ReportRepository = Depends(_repo)):
    try:
        report = repo.cash_flow(fy_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    if format == "pdf":
        from stow.reports.pdf import render_pdf
        return Response(content=render_pdf("cash_flow", report), media_type="application/pdf")
    return report
