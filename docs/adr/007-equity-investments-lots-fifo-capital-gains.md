# ADR 007 — Equity Investments: Lots, FIFO, and Capital Gains

**Status:** Accepted

## Context

Issue #6 adds tracking for equity mutual funds and direct stocks. These instruments require:
- Recording purchase lots (units, cost per unit, acquisition date)
- FIFO consumption when units are sold
- Automatic STCG/LTCG classification based on holding period
- A versioned tax rule table so historical gains use the rate effective on the sale date, not today's rate
- A capital gains report suitable for ITR Schedule CG

Scope is `investment_subtype` values `equity_mf` and `stock` on `Account`. Fixed deposits and PPF are addressed in issue #8.

## Decisions

### Unit representation: milliunits

MF units carry up to 3 decimal places (e.g. 12.345 units). Units are stored as integers in **milliunits** (1 unit = 1000 milliunits) to keep all arithmetic in integers, consistent with the paise convention for amounts.

```
12.345 units → 12345 milliunits
cost_per_unit stored in paise per milliunit
total cost = units_milliunits × cost_per_unit_paise_per_milliunit / 1000
```

### New models

**Lot** — one row per purchase:
```
id, account_id, transaction_id (FK → transaction)
acquisition_date: date
units: int              # milliunits, total purchased
cost_per_unit: int      # paise per milliunit
remaining_units: int    # decremented on sale; 0 = fully consumed
```

**CapitalGainEntry** — one row per lot consumed during a sale:
```
id, lot_id, sale_transaction_id (FK → transaction)
units_sold: int         # milliunits consumed from this lot
sale_date: date
sale_price_per_unit: int  # paise per milliunit at time of sale
gain: int               # paise, signed (negative = loss)
gain_type: str          # stcg | ltcg
```

**CapitalGainsTaxRule** — versioned tax parameters:
```
id
asset_type: str                # equity | debt
holding_threshold_days: int    # days ≥ this → ltcg (365 for equity)
stcg_rate_bps: int             # basis points (2000 = 20%)
ltcg_rate_bps: int             # basis points (1250 = 12.5%)
ltcg_exemption_paise: int      # paise (12_500_000 = ₹1.25L)
effective_from: date
```

Rule lookup: `MAX(effective_from) WHERE effective_from <= sale_date AND asset_type = ?`.
No `effective_until` column — inserting a new row with a later `effective_from` supersedes the old rule for all dates on or after it.

### Seed data: capital gains accounts

The sell operation automatically routes gains and losses to named income/expense accounts seeded at startup:

| Account name | Group | Nature |
|---|---|---|
| Short Term Capital Gains | Capital Gains | income |
| Long Term Capital Gains | Capital Gains | income |
| Capital Loss | Capital Gains | expense |

The sell endpoint does not accept a `gain_account_id` parameter — routing is determined by the computed `gain_type`.

### Seed data: tax rule versions (equity)

| effective_from | stcg | ltcg | ltcg exemption |
|---|---|---|---|
| 2018-02-01 | 15% (1500 bps) | 10% (1000 bps) | ₹1,00,000 |
| 2024-07-23 | 20% (2000 bps) | 12.5% (1250 bps) | ₹1,25,000 |

Future budget changes: insert a new row. No code change required.

### Double-entry on buy

```
Dr  Investment account (cost basis)
  Cr  Bank / source account
```

### Double-entry on sell

Gain case:
```
Dr  Bank / destination account       (sale proceeds)
  Cr  Investment account             (cost basis of lots consumed)
  Cr  Short/Long Term Capital Gains  (gain)
```

Loss case:
```
Dr  Bank / destination account       (sale proceeds)
Dr  Capital Loss                     (loss, absolute value)
  Cr  Investment account             (cost basis of lots consumed)
```

### FIFO algorithm

1. Load open lots for the account ordered by `acquisition_date ASC`, then `id ASC` (tie-break).
2. Walk lots until `units_to_sell` is exhausted.
3. Per lot: `units_consumed = min(lot.remaining_units, units_to_sell_remaining)`.
4. `holding_days = (sale_date - lot.acquisition_date).days`.
5. Look up `CapitalGainsTaxRule` effective on `sale_date` for the account's `investment_subtype`-mapped asset type.
6. `gain_type = "ltcg" if holding_days >= rule.holding_threshold_days else "stcg"`.
7. `gain = (sale_price_per_unit - lot.cost_per_unit) * units_consumed // 1000`.
8. Create `CapitalGainEntry`; decrement `lot.remaining_units`.
9. If total remaining units across all open lots < `units_to_sell` → reject 422 before touching any lot.

### API surface

| Method | Path | Description |
|---|---|---|
| `POST` | `/investments/{account_id}/buy` | Record purchase — creates Lot + transaction |
| `POST` | `/investments/{account_id}/sell` | Record sale — FIFO consumes lots, creates CapitalGainEntry rows + transaction |
| `GET` | `/investments/{account_id}/holdings` | Open lots with cost basis and remaining units |
| `GET` | `/investments/{account_id}/capital-gains?fy_id=` | CapitalGainEntry rows for the FY, with STCG/LTCG totals |
| `GET` | `/reports/capital-gains?fy_id=` | Cross-account CG summary for ITR Schedule CG |

### Repository pattern

`LotRepository` per ADR 004. Route handlers call the repository; FIFO logic lives entirely inside `sell()`.

## Rejected Alternatives

- **Weighted Average Cost (WAC)**: FIFO is required for Indian capital gains tax; WAC is not acceptable for ITR purposes.
- **Storing gain_type computed eagerly at buy time**: gain_type depends on sale_date, which is unknown at purchase. It must be computed at sell time.
- **effective_until column on tax rules**: Adds maintenance burden (every new rule requires updating the previous row's `effective_until`). `MAX(effective_from) <= sale_date` is simpler and equally correct.
- **Explicit gain_account_id on sell**: Forces caller to know the tax classification before the system computes it. The system determines the account from the computed gain_type.
- **Float for units**: Floats cause rounding errors in FIFO arithmetic. Milliunits keep all math integer-exact.
