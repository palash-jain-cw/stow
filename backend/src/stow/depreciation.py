from __future__ import annotations

from datetime import date

from sqlmodel import Session, col, func, select

from stow.models import Account, Entry, FinancialYear, OpeningBalance, Transaction


def _balance_before_fy(session: Session, account_id: int, fy: FinancialYear) -> int:
    """OB carried into this FY + sum of entries in all prior FYs."""
    ob = session.exec(
        select(OpeningBalance)
        .where(OpeningBalance.account_id == account_id)
        .where(OpeningBalance.fy_id == fy.id)
    ).first()
    ob_amount = ob.amount if ob else 0

    prior_fy_ids = [
        f.id for f in session.exec(
            select(FinancialYear).where(FinancialYear.end_date < fy.start_date)
        ).all()
    ]
    entries_sum = 0
    if prior_fy_ids:
        entries_sum = session.exec(
            select(func.coalesce(func.sum(Entry.amount), 0))
            .join(Transaction, col(Entry.transaction_id) == col(Transaction.id))
            .where(Entry.account_id == account_id)
            .where(col(Transaction.fy_id).in_(prior_fy_ids))
        ).one() or 0

    return ob_amount + entries_sum


def _entries_in_fy(session: Session, account_id: int, fy_id: int) -> int:
    """Sum of entries on an account for transactions in the given FY."""
    result = session.exec(
        select(func.coalesce(func.sum(Entry.amount), 0))
        .join(Transaction, col(Entry.transaction_id) == col(Transaction.id))
        .where(Entry.account_id == account_id)
        .where(Transaction.fy_id == fy_id)
    ).one()
    return result or 0


def _acquisition_date(session: Session, account_id: int) -> date | None:
    row = session.exec(
        select(func.min(Transaction.date))
        .join(Entry, col(Transaction.id) == col(Entry.transaction_id))
        .where(Entry.account_id == account_id)
    ).first()
    return row


def _half_year_applies(acq_date: date | None, fy: FinancialYear) -> bool:
    if acq_date is None:
        return False
    if not (fy.start_date <= acq_date <= fy.end_date):
        return False
    oct3 = date(fy.start_date.year, 10, 3)
    return acq_date > oct3


def unposted_depreciation(session: Session, fy_id: int) -> list[dict]:
    """Accounts with depreciation_amount > 0 but no credit entry on their accum depr account this FY."""
    summary = depreciation_summary(session, fy_id)
    result = []
    for item in summary:
        if item["depreciation_amount"] <= 0:
            continue
        posted = _entries_in_fy(session, item["suggested_cr_account_id"], fy_id)
        if posted >= 0:  # no credit (negative) entry posted yet
            result.append(item)
    return result


def depreciation_summary(session: Session, fy_id: int) -> list[dict]:
    fy = session.get(FinancialYear, fy_id)
    if not fy:
        return []

    assets = session.exec(
        select(Account)
        .where(Account.depreciation_rate != None)  # noqa: E711
        .where(Account.accumulated_depreciation_account_id != None)  # noqa: E711
        .where(Account.is_archived == False)  # noqa: E712
    ).all()

    results = []
    for asset in assets:
        # Gross cost = prior balance + current FY additions (handles assets acquired this FY)
        gross = (_balance_before_fy(session, asset.id, fy)
                 + _entries_in_fy(session, asset.id, fy_id))
        accum = _balance_before_fy(session, asset.accumulated_depreciation_account_id, fy)
        opening_wdv = gross + accum  # accum is negative (credit), so this subtracts

        if opening_wdv <= 0:
            depr_amount = 0
            half_year = False
        else:
            acq = _acquisition_date(session, asset.id)
            half_year = _half_year_applies(acq, fy)
            rate = asset.depreciation_rate * (0.5 if half_year else 1.0)
            depr_amount = int(opening_wdv * rate)

        results.append({
            "account_id": asset.id,
            "account_name": asset.name,
            "depreciation_rate": asset.depreciation_rate,
            "opening_wdv": opening_wdv,
            "depreciation_amount": depr_amount,
            "half_year_rule_applied": half_year,
            "suggested_cr_account_id": asset.accumulated_depreciation_account_id,
        })

    return results
