# ADR 021 — Portfolio Screen

**Status:** Accepted
**Issue:** #19
**Date:** 2026-05-16

---

## Context

Issue #19 covers an investment portfolio overview. The backend has no global holdings endpoint; all equity/stock data is per-account. `GET /investments/ppf` does not exist — PPF tab is omitted from this build.

---

## Decisions

### 1. Tabs

Three tabs: **Equity MF** | **Stocks** | **Fixed Deposits**. PPF tab excluded (no backend endpoint).

Tab state stored in `useSearchParams` as `?tab=mf` (default `mf`).

### 2. Header — allocation bar

Fetch all accounts from `GET /accounts`. Filter by `investment_subtype`:
- Equity MF: `investment_subtype === 'equity_mf'` — use `account.balance` (cost basis)
- Stocks: `investment_subtype === 'stock'` — use `account.balance`
- FDs: `investment_subtype === 'fd'` — use `account.balance`

Total invested = sum of all three groups' balances. Stacked horizontal bar (6px height, border-radius) with coloured segments proportional to total. Legend chips below: type label + rupee amount + percentage.

Colours: Equity MF = blue-600, Stocks = violet-600, FDs = amber-600.

### 3. Equity MF tab

1. Get all `equity_mf` accounts from accounts list.
2. For each account, `GET /investments/{account_id}/portfolio` → `PortfolioItemOut[]`. Parallel via `Promise.all`.
3. Each account renders as one row in the holdings table (aggregated across lots):
   - Fund name = `account.name`
   - Units held = `sum(remaining_units) / 1000` (displayed with up to 3 decimal places)
   - Avg NAV = `cost_per_unit / 100` rupees (from any lot; all lots of same account share same avg — actually use `total_cost_basis / (total_remaining_units / 1000)` to recompute)
   - Invested = `sum(cost_basis)` paise → `<MonoAmount>`
   - Current value = `sum(current_value)` paise if all non-null, else "—"
   - Unrealized gain = `sum(unrealized_gain)` paise; emerald if ≥ 0, red if < 0
   - CG type badge: all lots with age > 365d → LTCG pill; all ≤ 365d → STCG pill; mixed → Mixed pill

4. Click account row → expand lot detail table (CSS grid 0fr → 1fr). Columns: Lot# | Units | Buy NAV | Buy date | Age (months) | Unrealized | Type.
5. Only one row expanded at a time.
6. Totals row at bottom: Invested total + Current value total + Unrealized total.

**Avg NAV computation (per account row):**
```
avgNav = total_cost_basis / (total_remaining_units / 1000)  // paise per unit
display = avgNav / 100  // rupees
```

**Age computation per lot:**
```
months = Math.floor((today - acquisition_date).days / 30.44)
isLTCG = days > 365
```

### 4. Stocks tab

Same structure as Equity MF. Label differences only: "Units held" → "Shares held", "Avg NAV" → "Avg cost", "Units" → "Shares" in lot table.

Account name used as stock identifier (e.g., "Infosys NSE: INFY").

### 5. Fixed Deposits tab

Data from `GET /investments/fds` → `FdListItemOut[]`.

Columns: Bank/FD name | Principal | Rate | Start date | Maturity date | Interest accrued | Status badge.

TDS column omitted — not present in `FdListItemOut`.

Status badge values from `fd.status`:
- `active` → emerald badge "Active"
- `matured` → zinc badge "Matured"
- any `days_to_maturity ≤ 30` and not matured → amber badge "Matures in N days"

Rows with `days_to_maturity ≤ 30` and status not matured → amber left border (`border-l-2 border-amber-400`).

Click row → expand detail: tenure (maturity - start), compounding, maturity amount (principal + accrued), days to maturity.

### 6. Loading / empty states

- Allocation bar: skeleton placeholder while accounts are loading.
- Holdings tabs: `LoadingRows` skeleton (4 rows) while portfolio data is in flight.
- No investment accounts of a subtype → inline "No {Equity MF / Stocks / Fixed Deposits} found."
- No active FY → not needed (FY not required for portfolio queries).

### 7. Data types (frontend)

```ts
interface PortfolioItemOut {
  lot_id: number
  acquisition_date: string     // ISO date
  units: number                // milliunits
  remaining_units: number      // milliunits
  cost_per_unit: number        // paise per unit
  cost_basis: number           // paise
  current_price_per_unit: number | null
  current_value: number | null // paise
  unrealized_gain: number | null // paise
}

interface FdListItemOut {
  account_id: number
  name: string
  principal: number           // paise
  interest_rate: number       // basis points (e.g. 700 = 7%)
  start_date: string
  maturity_date: string
  compounding: string
  status: string
  days_to_maturity: number
  accrued_interest: number    // paise
}
```

---

## Consequences

- PPF tab omitted; can be added later once backend endpoint exists.
- TDS column not shown in FD table (not in backend schema).
- N parallel portfolio requests per tab (one per equity/stock account). Acceptable for personal use (< 20 accounts).
- Buy date and price are available in `PortfolioItemOut` (via `acquisition_date` + `cost_per_unit`) unlike the Reports capital gains table.
