import uuid

import pytest

from tests.helpers import get_or_create_account, get_or_create_fy, get_or_create_group


@pytest.fixture()
def accounts(client):
    get_or_create_group(client, "Bank Accounts", "asset")
    get_or_create_group(client, "Indirect Expenses", "expense")
    bank = get_or_create_account(client, "HDFC Bank", "Bank Accounts")
    expense = get_or_create_account(client, "Office Supplies", "Indirect Expenses")
    return {"bank": bank, "expense": expense}


def make_txn(fy_id, bank_id, expense_id, amount=10000, txn_type="payment", date="2025-06-01"):
    return {
        "type": txn_type,
        "date": date,
        "narration": "Office supplies purchase",
        "fy_id": fy_id,
        "entries": [
            {"account_id": expense_id, "amount": amount},
            {"account_id": bank_id, "amount": -amount},
        ],
    }


def _make_txn_on(fy_id, bank_id, expense_id, date_str, narration="txn"):
    return {
        "type": "payment",
        "date": date_str,
        "narration": narration,
        "fy_id": fy_id,
        "entries": [
            {"account_id": expense_id, "amount": 10000},
            {"account_id": bank_id, "amount": -10000},
        ],
    }


def _post_txn(client, payload):
    resp = client.post("/transactions", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ── Slice 1: balanced entries ──────────────────────────────────────────────


def test_create_balanced_transaction(client, accounts):
    fy = get_or_create_fy(client, "1995-04-01", "1996-03-31")
    payload = make_txn(
        fy["id"],
        accounts["bank"]["id"],
        accounts["expense"]["id"],
        date="1995-06-01",
    )
    data = _post_txn(client, payload)
    assert data["number"].startswith("PAY-1995-")
    assert data["narration"] == "Office supplies purchase"
    assert len(data["entries"]) == 2


# ── Slice 2: unbalanced entries rejected ──────────────────────────────────


def test_unbalanced_entries_rejected(client, accounts):
    fy = get_or_create_fy(client, "1996-04-01", "1997-03-31")
    payload = make_txn(fy["id"], accounts["bank"]["id"], accounts["expense"]["id"], date="1996-06-01")
    payload["entries"][1]["amount"] = -99
    resp = client.post("/transactions", json=payload)
    assert resp.status_code == 422


# ── Slice 3: transaction numbering ────────────────────────────────────────


def test_numbering_increments_per_type(client, accounts):
    fy = get_or_create_fy(client, "1997-04-01", "1998-03-31")
    b, e = accounts["bank"]["id"], accounts["expense"]["id"]
    _post_txn(client, make_txn(fy["id"], b, e, txn_type="payment", date="1997-06-01"))
    data = _post_txn(client, make_txn(fy["id"], b, e, txn_type="payment", date="1997-06-02"))
    assert data["number"] == "PAY-1997-002"


def test_numbering_independent_per_type(client, accounts):
    fy = get_or_create_fy(client, "1998-04-01", "1999-03-31")
    b, e = accounts["bank"]["id"], accounts["expense"]["id"]
    _post_txn(client, make_txn(fy["id"], b, e, txn_type="payment", date="1998-06-01"))
    data = _post_txn(client, make_txn(fy["id"], b, e, txn_type="receipt", date="1998-06-02"))
    assert data["number"] == "REC-1998-001"


# ── Slice 4: FY lifecycle ─────────────────────────────────────────────────


def test_fy_starts_open(client):
    fy = get_or_create_fy(client, "2199-04-01", "2200-03-31")
    assert fy["status"] == "open"


def test_first_transaction_activates_fy(client, accounts):
    fy = get_or_create_fy(client, "2101-04-01", "2102-03-31")
    b, e = accounts["bank"]["id"], accounts["expense"]["id"]
    _post_txn(client, make_txn(fy["id"], b, e, date="2101-06-01"))
    updated = client.get(f"/financial-years/{fy['id']}").json()
    assert updated["status"] == "active"


# ── Slice 5: FY lock ──────────────────────────────────────────────────────


def test_lock_fy_stores_net_profit(client, accounts):
    fy = get_or_create_fy(client, "2001-04-01", "2002-03-31")
    b, e = accounts["bank"]["id"], accounts["expense"]["id"]
    _post_txn(client, make_txn(fy["id"], b, e, amount=50000, date="2001-06-01"))
    resp = client.post(f"/financial-years/{fy['id']}/lock")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "locked"
    assert data["net_profit"] is not None


def test_lock_fy_rejects_if_already_locked(client, accounts):
    fy = get_or_create_fy(client, "2002-04-01", "2003-03-31")
    b, e = accounts["bank"]["id"], accounts["expense"]["id"]
    _post_txn(client, make_txn(fy["id"], b, e, date="2002-06-01"))
    client.post(f"/financial-years/{fy['id']}/lock")
    resp = client.post(f"/financial-years/{fy['id']}/lock")
    assert resp.status_code == 409


# ── Slice 6: locked FY read-only ─────────────────────────────────────────


def test_locked_fy_rejects_new_transaction(client, accounts):
    fy = get_or_create_fy(client, "2003-04-01", "2004-03-31")
    b, e = accounts["bank"]["id"], accounts["expense"]["id"]
    _post_txn(client, make_txn(fy["id"], b, e, date="2003-06-01"))
    client.post(f"/financial-years/{fy['id']}/lock")
    resp = client.post("/transactions", json=make_txn(fy["id"], b, e, date="2003-07-01"))
    assert resp.status_code == 403


def test_locked_fy_rejects_edit(client, accounts):
    fy = get_or_create_fy(client, "2004-04-01", "2005-03-31")
    b, e = accounts["bank"]["id"], accounts["expense"]["id"]
    txn = _post_txn(client, make_txn(fy["id"], b, e, date="2004-06-01"))
    client.post(f"/financial-years/{fy['id']}/lock")
    resp = client.put(f"/transactions/{txn['id']}", json={"narration": "changed"})
    assert resp.status_code == 403


# ── Slice 7: date range filtering ─────────────────────────────────────────


def test_list_transactions_from_date_filter(client, accounts):
    tag = uuid.uuid4().hex[:8]
    fy = get_or_create_fy(client, "2030-04-01", "2031-03-31")
    b, e = accounts["bank"]["id"], accounts["expense"]["id"]
    _post_txn(client, _make_txn_on(fy["id"], b, e, "2030-04-15", f"April txn {tag}"))
    _post_txn(client, _make_txn_on(fy["id"], b, e, "2030-06-15", f"June txn {tag}"))

    resp = client.get(f"/transactions?from_date=2030-06-01&q={tag}")
    assert resp.status_code == 200
    narrations = [t["narration"] for t in resp.json()]
    assert f"June txn {tag}" in narrations
    assert f"April txn {tag}" not in narrations


def test_list_transactions_to_date_filter(client, accounts):
    tag = uuid.uuid4().hex[:8]
    fy = get_or_create_fy(client, "2031-04-01", "2032-03-31")
    b, e = accounts["bank"]["id"], accounts["expense"]["id"]
    _post_txn(client, _make_txn_on(fy["id"], b, e, "2031-04-15", f"April txn {tag}"))
    _post_txn(client, _make_txn_on(fy["id"], b, e, "2031-06-15", f"June txn {tag}"))

    resp = client.get(f"/transactions?to_date=2031-04-30&q={tag}")
    assert resp.status_code == 200
    narrations = [t["narration"] for t in resp.json()]
    assert f"April txn {tag}" in narrations
    assert f"June txn {tag}" not in narrations


def test_list_transactions_date_range_filter(client, accounts):
    tag = uuid.uuid4().hex[:8]
    fy = get_or_create_fy(client, "2032-04-01", "2033-03-31")
    b, e = accounts["bank"]["id"], accounts["expense"]["id"]
    _post_txn(client, _make_txn_on(fy["id"], b, e, "2032-04-15", f"April txn {tag}"))
    _post_txn(client, _make_txn_on(fy["id"], b, e, "2032-06-15", f"June txn {tag}"))
    _post_txn(client, _make_txn_on(fy["id"], b, e, "2032-08-15", f"August txn {tag}"))

    resp = client.get(f"/transactions?from_date=2032-05-01&to_date=2032-07-31&q={tag}")
    assert resp.status_code == 200
    narrations = [t["narration"] for t in resp.json()]
    assert f"June txn {tag}" in narrations
    assert f"April txn {tag}" not in narrations
    assert f"August txn {tag}" not in narrations


# ── FY-from-date resolution ───────────────────────────────────────────────


def test_post_with_matching_fy_id(client, accounts):
    fy = get_or_create_fy(client, "2016-04-01", "2017-03-31")
    b, e = accounts["bank"]["id"], accounts["expense"]["id"]
    data = _post_txn(client, make_txn(fy["id"], b, e, date="2016-06-01"))
    assert data["fy_id"] == fy["id"]


def test_post_with_mismatched_fy_id_rejected(client, accounts):
    fy = get_or_create_fy(client, "2017-04-01", "2018-03-31")
    other = get_or_create_fy(client, "1994-04-01", "1995-03-31")
    b, e = accounts["bank"]["id"], accounts["expense"]["id"]
    payload = make_txn(other["id"], b, e, date="2017-06-01")
    resp = client.post("/transactions", json=payload)
    assert resp.status_code == 422


def test_post_without_fy_id_resolves_from_date(client, accounts):
    fy = get_or_create_fy(client, "2018-04-01", "2019-03-31")
    b, e = accounts["bank"]["id"], accounts["expense"]["id"]
    payload = make_txn(fy["id"], b, e, date="2018-06-01")
    payload.pop("fy_id")
    data = _post_txn(client, payload)
    assert data["fy_id"] == fy["id"]


def test_post_auto_creates_missing_fy(client, accounts):
    b, e = accounts["bank"]["id"], accounts["expense"]["id"]
    payload = {
        "type": "payment",
        "date": "2023-06-01",
        "narration": "Backfill",
        "entries": [
            {"account_id": e, "amount": 10000},
            {"account_id": b, "amount": -10000},
        ],
    }
    data = _post_txn(client, payload)
    assert data["fy_id"] is not None


def test_put_date_moves_to_different_fy(client, accounts):
    fy = get_or_create_fy(client, "2019-04-01", "2020-03-31")
    other = get_or_create_fy(client, "1993-04-01", "1994-03-31")
    b, e = accounts["bank"]["id"], accounts["expense"]["id"]
    txn = _post_txn(client, make_txn(fy["id"], b, e, date="2019-06-01"))
    resp = client.put(f"/transactions/{txn['id']}", json={"date": "1993-06-01"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["fy_id"] == other["id"]
    assert data["number"].startswith("PAY-1993-")


# ── Tag filtering ──────────────────────────────────────────────────────────


def test_list_transactions_tag_filter(client, accounts):
    tag = uuid.uuid4().hex[:8]
    fy = get_or_create_fy(client, "2040-04-01", "2041-03-31")
    b, e = accounts["bank"]["id"], accounts["expense"]["id"]
    tagged_payload = make_txn(fy["id"], b, e, date="2040-06-01")
    tagged_payload["tags"] = ["wife", "personal"]
    tagged_payload["narration"] = f"Tagged txn {tag}"
    tagged = _post_txn(client, tagged_payload)

    untagged_payload = make_txn(fy["id"], b, e, date="2040-06-02")
    untagged_payload["narration"] = f"Untagged txn {tag}"
    _post_txn(client, untagged_payload)

    resp = client.get(f"/transactions?tags=wife&q={tag}")
    assert resp.status_code == 200
    ids = [t["id"] for t in resp.json()]
    assert tagged["id"] in ids
    assert len(ids) == 1


def test_list_transactions_tag_filter_handles_null_and_scalar_tags(client, session, accounts):
    from sqlalchemy import text

    tag = uuid.uuid4().hex[:8]
    fy = get_or_create_fy(client, "2041-04-01", "2042-03-31")
    b, e = accounts["bank"]["id"], accounts["expense"]["id"]

    tagged_payload = make_txn(fy["id"], b, e, date="2041-06-01")
    tagged_payload["tags"] = ["dad"]
    tagged_payload["narration"] = f"Dad tagged {tag}"
    dad_txn = _post_txn(client, tagged_payload)

    null_payload = make_txn(fy["id"], b, e, date="2041-06-02")
    null_payload["narration"] = f"Null tags {tag}"
    null_txn = _post_txn(client, null_payload)
    session.execute(
        text("UPDATE transaction SET tags = NULL WHERE id = :id"),
        {"id": null_txn["id"]},
    )
    session.commit()

    scalar_payload = make_txn(fy["id"], b, e, date="2041-06-03")
    scalar_payload["narration"] = f"Scalar tags {tag}"
    scalar_txn = _post_txn(client, scalar_payload)
    session.execute(
        text("UPDATE transaction SET tags = '\"dad\"'::json WHERE id = :id"),
        {"id": scalar_txn["id"]},
    )
    session.commit()

    resp = client.get(f"/transactions?tags=dad&q={tag}")
    assert resp.status_code == 200
    ids = [t["id"] for t in resp.json()]
    assert ids == [dad_txn["id"]]
