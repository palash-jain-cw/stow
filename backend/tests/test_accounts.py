import pytest

from tests.helpers import get_or_create_fy, get_or_create_group, get_or_create_account, set_only_active_fy


@pytest.fixture()
def group_id(client):
    group = get_or_create_group(client, "Accounts Test Banks", "asset")
    return group["id"]


def test_create_account(client, group_id):
    resp = client.post("/accounts", json={"name": "HDFC Bank", "group_id": group_id})
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "HDFC Bank"
    assert data["is_archived"] is False
    assert data["currency"] == "INR"


def test_list_accounts(client, group_id):
    client.post("/accounts", json={"name": "Axis Bank", "group_id": group_id})
    resp = client.get("/accounts")
    names = [a["name"] for a in resp.json()]
    assert "Axis Bank" in names


def test_get_account_by_id(client, group_id):
    created = client.post("/accounts", json={"name": "HDFC Bank", "group_id": group_id}).json()
    resp = client.get(f"/accounts/{created['id']}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "HDFC Bank"


def test_update_account(client, group_id):
    created = client.post("/accounts", json={"name": "Old", "group_id": group_id}).json()
    resp = client.put(f"/accounts/{created['id']}", json={"name": "New", "group_id": group_id})
    assert resp.status_code == 200
    assert resp.json()["name"] == "New"


def test_list_accounts_excludes_archived_by_default(client, group_id):
    created = client.post("/accounts", json={"name": "Hidden", "group_id": group_id}).json()
    client.post(f"/accounts/{created['id']}/archive")
    resp = client.get("/accounts")
    names = [a["name"] for a in resp.json()]
    assert "Hidden" not in names


def test_list_accounts_includes_archived_when_requested(client, group_id):
    created = client.post("/accounts", json={"name": "Archived", "group_id": group_id}).json()
    client.post(f"/accounts/{created['id']}/archive")
    resp = client.get("/accounts?include_archived=true")
    names = [a["name"] for a in resp.json()]
    assert "Archived" in names


def test_position_scope_sums_entries_across_financial_years(client, group_id, session):
    fy_a = get_or_create_fy(client, "2001-04-01", "2002-03-31", status="active")
    fy_b = get_or_create_fy(client, "2002-04-01", "2003-03-31", status="open")
    exp_grp = get_or_create_group(client, "Scope Expenses", "expense")
    bank = client.post("/accounts", json={"name": "Scope Bank", "group_id": group_id}).json()
    expense = client.post("/accounts", json={"name": "Scope Expense", "group_id": exp_grp["id"]}).json()

    client.post("/transactions", json={
        "type": "payment",
        "date": "2001-06-01",
        "narration": "Prior FY",
        "fy_id": fy_a["id"],
        "entries": [
            {"account_id": expense["id"], "amount": 10000},
            {"account_id": bank["id"], "amount": -10000},
        ],
    })
    client.post("/transactions", json={
        "type": "payment",
        "date": "2002-06-01",
        "narration": "Later FY",
        "fy_id": fy_b["id"],
        "entries": [
            {"account_id": expense["id"], "amount": 5000},
            {"account_id": bank["id"], "amount": -5000},
        ],
    })
    set_only_active_fy(session, fy_b["id"])

    active = next(a for a in client.get("/accounts").json() if a["id"] == bank["id"])
    position = next(a for a in client.get("/accounts?scope=position").json() if a["id"] == bank["id"])

    assert active["balance"] == -5000
    assert position["balance"] == -15000


def test_position_scope_uses_active_entries_when_ob_carry_forward(client, group_id, session):
    """After OB carry-forward, position must not double-count all-time entries."""
    fy_a = get_or_create_fy(client, "2003-04-01", "2004-03-31", status="active")
    fy_b = get_or_create_fy(client, "2004-04-01", "2005-03-31", status="open")
    exp_grp = get_or_create_group(client, "Carry Expenses", "expense")
    bank = client.post("/accounts", json={"name": "Carry Bank", "group_id": group_id}).json()
    expense = client.post("/accounts", json={"name": "Carry Expense", "group_id": exp_grp["id"]}).json()

    client.post("/transactions", json={
        "type": "payment",
        "date": "2003-06-01",
        "narration": "Prior FY",
        "fy_id": fy_a["id"],
        "entries": [
            {"account_id": expense["id"], "amount": 10000},
            {"account_id": bank["id"], "amount": -10000},
        ],
    })
    client.put(
        f"/accounts/{bank['id']}/opening-balance",
        json={"fy_id": fy_b["id"], "amount": -10000},
    )
    client.post("/transactions", json={
        "type": "payment",
        "date": "2004-06-01",
        "narration": "Later FY",
        "fy_id": fy_b["id"],
        "entries": [
            {"account_id": expense["id"], "amount": 5000},
            {"account_id": bank["id"], "amount": -5000},
        ],
    })
    set_only_active_fy(session, fy_b["id"])

    position = next(
        a for a in client.get("/accounts?scope=position").json() if a["id"] == bank["id"]
    )
    assert position["balance"] == -15000
