import uuid

import pytest

from tests.helpers import get_or_create_account, get_or_create_fy, get_or_create_group


@pytest.fixture()
def ctx(client):
    """Isolated bank + expense + FY per test."""
    tag = uuid.uuid4().hex[:8]
    year = 2060 + (int(tag[:4], 16) % 30)
    get_or_create_group(client, f"Audit Banks {tag}", "asset")
    get_or_create_group(client, f"Audit Expenses {tag}", "expense")
    bank = get_or_create_account(client, f"Audit Bank {tag}", f"Audit Banks {tag}")
    expense = get_or_create_account(client, f"Audit Expense {tag}", f"Audit Expenses {tag}")
    fy = get_or_create_fy(client, f"{year}-04-01", f"{year + 1}-03-31")
    return {"bank": bank, "expense": expense, "fy": fy, "tag": tag, "year": year}


def make_txn(ctx, amount=10000, txn_type="payment", narration="Test", date=None):
    return {
        "type": txn_type,
        "date": date or f"{ctx['year']}-06-01",
        "narration": narration,
        "fy_id": ctx["fy"]["id"],
        "entries": [
            {"account_id": ctx["expense"]["id"], "amount": amount},
            {"account_id": ctx["bank"]["id"], "amount": -amount},
        ],
    }


def _post(client, ctx, **kwargs):
    resp = client.post("/transactions", json=make_txn(ctx, **kwargs))
    assert resp.status_code == 201, resp.text
    return resp.json()


# ── Slice 7: audit log ────────────────────────────────────────────────────


def test_edit_creates_audit_log(client, ctx):
    txn = _post(client, ctx)
    client.put(f"/transactions/{txn['id']}", json={"narration": "Updated narration"})
    logs = client.get(f"/transactions/{txn['id']}/audit-log").json()
    assert len(logs) == 1
    assert logs[0]["snapshot"]["narration"] == "Test"


def test_multiple_edits_append_audit_logs(client, ctx):
    txn = _post(client, ctx)
    client.put(f"/transactions/{txn['id']}", json={"narration": "Edit 1"})
    client.put(f"/transactions/{txn['id']}", json={"narration": "Edit 2"})
    logs = client.get(f"/transactions/{txn['id']}/audit-log").json()
    assert len(logs) == 2


# ── Slice 8: GET /transactions filters ───────────────────────────────────


def test_filter_by_type(client, ctx):
    _post(client, ctx, txn_type="payment")
    _post(client, ctx, txn_type="receipt")
    resp = client.get("/transactions?type=payment")
    assert all(t["type"] == "payment" for t in resp.json())


def test_filter_by_account(client, ctx):
    tag = ctx["tag"]
    _post(client, ctx, narration=f"Scoped {tag}")
    resp = client.get(f"/transactions?account_id={ctx['bank']['id']}&q={tag}")
    assert len(resp.json()) == 1


def test_filter_by_narration(client, ctx):
    tag = ctx["tag"]
    _post(client, ctx, narration=f"Electricity bill {tag}")
    _post(client, ctx, narration=f"Office supplies {tag}")
    results = client.get(f"/transactions?q={tag}").json()
    electricity = [t for t in results if "Electricity" in t["narration"]]
    assert len(electricity) == 1


# ── Slice 9: ledger ───────────────────────────────────────────────────────


def test_ledger_returns_transactions_for_account(client, ctx):
    b = ctx["bank"]["id"]
    fy_id = ctx["fy"]["id"]
    _post(client, ctx, amount=10000)
    _post(client, ctx, amount=5000)
    data = client.get(f"/accounts/{b}/ledger?fy_id={fy_id}").json()
    assert len(data) == 2
    assert data[0]["running_balance"] == -10000
    assert data[1]["running_balance"] == -15000


# ── Slice 10: opening balance editable until FY locked ─────────────────────


def test_opening_balance_allowed_after_transaction(client, ctx):
    b = ctx["bank"]["id"]
    _post(client, ctx)
    resp = client.put(
        f"/accounts/{b}/opening-balance",
        json={"fy_id": ctx["fy"]["id"], "amount": 99999},
    )
    assert resp.status_code == 200
    assert resp.json()["amount"] == 99999


def test_opening_balance_rejected_when_fy_locked(client, ctx):
    b = ctx["bank"]["id"]
    client.post(f"/financial-years/{ctx['fy']['id']}/lock")
    resp = client.put(
        f"/accounts/{b}/opening-balance",
        json={"fy_id": ctx["fy"]["id"], "amount": 99999},
    )
    assert resp.status_code == 403
