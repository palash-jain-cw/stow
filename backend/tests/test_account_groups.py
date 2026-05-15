def test_list_account_groups_empty(client):
    response = client.get("/account-groups")
    assert response.status_code == 200
    assert response.json() == []


def test_create_account_group(client):
    payload = {"name": "Bank Accounts", "nature": "asset", "sort_order": 1}
    response = client.post("/account-groups", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Bank Accounts"
    assert data["nature"] == "asset"
    assert data["id"] is not None


def test_created_group_appears_in_list(client):
    client.post("/account-groups", json={"name": "Cash-in-Hand", "nature": "asset", "sort_order": 2})
    response = client.get("/account-groups")
    names = [g["name"] for g in response.json()]
    assert "Cash-in-Hand" in names


def test_update_account_group(client):
    created = client.post("/account-groups", json={"name": "Old Name", "nature": "asset"}).json()
    response = client.put(f"/account-groups/{created['id']}", json={"name": "New Name", "nature": "asset"})
    assert response.status_code == 200
    assert response.json()["name"] == "New Name"


def test_delete_account_group(client):
    created = client.post("/account-groups", json={"name": "To Delete", "nature": "expense"}).json()
    response = client.delete(f"/account-groups/{created['id']}")
    assert response.status_code == 204
    all_groups = client.get("/account-groups").json()
    assert not any(g["id"] == created["id"] for g in all_groups)
