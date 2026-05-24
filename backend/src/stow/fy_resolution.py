from __future__ import annotations

import logging
from datetime import date

from sqlmodel import Session, col, select

from stow.models import FinancialYear

logger = logging.getLogger(__name__)


class FyResolutionError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def indian_fy_bounds(txn_date: date) -> tuple[date, date]:
    """Indian FY (Apr 1 – Mar 31) containing txn_date."""
    if txn_date.month >= 4:
        start = date(txn_date.year, 4, 1)
        end = date(txn_date.year + 1, 3, 31)
    else:
        start = date(txn_date.year - 1, 4, 1)
        end = date(txn_date.year, 3, 31)
    return start, end


def date_in_fy(txn_date: date, fy: FinancialYear) -> bool:
    return fy.start_date <= txn_date <= fy.end_date


def find_fy_for_date(session: Session, txn_date: date) -> FinancialYear | None:
    """Unlocked FY covering txn_date, or None."""
    return session.exec(
        select(FinancialYear)
        .where(FinancialYear.start_date <= txn_date)
        .where(FinancialYear.end_date >= txn_date)
        .where(FinancialYear.status != "locked")
    ).first()


def find_fy_covering_date(session: Session, txn_date: date) -> FinancialYear | None:
    """Any FY covering txn_date regardless of lock status."""
    return session.exec(
        select(FinancialYear)
        .where(FinancialYear.start_date <= txn_date)
        .where(FinancialYear.end_date >= txn_date)
    ).first()


def ensure_fy_for_date(
    session: Session,
    txn_date: date,
    *,
    auto_create: bool = True,
) -> tuple[FinancialYear, bool]:
    """Return (fy, created). Raises ValueError if unavailable."""
    existing = find_fy_for_date(session, txn_date)
    if existing:
        return existing, False

    covering = find_fy_covering_date(session, txn_date)
    if covering is not None and covering.status == "locked":
        raise ValueError(f"Financial year covering {txn_date} is locked")

    if not auto_create:
        raise ValueError(f"No financial year covers {txn_date}")

    start, end = indian_fy_bounds(txn_date)
    overlap = session.exec(
        select(FinancialYear).where(
            col(FinancialYear.start_date) <= end,
            col(FinancialYear.end_date) >= start,
        )
    ).first()
    if overlap is not None:
        if overlap.status == "locked":
            raise ValueError(f"Financial year covering {txn_date} is locked")
        if date_in_fy(txn_date, overlap):
            return overlap, False

    fy = FinancialYear(start_date=start, end_date=end, status="open")
    session.add(fy)
    session.flush()
    session.refresh(fy)
    logger.info(
        "Auto-created financial year id=%s for %s–%s",
        fy.id,
        start,
        end,
    )
    return fy, True


def resolve_fy_for_posting(
    session: Session,
    txn_date: date,
    fy_id: int | None = None,
    *,
    auto_create: bool = True,
) -> tuple[FinancialYear, bool]:
    """Return (fy, fy_was_auto_created). Raises FyResolutionError."""
    if fy_id is not None:
        fy = session.get(FinancialYear, fy_id)
        if fy is None:
            raise FyResolutionError(404, "Financial year not found")
        if fy.status == "locked":
            raise FyResolutionError(403, "Financial year is locked")
        if not date_in_fy(txn_date, fy):
            raise FyResolutionError(
                422,
                f"Transaction date {txn_date} is not within financial year "
                f"{fy.start_date}–{fy.end_date}",
            )
        return fy, False

    try:
        return ensure_fy_for_date(session, txn_date, auto_create=auto_create)
    except ValueError as exc:
        msg = str(exc)
        if "locked" in msg:
            raise FyResolutionError(403, msg) from exc
        raise FyResolutionError(422, msg) from exc


def raise_http_from_fy_error(exc: FyResolutionError) -> None:
    from fastapi import HTTPException

    raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
