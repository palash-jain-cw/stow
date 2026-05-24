import uuid
from datetime import date

import pytest

from tests.helpers import get_or_create_account, get_or_create_fy, get_or_create_group, fy_bounds_for_date


def _fd_payload(client, **overrides):
    get_or_create_group(client, "Bank Accounts", "asset")
    bank = get_or_create_account(client, f"FD Bank {uuid.uuid4().hex[:8]}", "Bank Accounts")
    txn_date = overrides.get("date") or overrides.get("start_date") or "2025-06-01"
    if isinstance(txn_date, date):
        txn_date = txn_date.isoformat()
    fy_start, fy_end = fy_bounds_for_date(date.fromisoformat(txn_date))
    fy = get_or_create_fy(client, fy_start, fy_end)
    base = {
        "name": f"SBI FD {uuid.uuid4().hex[:8]}",
        "principal": 500_000_000,
        "interest_rate": 750,
        "start_date": txn_date,
        "maturity_date": "2026-01-15",
        "compounding": "quarterly",
        "from_account_id": bank["id"],
        "fy_id": fy["id"],
        "date": txn_date,
    }
    merged = {**base, **overrides}
    if "date" not in overrides and "start_date" in overrides:
        merged["date"] = merged["start_date"]
    if isinstance(merged.get("date"), date):
        merged["date"] = merged["date"].isoformat()
    if isinstance(merged.get("start_date"), date):
        merged["start_date"] = merged["start_date"].isoformat()
    if isinstance(merged.get("maturity_date"), date):
        merged["maturity_date"] = merged["maturity_date"].isoformat()
    # Re-resolve FY if date changed via overrides
    d = date.fromisoformat(merged["date"])
    fy_start, fy_end = fy_bounds_for_date(d)
    merged["fy_id"] = get_or_create_fy(client, fy_start, fy_end)["id"]
    return merged


def _create_fd(client, **overrides):
    resp = client.post("/investments/fds", json=_fd_payload(client, **overrides))
    assert resp.status_code == 201, resp.text
    return resp.json()


# ── Slice 1: POST /investments/fds creates account + metadata ─────────────────


def test_create_fd_returns_201_with_fd_fields(client):
    payload = _fd_payload(client)
    data = _create_fd(client, **payload)
    assert data["name"] == payload["name"]
    assert data["principal"] == 500_000_000
    assert data["interest_rate"] == 750
    assert data["start_date"] == payload["start_date"]
    assert data["maturity_date"] == "2026-01-15"
    assert data["compounding"] == "quarterly"
    assert data["status"] == "active"
    assert "account_id" in data


def test_create_fd_status_defaults_to_active(client):
    assert _create_fd(client)["status"] == "active"


def test_create_fd_account_has_fd_subtype(client):
    data = _create_fd(client)
    account = client.get(f"/accounts/{data['account_id']}").json()
    assert account["investment_subtype"] == "fd"


def test_create_fd_invalid_compounding_returns_422(client):
    resp = client.post("/investments/fds", json=_fd_payload(client, compounding="weekly"))
    assert resp.status_code == 422


# ── Slice 2: GET /investments/fds lists FDs with derived fields ───────────────


def _get_fd(client, account_id: int) -> dict:
    items = client.get("/investments/fds").json()
    return next(i for i in items if i["account_id"] == account_id)


def test_list_fds_returns_days_to_maturity_and_accrued_interest(client):
    data = _create_fd(client)
    resp = client.get("/investments/fds")
    assert resp.status_code == 200
    item = _get_fd(client, data["account_id"])
    assert "days_to_maturity" in item
    assert "accrued_interest" in item
    assert isinstance(item["days_to_maturity"], int)
    assert isinstance(item["accrued_interest"], int)


def test_days_to_maturity_positive_for_future_maturity(client):
    data = _create_fd(client, maturity_date="2099-01-01", date="2099-01-01")
    assert _get_fd(client, data["account_id"])["days_to_maturity"] > 0


def test_days_to_maturity_negative_for_past_maturity(client):
    data = _create_fd(client, start_date="2020-01-01", maturity_date="2021-01-01", date="2020-01-01")
    assert _get_fd(client, data["account_id"])["days_to_maturity"] < 0


def test_accrued_interest_is_zero_when_started_today(client):
    from datetime import date

    today = date.today().isoformat()
    data = _create_fd(client, start_date=today, date=today)
    assert _get_fd(client, data["account_id"])["accrued_interest"] == 0


def test_accrued_interest_positive_for_fd_started_in_past(client):
    data = _create_fd(client, start_date="2025-01-01", date="2025-01-01")
    assert _get_fd(client, data["account_id"])["accrued_interest"] > 0


# ── Slice 3: GET /investments/fds/maturing-soon ───────────────────────────────


def test_maturing_soon_includes_fd_within_window(client):
    from datetime import date, timedelta

    soon = (date.today() + timedelta(days=20)).isoformat()
    data = _create_fd(client, maturity_date=soon, date=soon)
    resp = client.get("/investments/fds/maturing-soon?days=30")
    assert resp.status_code == 200
    ids = [i["account_id"] for i in resp.json()]
    assert data["account_id"] in ids


def test_maturing_soon_excludes_fd_outside_window(client):
    from datetime import date, timedelta

    far = (date.today() + timedelta(days=60)).isoformat()
    data = _create_fd(client, maturity_date=far, date=far)
    ids = [i["account_id"] for i in client.get("/investments/fds/maturing-soon?days=30").json()]
    assert data["account_id"] not in ids


def test_maturing_soon_excludes_past_maturity(client):
    data = _create_fd(client, start_date="2020-01-01", maturity_date="2021-01-01", date="2020-01-01")
    ids = [i["account_id"] for i in client.get("/investments/fds/maturing-soon?days=30").json()]
    assert data["account_id"] not in ids


def test_maturing_soon_default_window_is_30_days(client):
    from datetime import date, timedelta

    soon = (date.today() + timedelta(days=15)).isoformat()
    data = _create_fd(client, maturity_date=soon, date=soon)
    ids = [i["account_id"] for i in client.get("/investments/fds/maturing-soon").json()]
    assert data["account_id"] in ids
