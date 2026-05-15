# ADR 009 — Fixed Deposits

**Status:** Draft  
**Date:** 2026-05-15  
**Issue:** [#8](https://github.com/palash-jain-cw/stow/issues/8)

---

## Context

Issue #8 adds tracking for Fixed Deposits (FDs): term deposits with a fixed interest rate and maturity date, held at banks and NBFCs. Interest may compound monthly, quarterly, or annually (cumulative FD) or be paid out periodically (non-cumulative).

PPF is out of scope — dropped from issue #8.

FDs are modelled as Accounts with `investment_subtype = "fd"` (already noted in the `Account.investment_subtype` comment). The question is what additional metadata an FD needs and how to compute derived fields.

---

## Decisions

### 1. FD metadata: dedicated `fd_metadata` table

FDs carry instrument-level data (principal, rate, dates, compounding) that does not fit cleanly on the `Account` row and is not shared with any other instrument type.

```
fd_metadata(
    id               INT PK
    account_id       INT FK → account, UNIQUE
    principal        INT           # paise
    interest_rate    INT           # basis points (e.g. 750 = 7.50% p.a.)
    start_date       DATE
    maturity_date    DATE
    compounding      TEXT          # simple | monthly | quarterly | yearly
    status           TEXT          # active | matured | closed
)
```

**One-to-one with Account** (UNIQUE on `account_id`).

**Why basis points for interest_rate:**  
Consistent with `CapitalGainsTaxRule.stcg_rate_bps` / `ltcg_rate_bps`. Keeps all numeric fields integers; a `DECIMAL` column would be the only float in the schema.

**Why `status` is explicit:**  
`maturity_date < today` does not automatically mean the FD was closed or renewed — the user may have missed recording the maturity event. `status` is user-controlled (set manually or via a `POST /investments/fds/{id}/mature` action in a future issue). Default is `"active"`.

**`compounding` values:**
- `"simple"` — no compounding (used for some short-term FDs and interest-payout FDs)
- `"monthly"`, `"quarterly"`, `"yearly"` — standard compounding periods

### 2. FD account creation: atomic `POST /investments/fds`

`POST /investments/fds` accepts account name + group_id + all fd_metadata fields in one request body. The route handler creates the `Account` and `FdMetadata` rows in a single transaction. The FD account is tagged `investment_subtype = "fd"` and `cash_flow_tag = "investing"`.

Opening the FD (moving cash out of a bank account into the FD account) is recorded as a standard Journal or Payment transaction by the user — no special endpoint. This keeps the creation endpoint focused on instrument setup, not accounting entries.

### 3. Interest income: standard Receipt transaction

FD interest is recorded as a standard `receipt` transaction by the user:

```
Dr  Bank account (or FD account for cumulative)
  Cr  Fixed Deposit Interest Income
```

No dedicated `/investments/fds/{id}/interest` endpoint. Rationale: interest payment dates and whether the interest is reinvested vs. paid out are facts the user records; the system should not infer them from the compounding schedule.

**Seeded account added:** "Fixed Deposit Interest Income" under the existing "Other Income" account group.

### 4. Derived fields computed at query time

`GET /investments/fds` returns:

| Field | Source |
|---|---|
| `days_to_maturity` | `(maturity_date - today).days` — negative if past maturity |
| `accrued_interest` | Formula below, using `Decimal` arithmetic, returned as `int` (paise) |

**Accrued interest formula:**

```python
from decimal import Decimal

def accrued_interest(principal: int, rate_bps: int, start: date, compounding: str) -> int:
    rate = Decimal(rate_bps) / Decimal(10000)
    t_days = (date.today() - start).days
    t_years = Decimal(t_days) / Decimal(365)

    periods = {"simple": None, "monthly": 12, "quarterly": 4, "yearly": 1}
    n = periods[compounding]
    if n is None:
        interest = Decimal(principal) * rate * t_years
    else:
        interest = Decimal(principal) * ((1 + rate / n) ** (n * t_years) - 1)

    return int(interest)  # truncate to paise
```

This is an approximation (ignores actual compounding dates, leap years). It is used for display only; actual income is the sum of recorded interest receipt transactions.

### 5. Data access: direct queries, no repository

FD logic is not complex enough to justify a repository layer (per ADR 004). Route handlers query the DB directly via injected `Session`. The `accrued_interest` helper is a pure function — no DB access — and lives in `stow/investments/fd.py`.

### 6. API surface

| Method | Path | Description |
|---|---|---|
| `POST` | `/investments/fds` | Create FD account + metadata atomically |
| `GET` | `/investments/fds` | List all FDs with status, days_to_maturity, accrued_interest |
| `GET` | `/investments/fds/maturing-soon` | FDs maturing within `?days=30` (default 30) |

All endpoints live on the existing `investments` router.

---

## Rejected Alternatives

- **`interest_rate` as DECIMAL/float:** Only float in the schema; breaks the all-integer convention. bps are precise enough for Indian FD rates (typically 4.00%–9.00%, i.e. 400–900 bps).
- **Dedicated interest recording endpoint:** Forces the system to know compounding dates and cumulative-vs-payout distinction. Standard transactions are more flexible and already audited.
- **Repository for FD:** Logic is simple aggregation; indirection without abstraction (ADR 004).
- **`effective_until` on status:** Adds maintenance burden. Explicit user-set `status` field is clearer.
