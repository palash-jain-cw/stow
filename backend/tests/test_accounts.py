import pytest


@pytest.fixture()
def group_id(client):
    resp = client.post("/account-groups", json={"name": "Bank Accounts", "nature": "asset"})
    return resp.json()["id"]


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
