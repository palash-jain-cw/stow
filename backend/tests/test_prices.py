from __future__ import annotations

import pytest
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def invest_group(client):
    return client.post("/account-groups", json={
        "name": "Investments", "nature": "asset", "cash_flow_tag": "investing",
    }).json()


@pytest.fixture()
def bank(client):
    grp = client.post("/account-groups", json={
        "name": "Bank", "nature": "asset", "cash_flow_tag": "operating",
    }).json()
    return client.post("/accounts", json={"name": "HDFC Bank", "group_id": grp["id"]}).json()


@pytest.fixture()
def fy(client):
    return client.post("/financial-years", json={
        "start_date": "2025-04-01", "end_date": "2026-03-31",
    }).json()


@pytest.fixture()
def mf_account(client, invest_group):
    return client.post("/accounts", json={
        "name": "PPFAS Flexi Cap Fund",
        "group_id": invest_group["id"],
        "investment_subtype": "equity_mf",
        "price_source_id": "122639",
    }).json()


@pytest.fixture()
def stock_account(client, invest_group):
    return client.post("/accounts", json={
        "name": "Reliance Industries",
        "group_id": invest_group["id"],
        "investment_subtype": "stock",
        "price_source_id": "RELIANCE",
    }).json()


# ── Slice 1: GET /prices/latest returns 404 when no quote exists ──────────────

def test_get_latest_price_returns_404_when_no_quote(client, mf_account):
    resp = client.get(f"/prices/latest/{mf_account['id']}")
    assert resp.status_code == 404


# ── Slice 2: MfapiConnector parses NAV from mfapi.in response ─────────────────

async def test_mfapi_connector_parses_nav():
    from stow.investments.prices import MfapiConnector

    fake_body = {
        "status": "SUCCESS",
        "data": [{"date": "15-05-2026", "nav": "67.5432"}],
    }
    with patch("stow.investments.prices.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_resp = MagicMock()
        mock_resp.json.return_value = fake_body
        mock_resp.raise_for_status.return_value = None
        mock_client.get = AsyncMock(return_value=mock_resp)

        price = await MfapiConnector().fetch("122639")

    assert price == 6754  # round(67.5432 * 100)


# ── Slice 3: YfinanceConnector parses price ───────────────────────────────────

async def test_yfinance_connector_parses_price():
    from stow.investments.prices import YfinanceConnector

    with patch("stow.investments.prices.yf.Ticker") as mock_cls:
        mock_ticker = MagicMock()
        mock_ticker.fast_info.last_price = 2850.75
        mock_cls.return_value = mock_ticker

        price = await YfinanceConnector().fetch("RELIANCE")

    assert price == 285075  # round(2850.75 * 100)
    mock_cls.assert_called_once_with("RELIANCE.NS")


def test_yfinance_appends_ns_suffix_only_when_missing():
    """Connector must not double-append .NS if caller already included it."""
    from stow.investments.prices import YfinanceConnector

    connector = YfinanceConnector()
    assert connector._ticker_symbol("RELIANCE") == "RELIANCE.NS"
    assert connector._ticker_symbol("RELIANCE.NS") == "RELIANCE.NS"


# ── Slice 4: POST /prices/fetch stores quote; GET /prices/latest returns it ───

def test_fetch_stores_price_for_mf_account(client, mf_account):
    with patch(
        "stow.investments.prices.MfapiConnector.fetch",
        new=AsyncMock(return_value=6750),
    ):
        resp = client.post(f"/prices/fetch/{mf_account['id']}")

    assert resp.status_code == 201
    data = resp.json()
    assert data["price"] == 6750
    assert data["source"] == "mfapi"
    assert data["account_id"] == mf_account["id"]
    assert "quote_date" in data


def test_get_latest_price_returns_stored_quote(client, mf_account):
    with patch(
        "stow.investments.prices.MfapiConnector.fetch",
        new=AsyncMock(return_value=6750),
    ):
        client.post(f"/prices/fetch/{mf_account['id']}")

    resp = client.get(f"/prices/latest/{mf_account['id']}")
    assert resp.status_code == 200
    assert resp.json()["price"] == 6750


def test_fetch_is_idempotent_on_same_day(client, mf_account):
    with patch(
        "stow.investments.prices.MfapiConnector.fetch",
        new=AsyncMock(return_value=6750),
    ):
        client.post(f"/prices/fetch/{mf_account['id']}")

    with patch(
        "stow.investments.prices.MfapiConnector.fetch",
        new=AsyncMock(return_value=6800),
    ):
        resp = client.post(f"/prices/fetch/{mf_account['id']}")

    assert resp.status_code == 201
    assert resp.json()["price"] == 6800  # updated, not duplicated

    latest = client.get(f"/prices/latest/{mf_account['id']}").json()
    assert latest["price"] == 6800


def test_fetch_returns_422_for_account_without_price_source(client, invest_group):
    acc = client.post("/accounts", json={
        "name": "No Source Fund", "group_id": invest_group["id"],
        "investment_subtype": "equity_mf",
    }).json()
    resp = client.post(f"/prices/fetch/{acc['id']}")
    assert resp.status_code == 422


# ── Slice 5: POST /prices/fetch-all fetches all accounts with price_source_id ─

def test_fetch_all_fetches_accounts_with_source(client, mf_account, stock_account):
    with patch(
        "stow.investments.prices.MfapiConnector.fetch",
        new=AsyncMock(return_value=6750),
    ), patch(
        "stow.investments.prices.YfinanceConnector.fetch",
        new=AsyncMock(return_value=285075),
    ):
        resp = client.post("/prices/fetch-all")

    assert resp.status_code == 200
    prices = resp.json()
    account_ids = {p["account_id"] for p in prices}
    assert mf_account["id"] in account_ids
    assert stock_account["id"] in account_ids


def test_fetch_all_skips_accounts_without_source(client, invest_group, mf_account):
    client.post("/accounts", json={
        "name": "No Source Fund", "group_id": invest_group["id"],
        "investment_subtype": "equity_mf",
    })

    with patch(
        "stow.investments.prices.MfapiConnector.fetch",
        new=AsyncMock(return_value=6750),
    ):
        resp = client.post("/prices/fetch-all")

    account_ids = {p["account_id"] for p in resp.json()}
    assert mf_account["id"] in account_ids


# ── Slice 6: GET /investments/{id}/portfolio with current value ───────────────

def test_portfolio_includes_current_value_and_unrealized_gain(client, fy, bank, mf_account):
    # Buy 10 units at ₹100/unit (100 paise/unit stored as cost_per_unit)
    client.post(f"/investments/{mf_account['id']}/buy", json={
        "fy_id": fy["id"],
        "date": "2025-05-01",
        "units": 10_000,        # milliunits
        "cost_per_unit": 100,   # paise per unit
        "bank_account_id": bank["id"],
        "narration": "SIP",
    })

    with patch(
        "stow.investments.prices.MfapiConnector.fetch",
        new=AsyncMock(return_value=120),  # ₹1.20/unit
    ):
        client.post(f"/prices/fetch/{mf_account['id']}")

    resp = client.get(f"/investments/{mf_account['id']}/portfolio")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    item = items[0]
    assert item["cost_basis"] == 1000        # 10_000 * 100 / 1000 paise
    assert item["current_value"] == 1200     # 10_000 * 120 / 1000 paise
    assert item["unrealized_gain"] == 200    # 1200 - 1000
    assert item["current_price_per_unit"] == 120


def test_portfolio_omits_current_value_when_no_quote(client, fy, bank, mf_account):
    client.post(f"/investments/{mf_account['id']}/buy", json={
        "fy_id": fy["id"],
        "date": "2025-05-01",
        "units": 10_000,
        "cost_per_unit": 100,
        "bank_account_id": bank["id"],
        "narration": "SIP",
    })

    resp = client.get(f"/investments/{mf_account['id']}/portfolio")
    assert resp.status_code == 200
    item = resp.json()[0]
    assert item["current_price_per_unit"] is None
    assert item["current_value"] is None
    assert item["unrealized_gain"] is None
