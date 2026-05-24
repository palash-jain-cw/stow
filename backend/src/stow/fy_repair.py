from __future__ import annotations

import logging
import traceback
from dataclasses import dataclass, field
from datetime import date

from sqlmodel import Session, col, select

from stow.fy_resolution import (
    date_in_fy,
    ensure_fy_for_date,
    find_fy_covering_date,
    find_fy_for_date,
    indian_fy_bounds,
)
from stow.models import FinancialYear, Transaction
from stow.transaction_numbers import next_transaction_number

logger = logging.getLogger(__name__)


@dataclass
class SkippedTransaction:
    txn_id: int
    reason: str


@dataclass
class CreatedFinancialYear:
    fy_id: int
    start_date: date
    end_date: date
    txn_count: int = 1


@dataclass
class FyMoveBucket:
    start_date: date
    end_date: date
    txn_count: int
    will_create: bool


@dataclass
class RepairSummary:
    moved: int = 0
    dry_run: bool = False
    skipped_locked: list[SkippedTransaction] = field(default_factory=list)
    fys_created: list[CreatedFinancialYear] = field(default_factory=list)
    move_buckets: list[FyMoveBucket] = field(default_factory=list)


def _sync_investment_dates(session: Session, txn_id: int, new_date: date) -> None:
    from stow.models import CapitalGainEntry, Lot

    for lot in session.exec(select(Lot).where(Lot.transaction_id == txn_id)).all():
        lot.acquisition_date = new_date
        session.add(lot)
    for cge in session.exec(
        select(CapitalGainEntry).where(col(CapitalGainEntry.sale_transaction_id) == txn_id)
    ).all():
        cge.sale_date = new_date
        session.add(cge)


def repair_fy_assignments(session: Session, *, dry_run: bool = False) -> RepairSummary:
    """Move transactions whose date falls outside their assigned FY range."""
    summary = RepairSummary(dry_run=dry_run)
    txns = session.exec(select(Transaction)).all()
    move_counts: dict[tuple[date, date], dict[str, object]] = {}
    created_bounds: set[tuple[date, date]] = set()

    for txn in txns:
        assert txn.id is not None
        assigned = session.get(FinancialYear, txn.fy_id)
        if assigned is None:
            logger.warning("Transaction %s has missing fy_id=%s", txn.id, txn.fy_id)
            continue
        if date_in_fy(txn.date, assigned):
            continue

        if assigned.status == "locked":
            summary.skipped_locked.append(
                SkippedTransaction(
                    txn_id=txn.id,
                    reason=f"Assigned FY {assigned.id} is locked",
                )
            )
            continue

        if dry_run:
            target = find_fy_for_date(session, txn.date)
            created = False
            if target is None:
                covering = find_fy_covering_date(session, txn.date)
                if covering is not None and covering.status == "locked":
                    summary.skipped_locked.append(
                        SkippedTransaction(
                            txn_id=txn.id,
                            reason=f"Financial year covering {txn.date} is locked",
                        )
                    )
                    continue
                start, end = indian_fy_bounds(txn.date)
                created = True
                target = FinancialYear(start_date=start, end_date=end, status="open")
        else:
            try:
                target, created = ensure_fy_for_date(session, txn.date, auto_create=True)
            except ValueError as exc:
                summary.skipped_locked.append(
                    SkippedTransaction(txn_id=txn.id, reason=str(exc))
                )
                continue

        if target.status == "locked":
            summary.skipped_locked.append(
                SkippedTransaction(
                    txn_id=txn.id,
                    reason=f"Target FY {target.id} is locked",
                )
            )
            continue

        bounds = (target.start_date, target.end_date)
        bucket = move_counts.setdefault(
            bounds,
            {"txn_count": 0, "will_create": created},
        )
        bucket["txn_count"] = int(bucket["txn_count"]) + 1
        if created:
            created_bounds.add(bounds)

        if dry_run:
            summary.moved += 1
            continue

        try:
            if target.id != assigned.id:
                txn.fy_id = target.id or assigned.id
                txn.number = next_transaction_number(session, target, txn.type)
            _sync_investment_dates(session, txn.id, txn.date)
            session.add(txn)
            summary.moved += 1
        except Exception:
            logger.error(
                "Failed to repair transaction id=%s\n%s",
                txn.id,
                traceback.format_exc(),
            )
            session.rollback()
            raise

    summary.move_buckets = [
        FyMoveBucket(
            start_date=start,
            end_date=end,
            txn_count=int(data["txn_count"]),
            will_create=(start, end) in created_bounds,
        )
        for (start, end), data in sorted(move_counts.items())
    ]
    summary.fys_created = [
        CreatedFinancialYear(
            fy_id=0,
            start_date=start,
            end_date=end,
            txn_count=int(move_counts[(start, end)]["txn_count"]),
        )
        for start, end in sorted(created_bounds)
    ]

    if not dry_run:
        for item in summary.fys_created:
            fy = session.exec(
                select(FinancialYear).where(
                    FinancialYear.start_date == item.start_date,
                    FinancialYear.end_date == item.end_date,
                )
            ).first()
            if fy is not None:
                item.fy_id = fy.id or 0

    if not dry_run:
        session.commit()

    logger.info(
        "FY repair complete dry_run=%s moved=%s skipped=%s fys_created=%s",
        dry_run,
        summary.moved,
        len(summary.skipped_locked),
        len(summary.fys_created),
    )
    return summary
