from __future__ import annotations

from datetime import date

import pytest
from sqlmodel import Session

from stow.fy_repair import repair_fy_assignments
from stow.fy_resolution import indian_fy_bounds, resolve_fy_for_posting, FyResolutionError
from stow.models import FinancialYear, Transaction


def test_indian_fy_bounds_april():
    start, end = indian_fy_bounds(date(2025, 6, 1))
    assert start == date(2025, 4, 1)
    assert end == date(2026, 3, 31)


def test_indian_fy_bounds_march():
    start, end = indian_fy_bounds(date(2025, 2, 15))
    assert start == date(2024, 4, 1)
    assert end == date(2025, 3, 31)


def test_resolve_fy_mismatch_raises(session: Session):
    fy = FinancialYear(start_date=date(1980, 4, 1), end_date=date(1981, 3, 31), status="open")
    session.add(fy)
    session.commit()
    session.refresh(fy)

    with pytest.raises(FyResolutionError) as exc:
        resolve_fy_for_posting(session, date(1979, 6, 1), fy.id)
    assert exc.value.status_code == 422


def test_auto_create_fy(session: Session):
    fy, created = resolve_fy_for_posting(session, date(2177, 8, 1))
    assert created is True
    assert fy.start_date == date(2177, 4, 1)
    assert fy.end_date == date(2178, 3, 31)
    assert fy.status == "open"


def test_repair_moves_mismatched_txn(client, session: Session):
    """Repair moves a txn into the FY that covers its date (existing or created)."""
    txn_date = date(2170, 6, 1)
    expected_start, expected_end = indian_fy_bounds(txn_date)
    fy_wrong = FinancialYear(
        start_date=date(2171, 4, 1),
        end_date=date(2172, 3, 31),
        status="active",
    )
    session.add(fy_wrong)
    session.commit()
    session.refresh(fy_wrong)

    txn = Transaction(
        number="PAY-2170-001",
        type="payment",
        date=txn_date,
        narration="Backdated",
        fy_id=fy_wrong.id,
    )
    session.add(txn)
    session.commit()
    session.refresh(txn)

    summary = repair_fy_assignments(session, dry_run=False)
    assert summary.moved == 1

    session.refresh(txn)
    target = session.get(FinancialYear, txn.fy_id)
    assert target is not None
    assert target.start_date == expected_start
    assert target.end_date == expected_end
    assert txn.number.startswith("PAY-2170-")
