import pytest


@pytest.fixture()
def account_id(client):
    grp = client.post("/account-groups", json={"name": "Bank Accounts", "nature": "asset"}).json()
    acc = client.post("/accounts", json={"name": "HDFC Bank", "group_id": grp["id"]}).json()
    return acc["id"]


def test_get_opening_balance_default_zero(client, account_id):
    resp = client.get(f"/accounts/{account_id}/opening-balance?fy_id=1")
    assert resp.status_code == 200
    assert resp.json()["amount"] == 0


def test_put_opening_balance(client, account_id):
    resp = client.put(
        f"/accounts/{account_id}/opening-balance",
        json={"fy_id": 1, "amount": 100000},
    )
    assert resp.status_code == 200
    assert resp.json()["amount"] == 100000


def test_get_returns_updated_balance(client, account_id):
    client.put(f"/accounts/{account_id}/opening-balance", json={"fy_id": 1, "amount": 50000})
    resp = client.get(f"/accounts/{account_id}/opening-balance?fy_id=1")
    assert resp.json()["amount"] == 50000
