import pytest
from datetime import date


@pytest.fixture()
def fy(client):
    resp = client.post("/financial-years", json={
        "start_date": "2025-04-01",
        "end_date": "2026-03-31",
    })
    return resp.json()


@pytest.fixture()
def accounts(client):
    grp = client.post("/account-groups", json={"name": "Bank Accounts", "nature": "asset"}).json()
    exp_grp = client.post("/account-groups", json={"name": "Indirect Expenses", "nature": "expense"}).json()
    bank = client.post("/accounts", json={"name": "HDFC Bank", "group_id": grp["id"]}).json()
    expense = client.post("/accounts", json={"name": "Office Supplies", "group_id": exp_grp["id"]}).json()
    return {"bank": bank, "expense": expense}


def make_txn(fy_id, bank_id, expense_id, amount=10000, txn_type="payment"):
    return {
        "type": txn_type,
        "date": "2025-06-01",
        "narration": "Office supplies purchase",
        "fy_id": fy_id,
        "entries": [
            {"account_id": expense_id, "amount": amount},
            {"account_id": bank_id,    "amount": -amount},
        ],
    }


# ── Slice 1: balanced entries ──────────────────────────────────────────────

def test_create_balanced_transaction(client, fy, accounts):
    payload = make_txn(fy["id"], accounts["bank"]["id"], accounts["expense"]["id"])
    resp = client.post("/transactions", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["number"] == "PAY-2025-001"
    assert data["narration"] == "Office supplies purchase"
    assert len(data["entries"]) == 2


# ── Slice 2: unbalanced entries rejected ──────────────────────────────────

def test_unbalanced_entries_rejected(client, fy, accounts):
    payload = make_txn(fy["id"], accounts["bank"]["id"], accounts["expense"]["id"])
    payload["entries"][1]["amount"] = -99  # doesn't balance
    resp = client.post("/transactions", json=payload)
    assert resp.status_code == 422


# ── Slice 3: transaction numbering ────────────────────────────────────────

def test_numbering_increments_per_type(client, fy, accounts):
    b, e = accounts["bank"]["id"], accounts["expense"]["id"]
    client.post("/transactions", json=make_txn(fy["id"], b, e, txn_type="payment"))
    resp = client.post("/transactions", json=make_txn(fy["id"], b, e, txn_type="payment"))
    assert resp.json()["number"] == "PAY-2025-002"


def test_numbering_independent_per_type(client, fy, accounts):
    b, e = accounts["bank"]["id"], accounts["expense"]["id"]
    client.post("/transactions", json=make_txn(fy["id"], b, e, txn_type="payment"))
    resp = client.post("/transactions", json=make_txn(fy["id"], b, e, txn_type="receipt"))
    assert resp.json()["number"] == "REC-2025-001"


# ── Slice 4: FY lifecycle ─────────────────────────────────────────────────

def test_fy_starts_open(client, fy):
    assert fy["status"] == "open"


def test_first_transaction_activates_fy(client, fy, accounts):
    b, e = accounts["bank"]["id"], accounts["expense"]["id"]
    client.post("/transactions", json=make_txn(fy["id"], b, e))
    updated = client.get(f"/financial-years/{fy['id']}").json()
    assert updated["status"] == "active"


# ── Slice 5: FY lock ──────────────────────────────────────────────────────

def test_lock_fy_stores_net_profit(client, fy, accounts):
    b, e = accounts["bank"]["id"], accounts["expense"]["id"]
    client.post("/transactions", json=make_txn(fy["id"], b, e, amount=50000))
    resp = client.post(f"/financial-years/{fy['id']}/lock")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "locked"
    assert data["net_profit"] is not None


def test_lock_fy_rejects_if_already_locked(client, fy, accounts):
    b, e = accounts["bank"]["id"], accounts["expense"]["id"]
    client.post("/transactions", json=make_txn(fy["id"], b, e))
    client.post(f"/financial-years/{fy['id']}/lock")
    resp = client.post(f"/financial-years/{fy['id']}/lock")
    assert resp.status_code == 409


# ── Slice 6: locked FY read-only ─────────────────────────────────────────

def test_locked_fy_rejects_new_transaction(client, fy, accounts):
    b, e = accounts["bank"]["id"], accounts["expense"]["id"]
    client.post("/transactions", json=make_txn(fy["id"], b, e))
    client.post(f"/financial-years/{fy['id']}/lock")
    resp = client.post("/transactions", json=make_txn(fy["id"], b, e))
    assert resp.status_code == 403


def test_locked_fy_rejects_edit(client, fy, accounts):
    b, e = accounts["bank"]["id"], accounts["expense"]["id"]
    txn = client.post("/transactions", json=make_txn(fy["id"], b, e)).json()
    client.post(f"/financial-years/{fy['id']}/lock")
    resp = client.put(f"/transactions/{txn['id']}", json={"narration": "changed"})
    assert resp.status_code == 403


# ── Slice 7: date range filtering ─────────────────────────────────────────

def _make_txn_on(fy_id, bank_id, expense_id, date_str, narration="txn"):
    return {
        "type": "payment",
        "date": date_str,
        "narration": narration,
        "fy_id": fy_id,
        "entries": [
            {"account_id": expense_id, "amount": 10000},
            {"account_id": bank_id,    "amount": -10000},
        ],
    }


def test_list_transactions_from_date_filter(client, fy, accounts):
    b, e = accounts["bank"]["id"], accounts["expense"]["id"]
    client.post("/transactions", json=_make_txn_on(fy["id"], b, e, "2025-04-15", "April txn"))
    client.post("/transactions", json=_make_txn_on(fy["id"], b, e, "2025-06-15", "June txn"))

    resp = client.get("/transactions?from_date=2025-06-01")
    assert resp.status_code == 200
    narrations = [t["narration"] for t in resp.json()]
    assert "June txn" in narrations
    assert "April txn" not in narrations


def test_list_transactions_to_date_filter(client, fy, accounts):
    b, e = accounts["bank"]["id"], accounts["expense"]["id"]
    client.post("/transactions", json=_make_txn_on(fy["id"], b, e, "2025-04-15", "April txn"))
    client.post("/transactions", json=_make_txn_on(fy["id"], b, e, "2025-06-15", "June txn"))

    resp = client.get("/transactions?to_date=2025-04-30")
    assert resp.status_code == 200
    narrations = [t["narration"] for t in resp.json()]
    assert "April txn" in narrations
    assert "June txn" not in narrations


def test_list_transactions_date_range_filter(client, fy, accounts):
    b, e = accounts["bank"]["id"], accounts["expense"]["id"]
    client.post("/transactions", json=_make_txn_on(fy["id"], b, e, "2025-04-15", "April txn"))
    client.post("/transactions", json=_make_txn_on(fy["id"], b, e, "2025-06-15", "June txn"))
    client.post("/transactions", json=_make_txn_on(fy["id"], b, e, "2025-08-15", "August txn"))

    resp = client.get("/transactions?from_date=2025-05-01&to_date=2025-07-31")
    assert resp.status_code == 200
    narrations = [t["narration"] for t in resp.json()]
    assert "June txn" in narrations
    assert "April txn" not in narrations
    assert "August txn" not in narrations
