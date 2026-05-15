import pytest


@pytest.fixture()
def investments_group(client):
    return client.get("/account-groups").json()


def _fd_payload(**overrides):
    base = {
        "name": "SBI FD",
        "principal": 500_000_000,   # ₹5,00,000 in paise
        "interest_rate": 750,        # 7.50% p.a. in bps
        "start_date": "2025-01-15",
        "maturity_date": "2026-01-15",
        "compounding": "quarterly",
    }
    return {**base, **overrides}


# ── Slice 1: POST /investments/fds creates account + metadata ─────────────────

def test_create_fd_returns_201_with_fd_fields(client):
    resp = client.post("/investments/fds", json=_fd_payload())
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "SBI FD"
    assert data["principal"] == 500_000_000
    assert data["interest_rate"] == 750
    assert data["start_date"] == "2025-01-15"
    assert data["maturity_date"] == "2026-01-15"
    assert data["compounding"] == "quarterly"
    assert data["status"] == "active"
    assert "account_id" in data


def test_create_fd_status_defaults_to_active(client):
    resp = client.post("/investments/fds", json=_fd_payload())
    assert resp.json()["status"] == "active"


def test_create_fd_account_has_fd_subtype(client):
    data = client.post("/investments/fds", json=_fd_payload()).json()
    account = client.get(f"/accounts/{data['account_id']}").json()
    assert account["investment_subtype"] == "fd"


def test_create_fd_invalid_compounding_returns_422(client):
    resp = client.post("/investments/fds", json=_fd_payload(compounding="weekly"))
    assert resp.status_code == 422


# ── Slice 2: GET /investments/fds lists FDs with derived fields ───────────────

def _get_fd(client, account_id: int) -> dict:
    items = client.get("/investments/fds").json()
    return next(i for i in items if i["account_id"] == account_id)


def test_list_fds_returns_days_to_maturity_and_accrued_interest(client):
    account_id = client.post("/investments/fds", json=_fd_payload()).json()["account_id"]
    resp = client.get("/investments/fds")
    assert resp.status_code == 200
    item = _get_fd(client, account_id)
    assert "days_to_maturity" in item
    assert "accrued_interest" in item
    assert isinstance(item["days_to_maturity"], int)
    assert isinstance(item["accrued_interest"], int)


def test_days_to_maturity_positive_for_future_maturity(client):
    account_id = client.post("/investments/fds", json=_fd_payload(
        maturity_date="2099-01-01",
    )).json()["account_id"]
    assert _get_fd(client, account_id)["days_to_maturity"] > 0


def test_days_to_maturity_negative_for_past_maturity(client):
    account_id = client.post("/investments/fds", json=_fd_payload(
        start_date="2020-01-01",
        maturity_date="2021-01-01",
    )).json()["account_id"]
    assert _get_fd(client, account_id)["days_to_maturity"] < 0


def test_accrued_interest_is_zero_when_started_today(client):
    from datetime import date
    account_id = client.post("/investments/fds", json=_fd_payload(
        start_date=date.today().isoformat(),
    )).json()["account_id"]
    assert _get_fd(client, account_id)["accrued_interest"] == 0


def test_accrued_interest_positive_for_fd_started_in_past(client):
    account_id = client.post("/investments/fds", json=_fd_payload(
        start_date="2025-01-01",
    )).json()["account_id"]
    assert _get_fd(client, account_id)["accrued_interest"] > 0


# ── Slice 3: GET /investments/fds/maturing-soon ───────────────────────────────

def test_maturing_soon_includes_fd_within_window(client):
    from datetime import date, timedelta
    soon = (date.today() + timedelta(days=20)).isoformat()
    account_id = client.post("/investments/fds", json=_fd_payload(
        maturity_date=soon,
    )).json()["account_id"]
    resp = client.get("/investments/fds/maturing-soon?days=30")
    assert resp.status_code == 200
    ids = [i["account_id"] for i in resp.json()]
    assert account_id in ids


def test_maturing_soon_excludes_fd_outside_window(client):
    from datetime import date, timedelta
    far = (date.today() + timedelta(days=60)).isoformat()
    account_id = client.post("/investments/fds", json=_fd_payload(
        maturity_date=far,
    )).json()["account_id"]
    ids = [i["account_id"] for i in client.get("/investments/fds/maturing-soon?days=30").json()]
    assert account_id not in ids


def test_maturing_soon_excludes_past_maturity(client):
    account_id = client.post("/investments/fds", json=_fd_payload(
        start_date="2020-01-01",
        maturity_date="2021-01-01",
    )).json()["account_id"]
    ids = [i["account_id"] for i in client.get("/investments/fds/maturing-soon?days=30").json()]
    assert account_id not in ids


def test_maturing_soon_default_window_is_30_days(client):
    from datetime import date, timedelta
    soon = (date.today() + timedelta(days=15)).isoformat()
    account_id = client.post("/investments/fds", json=_fd_payload(
        maturity_date=soon,
    )).json()["account_id"]
    # No ?days= param — should use 30-day default
    ids = [i["account_id"] for i in client.get("/investments/fds/maturing-soon").json()]
    assert account_id in ids
