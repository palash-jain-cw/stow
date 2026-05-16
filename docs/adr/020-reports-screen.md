# ADR 020 — Reports Screen

**Status:** Accepted
**Issue:** #18
**Date:** 2026-05-16

---

## Context

Issue #18 covers five report tabs driven by existing backend endpoints. Key constraints:
- All endpoints take `fy_id` (not date ranges) — period selector is FY selector only.
- Capital gains is per-account (`GET /investments/{account_id}/capital-gains`), not a global endpoint.
- PDF export: same URL with `?format=pdf` query param, opened in a new tab.

---

## Decisions

### 1. Layout

Full-width page (not two-panel). Header: "Reports" title + FY selector + Export PDF button. Below: tab strip (P&L | Balance Sheet | Trial Balance | Cash Flow | Capital Gains). Body: `flex-1 overflow-y-auto` with report content centered at `max-w-2xl` (or `max-w-4xl` for Balance Sheet).

### 2. Period selector

`<select>` populated from `GET /financial-years`. Default: active FY. Changing FY invalidates all report queries. No quarterly/custom options (backend doesn't support them).

### 3. Tab routing

`useSearchParams` from react-router-dom. Tab stored as `?tab=pl` (default). This preserves tab across page navigations.

### 4. Collapsible groups (P&L and Balance Sheet)

`collapsed: Set<string>` in `useState`, keyed by group name. Default: expanded. Click group header toggles.

### 5. P&L tab

Two sections (Income / Expenses). Each `ProfitLossGroup` renders as: collapsible group header row (group_name + subtotal) + child account rows (account_name + amount). Net Profit row at bottom (emerald if ≥ 0, red if negative).

### 6. Balance Sheet tab

Two-column grid (`grid-cols-2`). Left: liabilities + equity sections. Right: asset sections. Balance check strip at bottom.

`BalanceSheetSection.accounts` is `list[dict]` with `{account_id, account_name, amount}`.

### 7. Trial Balance tab

Flat table: Account | Group | Debit | Credit. Grand total row. Balance check (total_debit === total_credit).

### 8. Cash Flow tab

Three section headers (Operating / Investing / Financing) from `sections[].tag`. Each section's `items` rendered as label + amount rows. Net change, opening cash, closing cash at bottom.

### 9. Capital Gains tab

Since there's no global endpoint, fetch `GET /investments/{account_id}/capital-gains?fy_id=X` for every investment account (accounts where `investment_subtype` is set). Aggregate all entries.

Two sub-tables: STCG (`gain_type === 'stcg'`) and LTCG (`gain_type === 'ltcg'`). Columns: Instrument (account name) | Units sold | Sale date | Sale price/unit | Gain.

Note: Buy date and buy price are not available in `CapitalGainEntryOut` (those are on the lot record). The table omits those columns.

LTCG exemption note: fetch `GET /tax-rules` and use the `ltcg_exemption_paise` from the equity rule.

### 10. Export PDF

Button calls `window.open(`${BASE}/reports/${reportType}?fy_id=${fyId}&format=pdf`)`. Capital Gains tab shows "Export PDF not available" (no single endpoint).

### 11. Empty / loading states

- No active FY: "No financial year found." with a link to Settings.
- Report loading: skeleton placeholder rows.
- Empty report data: inline "No data for this period."

---

## Consequences

- Capital Gains tab makes N requests (one per investment account). For a personal app with < 20 investment accounts this is acceptable.
- Buy date/price are absent from the Capital Gains table — a known limitation of the `CapitalGainEntryOut` schema.
- PDF export is browser-native (new tab); no client-side PDF generation needed.
