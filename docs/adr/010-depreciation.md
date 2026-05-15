# ADR 010 — Depreciation

**Status:** Draft  
**Date:** 2026-05-15  
**Issue:** [#9](https://github.com/palash-jain-cw/stow/issues/9)

---

## Context

Issue #9 adds WDV (Written Down Value) depreciation per the Indian Income Tax Act. The system calculates how much depreciation should be charged for each fixed asset account in a given FY and surfaces this as a review summary — the user posts the journal entry manually via the standard transaction flow.

---

## Decisions

### 1. `accumulated_depreciation_account_id` on Account

Each fixed asset account is paired with its own accumulated depreciation account. The link is stored as a nullable self-FK on `Account`:

```
Account.accumulated_depreciation_account_id  INT FK → account.id  (nullable)
```

The user creates both accounts separately (fixed asset under "Fixed Assets", accumulated depreciation under the seeded "Accumulated Depreciation" group), then links them via `PUT /accounts/{id}`. No atomic creation endpoint — matches the existing pattern for account management.

Only accounts with `accumulated_depreciation_account_id IS NOT NULL` and `depreciation_rate IS NOT NULL` are included in the depreciation summary.

### 2. Opening WDV calculation

```
opening_WDV = balance_before_fy(fixed_asset_account, fy_id)
            + balance_before_fy(accumulated_depr_account, fy_id)
```

`balance_before_fy(account_id, fy_id)` =
- `OpeningBalance.amount` for `(account_id, fy_id)` if the record exists (carries in data from before Stow), else 0
- plus `SUM(Entry.amount)` for this account across all transactions whose `fy_id` is any FY other than the current one and whose FY ends before the current FY starts

The accumulated depreciation account has credit (negative) entry amounts, so adding it to the fixed asset balance naturally yields WDV.

### 3. Depreciation amount

```
depreciation = opening_WDV × depreciation_rate
```

`depreciation_rate` is stored as `float` on `Account` (already present; e.g. `0.15` = 15%). Result is truncated to `int` paise.

If `opening_WDV <= 0` the depreciation amount is 0 (fully depreciated or net credit position).

### 4. Half-year rule

Per IT Act: if an asset is acquired after October 3 of the financial year, only 50% of the normal depreciation is charged for that year.

**Detection:** find the earliest entry date across all transactions on the fixed asset account (the acquisition date). If that date falls within the current FY AND is after October 3 of the FY's start year, apply the half-year rule.

If the asset has entries in a prior FY (i.e., it was acquired before the current FY started), the half-year rule does not apply — it is already in its second or later year of ownership.

### 5. API surface

| Method | Path | Description |
|---|---|---|
| `GET` | `/depreciation/summary` | `?fy_id=` — one row per fixed asset account with linked accumulated depreciation account |
| `GET` | `/financial-years/{id}/pre-lock-check` | Depreciation warning for unposted entries |

**`GET /depreciation/summary` response row:**

```json
{
  "account_id": 1,
  "account_name": "Laptop",
  "depreciation_rate": 0.4,
  "opening_wdv": 60000000,
  "depreciation_amount": 24000000,
  "half_year_rule_applied": false,
  "suggested_dr_account_id": 5,
  "suggested_cr_account_id": 2
}
```

`suggested_dr_account_id` is the seeded "Depreciation" expense account; `suggested_cr_account_id` is the `accumulated_depreciation_account_id` of the fixed asset.

**`GET /financial-years/{id}/pre-lock-check` response:**

```json
{
  "unposted_depreciation": [
    {"account_id": 1, "account_name": "Laptop", "depreciation_amount": 24000000}
  ]
}
```

An account appears here if `depreciation_amount > 0` AND no entry exists on its `accumulated_depreciation_account_id` for transactions in this FY.

### 6. Seeded accounts

"Depreciation" account added under the "Indirect Expenses" group. This is the debit side of the suggested journal entry.

### 7. Data access: direct queries, no repository

Logic is straightforward aggregation per ADR 004. Calculation helpers are pure functions in `stow/depreciation.py`; route handlers in `stow/routers/depreciation.py` call them directly.

---

## Rejected Alternatives

- **Straight-line method:** WDV is the IT Act standard; straight-line is used in company accounts (Companies Act) but not in personal tax returns.
- **Auto-posting depreciation at year-end:** The issue specifies user review before posting. Auto-posting removes human oversight and bypasses the double-entry audit trail.
- **`depreciation_rate` in bps:** The field already exists as `float`. Changing it would be a breaking schema change with no practical benefit — depreciation rates do not require the same integer-only discipline as monetary amounts.
- **Single shared accumulated depreciation account:** Indian accounting practice pairs one accumulated depreciation contra-account per fixed asset for clean asset-level reporting.
