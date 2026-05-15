"""
Real outbound HTTP calls — excluded from the default test run.
Run with: pytest tests/integration/ --run-integration
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


async def test_mfapi_connector_returns_positive_price():
    """Parag Parikh Flexi Cap Fund — Direct (scheme 122639, live since 2013)."""
    from stow.investments.prices import MfapiConnector

    price = await MfapiConnector().fetch("122639")
    assert isinstance(price, int)
    assert price > 0


async def test_yfinance_connector_returns_positive_price():
    """Reliance Industries NSE listing — stable blue-chip ticker."""
    from stow.investments.prices import YfinanceConnector

    price = await YfinanceConnector().fetch("RELIANCE")
    assert isinstance(price, int)
    assert price > 0
