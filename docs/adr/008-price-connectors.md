# ADR 008 — Price Connectors (MF NAV & Stock Prices)

**Status:** Accepted  
**Date:** 2026-05-15  
**Issue:** [#7](https://github.com/palash-jain-cw/stow/issues/7)

---

## Context

To show unrealized gain in the portfolio screen we need current market prices per account. Two data sources are in scope:

- **Mutual funds (equity_mf accounts):** AMFI publishes NAV daily via the mfapi.in public API — no authentication required.
- **Stocks (stock accounts):** NSE-listed equities via the `yfinance` Python package, which wraps Yahoo Finance's unofficial endpoint.

Prices are stored so the portfolio remains viewable offline and so historical snapshots can be reconstructed.

---

## Decisions

### 1. PriceQuote model

```
price_quote(id, account_id FK, price INT, quote_date DATE, source TEXT)
UNIQUE (account_id, quote_date)
```

- `price` is paise per unit (integer, consistent with all other amounts in the system).
- `source` is `mfapi` or `yfinance` — useful for auditing data provenance.
- Upsert on `(account_id, quote_date)` so running fetch twice on the same day is idempotent.

### 2. price_source_id on Account

`Account` gains a nullable `price_source_id TEXT` column:

- For `equity_mf` accounts: AMFI scheme code (e.g. `"100033"`).
- For `stock` accounts: NSE ticker without suffix (e.g. `"INFY"`); the connector appends `.NS` for yfinance.
- `NULL` means no price fetching; portfolio shows cost basis only.

### 3. Connector interface

```python
class PriceConnector(Protocol):
    async def fetch(self, source_id: str) -> int:  # paise per unit
        ...
```

Two implementations: `MfapiConnector` (httpx GET) and `YfinanceConnector` (yfinance sync, wrapped in `asyncio.to_thread`).

`httpx` is already in dev deps; promote to production dependency. `yfinance` added as production dependency.

### 4. API surface (on-demand only)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/prices/fetch/{account_id}` | Fetch and upsert latest price for one account |
| POST | `/prices/fetch-all` | Fetch prices for all accounts with `price_source_id` |
| GET | `/prices/latest/{account_id}` | Most recent stored price quote |
| GET | `/investments/{account_id}/portfolio` | Holdings with current value + unrealized gain |

Background scheduling is out of scope for this issue; see [#21](https://github.com/palash-jain-cw/stow/issues/21).

### 5. Portfolio calculation

For each lot with `remaining_units > 0`:

```
current_value_paise = remaining_units * current_price_per_unit / 1000
cost_basis_paise    = remaining_units * cost_per_unit / 1000
unrealized_gain     = current_value_paise - cost_basis_paise
```

`current_price_per_unit` comes from the latest `price_quote` for the account. If no quote exists, `current_value` and `unrealized_gain` are `null` in the response.

---

## Integration tests

### Rationale

The connector code parses real API responses. That parsing is the only logic that can silently break when an external API changes its format. Unit tests with hardcoded fixtures catch regressions *after* someone notices; integration tests catch them proactively.

### Approach

- A separate pytest marker `integration` (`pytest -m integration`).
- Not run in CI by default. Run manually before releases or when a connector is touched.
- Each integration test makes one real outbound call, asserts the returned price is a positive integer, and does **not** write to the database.
- Tests use well-known, stable instruments expected to be around indefinitely:

| Connector | Instrument | source_id |
|-----------|-----------|-----------|
| mfapi.in | Parag Parikh Flexi Cap Fund — Direct | `"122639"` |
| yfinance | Reliance Industries | `"RELIANCE"` (→ `RELIANCE.NS`) |

### Test structure

```python
# tests/integration/test_price_connectors.py
import pytest

pytestmark = pytest.mark.integration

@pytest.mark.asyncio
async def test_mfapi_connector_returns_positive_price():
    connector = MfapiConnector()
    price = await connector.fetch("122639")
    assert isinstance(price, int)
    assert price > 0

@pytest.mark.asyncio
async def test_yfinance_connector_returns_positive_price():
    connector = YfinanceConnector()
    price = await connector.fetch("RELIANCE")
    assert isinstance(price, int)
    assert price > 0
```

Register the marker in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
markers = ["integration: calls real external APIs — run with -m integration"]
```

### What integration tests do NOT check

- Database writes (tested by unit tests with testcontainer)
- Error-handling paths (tested by unit tests with httpx mock / monkeypatching yfinance)
- Rate limits or auth errors (not applicable to these public APIs)

---

## Consequences

- `yfinance` is an unofficial Yahoo Finance wrapper; the endpoint could break without notice. The integration test will catch this before it reaches prod.
- mfapi.in is a community-maintained public API. Same caveat. The stable scheme code `122639` (PPFAS) has been published since 2017.
- `price_source_id` is freeform text; no validation of scheme code / ticker format at the API layer. Invalid values fail gracefully at fetch time with a logged error.
