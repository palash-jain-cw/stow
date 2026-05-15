import pytest


@pytest.fixture()
def fy(client):
    return client.post("/financial-years", json={
        "start_date": "2025-04-01", "end_date": "2026-03-31",
    }).json()


@pytest.fixture()
def accounts(client):
    grp = client.post("/account-groups", json={"name": "Bank Accounts", "nature": "asset"}).json()
    exp_grp = client.post("/account-groups", json={"name": "Indirect Expenses", "nature": "expense"}).json()
    bank = client.post("/accounts", json={"name": "HDFC Bank", "group_id": grp["id"]}).json()
    expense = client.post("/accounts", json={"name": "Office Supplies", "group_id": exp_grp["id"]}).json()
    return {"bank": bank, "expense": expense}


def make_txn(fy_id, bank_id, expense_id, amount=10000, txn_type="payment", narration="Test"):
    return {
        "type": txn_type, "date": "2025-06-01", "narration": narration, "fy_id": fy_id,
        "entries": [
            {"account_id": expense_id, "amount": amount},
            {"account_id": bank_id,    "amount": -amount},
        ],
    }


# ── Slice 7: audit log ────────────────────────────────────────────────────

def test_edit_creates_audit_log(client, fy, accounts):
    b, e = accounts["bank"]["id"], accounts["expense"]["id"]
    txn = client.post("/transactions", json=make_txn(fy["id"], b, e)).json()
    client.put(f"/transactions/{txn['id']}", json={"narration": "Updated narration"})
    resp = client.get(f"/transactions/{txn['id']}/audit-log")
    assert resp.status_code == 200
    logs = resp.json()
    assert len(logs) == 1
    assert logs[0]["snapshot"]["narration"] == "Test"


def test_multiple_edits_append_audit_logs(client, fy, accounts):
    b, e = accounts["bank"]["id"], accounts["expense"]["id"]
    txn = client.post("/transactions", json=make_txn(fy["id"], b, e)).json()
    client.put(f"/transactions/{txn['id']}", json={"narration": "Edit 1"})
    client.put(f"/transactions/{txn['id']}", json={"narration": "Edit 2"})
    logs = client.get(f"/transactions/{txn['id']}/audit-log").json()
    assert len(logs) == 2


# ── Slice 8: GET /transactions filters ───────────────────────────────────

def test_filter_by_type(client, fy, accounts):
    b, e = accounts["bank"]["id"], accounts["expense"]["id"]
    client.post("/transactions", json=make_txn(fy["id"], b, e, txn_type="payment"))
    client.post("/transactions", json=make_txn(fy["id"], b, e, txn_type="receipt"))
    resp = client.get("/transactions?type=payment")
    assert all(t["type"] == "payment" for t in resp.json())


def test_filter_by_account(client, fy, accounts):
    b, e = accounts["bank"]["id"], accounts["expense"]["id"]
    client.post("/transactions", json=make_txn(fy["id"], b, e))
    resp = client.get(f"/transactions?account_id={b}")
    assert len(resp.json()) == 1


def test_filter_by_narration(client, fy, accounts):
    b, e = accounts["bank"]["id"], accounts["expense"]["id"]
    client.post("/transactions", json=make_txn(fy["id"], b, e, narration="Electricity bill"))
    client.post("/transactions", json=make_txn(fy["id"], b, e, narration="Office supplies"))
    resp = client.get("/transactions?q=electricity")
    results = resp.json()
    assert len(results) == 1
    assert "Electricity" in results[0]["narration"]


# ── Slice 9: ledger ───────────────────────────────────────────────────────

def test_ledger_returns_transactions_for_account(client, fy, accounts):
    b, e = accounts["bank"]["id"], accounts["expense"]["id"]
    client.post("/transactions", json=make_txn(fy["id"], b, e, amount=10000))
    client.post("/transactions", json=make_txn(fy["id"], b, e, amount=5000))
    resp = client.get(f"/accounts/{b}/ledger")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["running_balance"] == -10000
    assert data[1]["running_balance"] == -15000


# ── Slice 10: opening balance locked after first transaction ──────────────

def test_opening_balance_locked_after_transaction(client, fy, accounts):
    b, e = accounts["bank"]["id"], accounts["expense"]["id"]
    client.post("/transactions", json=make_txn(fy["id"], b, e))
    resp = client.put(
        f"/accounts/{b}/opening-balance",
        json={"fy_id": fy["id"], "amount": 99999},
    )
    assert resp.status_code == 409
