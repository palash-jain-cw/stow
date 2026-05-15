# ADR 005 — Financial Year Lifecycle and Year-End Closing

**Status:** Accepted

## Context

At the end of each financial year, income and expense (P&L) account balances need to be cleared and the net profit needs to flow into equity. There are two standard approaches:

**Option A — Explicit closing Journal entry:**
Post a synthetic Journal transaction in the old FY that debits every income account, credits every expense account, and posts the net difference to Retained Earnings. This zeroes out P&L accounts in the old FY's ledger.

**Option B — Opening balance carry-forward:**
At lock time, calculate net profit and store it on the FY record. When creating the new FY, carry forward balance sheet closing balances as opening balances, and set Retained Earnings opening balance = prior Retained Earnings + net profit. P&L accounts always start a new FY at zero with no explicit entry.

## Decision

**Option B — Opening balance carry-forward.**

### FY lock (`POST /financial-years/{id}/lock`)
1. Calculates net profit: `sum of all entry amounts on income/expense accounts` for the FY.
2. Stores `net_profit` (paise) on the `FinancialYear` record.
3. Sets `status = locked`. All transactions in the FY become read-only.
4. No transaction or Journal entry is posted.

### New FY opening balances (`POST /financial-years/{id}/prefill-opening-balances`)
Copies the closing balance of every balance sheet account (asset, liability, equity) from the prior locked FY into the new FY's opening balances. Sets:

```
Retained Earnings opening balance =
    prior FY Retained Earnings opening balance
    + prior FY closing balance adjustments
    + prior FY net_profit
```

P&L accounts (income, expense) are excluded — their opening balance is always zero and they never appear in the opening balance entry screen.

The user reviews and confirms the pre-filled opening balances before they take effect.

## Why Option A was rejected

1. **Synthetic transactions pollute the audit log.** The user never entered a closing Journal — posting one on their behalf breaks the principle that every transaction represents a real event.
2. **No real money movement.** The balance in HDFC Bank does not change at year end. A Journal entry moving money between ledger accounts is an accounting artefact, not a bookkeeping event.
3. **User control.** Option B gives the user explicit visibility over what carries forward. They can correct opening balances before the new FY goes active.

## Consequences

- `FinancialYear` carries a `net_profit` field (nullable integer, paise) set at lock time.
- The pre-fill endpoint is a convenience helper; opening balances remain fully editable until the first transaction is posted in the new FY.
- `Retained Earnings` is a pre-seeded account under `Reserves & Surplus`. Its balance grows year-over-year through accumulated opening balances, not through posting entries.
- P&L account opening balances are always zero and are not shown in the opening balance entry screen.
