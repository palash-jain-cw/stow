"""Unit tests for agent subagent tools against a real test database."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest

# Tool functions under test
from agent.subagents.transaction import (
    _create_transaction,
    _delete_transaction,
    _get_active_fy,
    _get_transaction,
    _list_accounts,
    _list_transactions,
    _update_transaction,
)
from agent.subagents.account import (
    _archive_account,
    _create_account,
    _get_account,
    _get_account_ledger,
    _list_accounts as _account_list_accounts,
)
from agent.subagents.report import (
    _get_balance_sheet,
    _get_cash_flow,
    _get_current_date,
    _get_financial_years,
    _get_profit_loss,
    _get_trial_balance,
    _list_accounts as _report_list_accounts,
    _list_transactions as _report_list_transactions,
)
from agent.subagents.recurring import (
    _get_recurring_due,
    _list_schedules,
)
from agent.subagents.import_agent import (
    _review_staging,
    _update_staging_row,
    _confirm_staging,
    _get_batch,
)
from agent.deps import StowDeps


# ─── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def asgi_app():
    """FastAPI app wired to the test database — reuses the session-scoped engine."""
    from stow.main import app
    return app


@pytest.fixture()
async def http_client(asgi_app, session):
    """Async HTTP client using ASGI transport so no real network call is needed."""
    from stow.db import get_session
    asgi_app.dependency_overrides[get_session] = lambda: session
    transport = httpx.ASGITransport(app=asgi_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    asgi_app.dependency_overrides.clear()


@pytest.fixture()
def deps(http_client):
    return StowDeps(base_url="http://test", http_client=http_client)


@pytest.fixture()
def ctx(deps):
    """Minimal RunContext mock — tools only need ctx.deps."""
    mock = MagicMock()
    mock.deps = deps
    return mock


@pytest.fixture()
async def fy(client):
    """Create an active financial year and return it."""
    r = client.post("/financial-years", json={
        "start_date": "2026-04-01",
        "end_date": "2027-03-31",
        "status": "active",
    })
    assert r.status_code == 201
    return r.json()


@pytest.fixture()
async def two_accounts(client, session):
    """Return two account group IDs (asset, expense) and create two accounts."""
    from sqlmodel import select
    from stow.models import AccountGroup
    asset_group = session.exec(
        select(AccountGroup).where(AccountGroup.nature == "asset")
    ).first()
    expense_group = session.exec(
        select(AccountGroup).where(AccountGroup.nature == "expense")
    ).first()

    r1 = client.post("/accounts", json={"name": "Test Bank", "group_id": asset_group.id, "currency": "INR"})
    assert r1.status_code == 201
    r2 = client.post("/accounts", json={"name": "Test Expense", "group_id": expense_group.id, "currency": "INR"})
    assert r2.status_code == 201
    return r1.json(), r2.json()


# ─── Tests ─────────────────────────────────────────────────────────────────

class TestTransactionTools:
    async def test_get_active_fy(self, ctx, fy):
        result = await _get_active_fy(ctx)
        assert result["status"] in ("active", "open")
        assert "id" in result

    async def test_list_accounts(self, ctx, two_accounts):
        result = await _list_accounts(ctx)
        names = [a["name"] for a in result]
        assert "Test Bank" in names
        assert "Test Expense" in names

    async def test_create_and_get_transaction(self, ctx, fy, two_accounts):
        bank, expense = two_accounts
        result = await _create_transaction(
            ctx,
            type="payment",
            date_str="2026-05-16",
            narration="Electricity bill",
            fy_id=fy["id"],
            from_account_id=bank["id"],
            to_account_id=expense["id"],
            amount_paise=240000,
        )
        assert result["narration"] == "Electricity bill"
        assert result["type"] == "payment"
        assert len(result["entries"]) == 2

        fetched = await _get_transaction(ctx, result["id"])
        assert fetched["id"] == result["id"]

    async def test_list_and_filter_transactions(self, ctx, fy, two_accounts):
        bank, expense = two_accounts
        await _create_transaction(
            ctx,
            type="payment",
            date_str="2026-05-16",
            narration="Filter test",
            fy_id=fy["id"],
            from_account_id=bank["id"],
            to_account_id=expense["id"],
            amount_paise=100,
        )
        txns = await _list_transactions(ctx, q="Filter test")
        assert any(t["narration"] == "Filter test" for t in txns)

    async def test_update_transaction(self, ctx, fy, two_accounts):
        bank, expense = two_accounts
        txn = await _create_transaction(
            ctx,
            type="payment",
            date_str="2026-05-16",
            narration="Original",
            fy_id=fy["id"],
            from_account_id=bank["id"],
            to_account_id=expense["id"],
            amount_paise=500,
        )
        updated = await _update_transaction(ctx, txn["id"], narration="Updated")
        assert updated["narration"] == "Updated"

    async def test_delete_transaction(self, ctx, fy, two_accounts):
        bank, expense = two_accounts
        txn = await _create_transaction(
            ctx,
            type="payment",
            date_str="2026-05-16",
            narration="To delete",
            fy_id=fy["id"],
            from_account_id=bank["id"],
            to_account_id=expense["id"],
            amount_paise=100,
        )
        result = await _delete_transaction(ctx, txn["id"])
        assert result["deleted"] is True


class TestAccountTools:
    async def test_list_accounts(self, ctx, two_accounts):
        result = await _account_list_accounts(ctx)
        assert isinstance(result, list)
        assert len(result) >= 2

    async def test_get_account(self, ctx, two_accounts):
        bank, _ = two_accounts
        result = await _get_account(ctx, bank["id"])
        assert result["id"] == bank["id"]
        assert result["name"] == "Test Bank"

    async def test_create_account(self, ctx, session):
        from sqlmodel import select
        from stow.models import AccountGroup
        group = session.exec(
            select(AccountGroup).where(AccountGroup.nature == "asset")
        ).first()
        result = await _create_account(ctx, name="New Account", group_id=group.id)
        assert result["name"] == "New Account"

    async def test_archive_account(self, ctx, session):
        from sqlmodel import select
        from stow.models import AccountGroup
        group = session.exec(
            select(AccountGroup).where(AccountGroup.nature == "asset")
        ).first()
        created = await _create_account(ctx, name="To Archive", group_id=group.id)
        archived = await _archive_account(ctx, created["id"])
        assert archived["is_archived"] is True

    async def test_get_account_ledger(self, ctx, fy, two_accounts):
        bank, _ = two_accounts
        result = await _get_account_ledger(ctx, bank["id"])
        assert isinstance(result, list)


class TestReportTools:
    async def test_get_current_date(self, ctx):
        result = await _get_current_date(ctx)
        assert "date" in result
        assert "year" in result and "month" in result and "day" in result
        import re
        assert re.match(r"\d{4}-\d{2}-\d{2}", result["date"])

    async def test_get_financial_years(self, ctx, fy):
        result = await _get_financial_years(ctx)
        assert isinstance(result, list)
        ids = [f["id"] for f in result]
        assert fy["id"] in ids

    async def test_list_accounts(self, ctx, two_accounts):
        result = await _report_list_accounts(ctx)
        assert isinstance(result, list)
        names = [a["name"] for a in result]
        assert "Test Bank" in names

    async def test_list_transactions_no_filter(self, ctx, fy, two_accounts):
        bank, expense = two_accounts
        await _create_transaction(
            ctx,
            type="payment",
            date_str="2026-05-01",
            narration="Report filter test",
            fy_id=fy["id"],
            from_account_id=bank["id"],
            to_account_id=expense["id"],
            amount_paise=5000,
        )
        result = await _report_list_transactions(ctx)
        assert any(t["narration"] == "Report filter test" for t in result)

    async def test_list_transactions_from_date_filter(self, ctx, fy, two_accounts):
        bank, expense = two_accounts
        await _create_transaction(
            ctx, type="payment", date_str="2026-04-10", narration="April report txn",
            fy_id=fy["id"], from_account_id=bank["id"], to_account_id=expense["id"], amount_paise=100,
        )
        await _create_transaction(
            ctx, type="payment", date_str="2026-06-10", narration="June report txn",
            fy_id=fy["id"], from_account_id=bank["id"], to_account_id=expense["id"], amount_paise=100,
        )
        result = await _report_list_transactions(ctx, from_date="2026-06-01")
        narrations = [t["narration"] for t in result]
        assert "June report txn" in narrations
        assert "April report txn" not in narrations

    async def test_list_transactions_date_range(self, ctx, fy, two_accounts):
        bank, expense = two_accounts
        await _create_transaction(
            ctx, type="payment", date_str="2026-05-15", narration="May range txn",
            fy_id=fy["id"], from_account_id=bank["id"], to_account_id=expense["id"], amount_paise=200,
        )
        result = await _report_list_transactions(
            ctx, from_date="2026-05-01", to_date="2026-05-31"
        )
        assert any(t["narration"] == "May range txn" for t in result)

    async def test_get_trial_balance(self, ctx, fy, two_accounts):
        result = await _get_trial_balance(ctx, fy["id"])
        assert "rows" in result

    async def test_get_profit_loss(self, ctx, fy):
        result = await _get_profit_loss(ctx, fy["id"])
        assert isinstance(result, dict)
        assert "total_income" in result or "net_profit" in result

    async def test_get_balance_sheet(self, ctx, fy):
        result = await _get_balance_sheet(ctx, fy["id"])
        assert isinstance(result, dict)
        assert "total_assets" in result

    async def test_get_cash_flow(self, ctx, fy):
        result = await _get_cash_flow(ctx, fy["id"])
        assert isinstance(result, dict)
        assert "net_change_in_cash" in result or "sections" in result


class TestRecurringTools:
    async def test_get_recurring_due_empty(self, ctx):
        result = await _get_recurring_due(ctx)
        assert isinstance(result, list)

    async def test_list_schedules_empty(self, ctx):
        result = await _list_schedules(ctx)
        assert isinstance(result, list)


class TestImportAgentTools:
    """Tests for import_agent tools: review, update, confirm staging."""

    @pytest.fixture()
    def batch(self, session):
        """Create a ready import batch with one staging row directly via the test session."""
        from datetime import date as _date
        from stow.models import ImportBatch, StagingRow

        b = ImportBatch(filename="test_stmt.pdf", status="ready")
        session.add(b)
        session.flush()
        row = StagingRow(
            batch_id=b.id,
            raw_data={"desc": "SWIGGY PAYMENT"},
            date=_date(2026, 5, 10),
            amount=-30000,
            description="SWIGGY PAYMENT",
        )
        session.add(row)
        session.flush()
        return {"batch_id": b.id, "row_id": row.id}

    async def test_review_staging_returns_rows(self, ctx, batch):
        rows = await _review_staging(ctx, batch["batch_id"])
        assert isinstance(rows, list)
        assert len(rows) >= 1
        assert any(r["description"] == "SWIGGY PAYMENT" for r in rows)

    async def test_update_staging_row_status(self, ctx, batch):
        row = await _update_staging_row(ctx, batch["batch_id"], batch["row_id"], status="confirmed")
        assert row["status"] == "confirmed"

    async def test_get_batch_returns_counts(self, ctx, batch):
        result = await _get_batch(ctx, batch["batch_id"])
        assert "counts" in result
        assert "pending" in result["counts"]


# ─── Dep isolation test ────────────────────────────────────────────────────

class TestStowDepsIsolation:
    def test_clone_for_subagent_isolates_subagents(self, deps):
        deps.subagents["x"] = object()
        clone = deps.clone_for_subagent(max_depth=0)
        assert clone.subagents == {}
        assert clone.base_url == deps.base_url
        assert clone.http_client is deps.http_client

    def test_clone_with_depth_inherits_subagents(self, deps):
        obj = object()
        deps.subagents["x"] = obj
        clone = deps.clone_for_subagent(max_depth=1)
        assert "x" in clone.subagents
