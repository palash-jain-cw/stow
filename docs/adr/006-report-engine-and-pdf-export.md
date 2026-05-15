# ADR 006 — Report Engine and PDF Export

**Status:** Accepted

## Context

Issue #5 adds four standard Indian accounting reports and the ability to export any of them as a styled PDF. The reports are multi-table aggregations that cut across Accounts, AccountGroups, Entries, Transactions, OpeningBalances, and FinancialYears — making them the first module complex enough to justify the Repository Pattern (per ADR 004).

## Decisions

### Reports in scope

| Report | Endpoint | Description |
|---|---|---|
| Trial Balance | `GET /reports/trial-balance?fy_id=` | All accounts: opening balance, period debits, period credits, closing balance |
| Profit & Loss | `GET /reports/profit-loss?fy_id=` | Income vs expense account groups with subtotals; net profit at bottom |
| Balance Sheet | `GET /reports/balance-sheet?fy_id=` | Assets vs liabilities + equity; net profit from FY if locked, computed live if active |
| Cash Flow | `GET /reports/cash-flow?fy_id=` | Indirect method: net profit adjusted for non-cash items and working capital movements, grouped by `cash_flow_tag` on AccountGroup |

All four reports are available as JSON. Appending `?format=pdf` to any report endpoint returns `application/pdf`.

### PDF library: WeasyPrint + Jinja2

WeasyPrint renders HTML+CSS to PDF. Jinja2 provides the HTML templates. This combination was chosen over fpdf2 (programmatic) and ReportLab because:

- HTML/CSS templates are readable, easy to maintain, and visually expressive
- WeasyPrint supports print-oriented CSS (page breaks, headers, footers, `@page` rules)
- The Docker image can be updated to install `libpango-1.0-0` and `libcairo2` (the only system-level deps)

Templates live in `src/stow/reports/templates/`. One template per report, extending a shared `base.html` that sets fonts, colour palette, page margins, and the Stow header/footer.

### Repository Pattern for report queries

`ReportRepository` encapsulates all report queries behind a clean interface:

```python
class ReportRepository:
    def __init__(self, session: Session): ...
    def trial_balance(self, fy_id: int) -> TrialBalanceReport: ...
    def profit_loss(self, fy_id: int) -> ProfitLossReport: ...
    def balance_sheet(self, fy_id: int) -> BalanceSheetReport: ...
    def cash_flow(self, fy_id: int) -> CashFlowReport: ...
```

Route handlers in `routers/reports.py` are thin: they call the repository, then optionally call `pdf.render(report)`.

### Accounting sign convention for reports

All amounts stored in paise. In the Entry model, positive = debit, negative = credit.

For report display:
- **Trial Balance**: show debits and credits in separate columns (absolute values); closing balance is debit-normal for asset/expense accounts, credit-normal for liability/equity/income.
- **P&L**: income accounts show credit balances as positive revenue; expense accounts show debit balances as positive cost.
- **Balance Sheet**: asset closing balances positive on left; liability+equity closing balances positive on right.
- **Cash Flow**: net profit from P&L as starting point; working capital movements follow standard indirect-method sign (increase in current asset = negative, increase in current liability = positive).

### Opening balance handling in reports

`OpeningBalance.amount` uses the same sign convention as entries (positive = debit). Reports add this to entry movements to get closing balance.

## Rejected Alternatives

- **fpdf2**: output quality insufficient for a polished personal finance tool; layout code is verbose and hard to maintain
- **ReportLab**: powerful but extremely verbose API; HTML templates are a better fit for the desired design quality
- **Separate PDF endpoints** (`/reports/trial-balance/pdf`): `?format=pdf` is simpler and keeps URL space clean
- **Pre-rendered PDFs stored on disk**: unnecessary for a personal tool with low request volume; render on demand
