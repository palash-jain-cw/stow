from __future__ import annotations

from sqlmodel import Session, col, select
from sqlalchemy import func

from stow.models import Account, AccountGroup, Entry, FinancialYear, OpeningBalance, Transaction
from stow.reports.schemas import (
    TrialBalanceReport,
    TrialBalanceRow,
    ProfitLossReport,
    ProfitLossGroup,
    BalanceSheetReport,
    BalanceSheetSection,
    CashFlowReport,
    CashFlowSection,
)


class ReportRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def _get_fy(self, fy_id: int) -> FinancialYear:
        fy = self._s.get(FinancialYear, fy_id)
        if fy is None:
            raise ValueError(f"FinancialYear {fy_id} not found")
        return fy

    def _opening_balances(self, fy_id: int) -> dict[int, int]:
        rows = self._s.exec(
            select(OpeningBalance).where(col(OpeningBalance.fy_id) == fy_id)
        ).all()
        return {r.account_id: r.amount for r in rows}

    def _entry_movements(self, fy_id: int) -> dict[int, int]:
        """Net entry amount per account for transactions in this FY (signed, Dr positive)."""
        stmt = (
            select(col(Entry.account_id), func.sum(col(Entry.amount)).label("net"))
            .join(Transaction, col(Entry.transaction_id) == col(Transaction.id))
            .where(col(Transaction.fy_id) == fy_id)
            .group_by(col(Entry.account_id))
        )
        return {account_id: int(net) for account_id, net in self._s.exec(stmt).all()}

    def trial_balance(self, fy_id: int) -> TrialBalanceReport:
        fy = self._get_fy(fy_id)
        accounts = self._s.exec(select(Account)).all()
        groups = {g.id: g for g in self._s.exec(select(AccountGroup)).all()}
        opening = self._opening_balances(fy_id)
        movements = self._entry_movements(fy_id)

        rows: list[TrialBalanceRow] = []
        for acc in accounts:
            ob = opening.get(acc.id or 0, 0)
            net = movements.get(acc.id or 0, 0)
            # net = debit entries + credit entries (signed); split into columns
            period_debit  = max(net, 0)
            period_credit = max(-net, 0)
            closing = ob + net
            grp = groups[acc.group_id]
            rows.append(TrialBalanceRow(
                account_id=acc.id or 0,
                account_name=acc.name,
                group_name=grp.name,
                nature=grp.nature,
                opening_balance=ob,
                debit=period_debit,
                credit=period_credit,
                closing_balance=closing,
            ))

        # Trial balance totals: sum of all debit-side closing balances = sum of all credit-side
        # Express as total_debit / total_credit on the period movements + opening columns
        # Standard TB: total debit column = total credit column
        total_debit  = sum(r.opening_balance for r in rows if r.opening_balance > 0) \
                     + sum(r.debit for r in rows)
        total_credit = sum(-r.opening_balance for r in rows if r.opening_balance < 0) \
                     + sum(r.credit for r in rows)

        return TrialBalanceReport(
            fy_id=fy_id,
            fy_start_date=fy.start_date,
            fy_end_date=fy.end_date,
            rows=rows,
            total_debit=total_debit,
            total_credit=total_credit,
        )

    def profit_loss(self, fy_id: int) -> ProfitLossReport:
        fy = self._get_fy(fy_id)
        tb = self.trial_balance(fy_id)

        income_groups: dict[str, list] = {}
        expense_groups: dict[str, list] = {}

        for row in tb.rows:
            if row.nature == "income":
                income_groups.setdefault(row.group_name, []).append(row)
            elif row.nature == "expense":
                expense_groups.setdefault(row.group_name, []).append(row)

        def make_groups(groups_map: dict, negate: bool) -> list[ProfitLossGroup]:
            result = []
            for gname, rows in groups_map.items():
                accounts = []
                for r in rows:
                    amt = -r.closing_balance if negate else r.closing_balance
                    accounts.append({"account_id": r.account_id, "account_name": r.account_name, "amount": amt})
                subtotal = sum(a["amount"] for a in accounts)
                nature = rows[0].nature
                result.append(ProfitLossGroup(group_name=gname, nature=nature, accounts=accounts, subtotal=subtotal))
            return result

        # Income: credit-normal → negate closing_balance to get positive income figure
        income_pl = make_groups(income_groups, negate=True)
        # Expense: debit-normal → closing_balance already positive
        expense_pl = make_groups(expense_groups, negate=False)

        total_income   = sum(g.subtotal for g in income_pl)
        total_expenses = sum(g.subtotal for g in expense_pl)

        return ProfitLossReport(
            fy_id=fy_id,
            fy_start_date=fy.start_date,
            fy_end_date=fy.end_date,
            income_groups=income_pl,
            expense_groups=expense_pl,
            total_income=total_income,
            total_expenses=total_expenses,
            net_profit=total_income - total_expenses,
        )

    def balance_sheet(self, fy_id: int) -> BalanceSheetReport:
        fy = self._get_fy(fy_id)
        tb = self.trial_balance(fy_id)
        pl = self.profit_loss(fy_id)

        asset_map: dict[str, list] = {}
        liability_map: dict[str, list] = {}
        equity_map: dict[str, list] = {}

        for row in tb.rows:
            if row.nature == "asset":
                asset_map.setdefault(row.group_name, []).append(row)
            elif row.nature == "liability":
                liability_map.setdefault(row.group_name, []).append(row)
            elif row.nature == "equity":
                equity_map.setdefault(row.group_name, []).append(row)

        def make_sections(groups_map: dict, negate: bool) -> list[BalanceSheetSection]:
            result = []
            for gname, rows in groups_map.items():
                accounts = []
                for r in rows:
                    amt = -r.closing_balance if negate else r.closing_balance
                    accounts.append({"account_id": r.account_id, "account_name": r.account_name, "amount": amt})
                subtotal = sum(a["amount"] for a in accounts)
                nature = rows[0].nature
                result.append(BalanceSheetSection(group_name=gname, nature=nature, accounts=accounts, subtotal=subtotal))
            return result

        asset_sections     = make_sections(asset_map, negate=False)
        liability_sections = make_sections(liability_map, negate=True)
        equity_sections    = make_sections(equity_map, negate=True)

        # Net profit goes into equity (retained earnings)
        if pl.net_profit != 0:
            equity_sections.append(BalanceSheetSection(
                group_name="Retained Earnings",
                nature="equity",
                accounts=[{"account_id": 0, "account_name": "Net Profit / (Loss)", "amount": pl.net_profit}],
                subtotal=pl.net_profit,
            ))

        total_assets = sum(s.subtotal for s in asset_sections)
        rhs_before_obe = (
            sum(s.subtotal for s in liability_sections)
            + sum(s.subtotal for s in equity_sections)
        )

        # Opening balances for balance-sheet accounts may have no counterpart entry
        # (ADR 005: first-year opening balances set per-account, not via double-entry).
        # Opening Balance Equity is the plug that makes the equation hold, equal to
        # the net equity implied by all opening balances that were not explicitly
        # posted to equity accounts.
        obe = total_assets - rhs_before_obe
        if obe != 0:
            equity_sections.append(BalanceSheetSection(
                group_name="Opening Balance Equity",
                nature="equity",
                accounts=[{"account_id": 0, "account_name": "Opening Balance Equity", "amount": obe}],
                subtotal=obe,
            ))

        total_liabilities_and_equity = rhs_before_obe + obe

        return BalanceSheetReport(
            fy_id=fy_id,
            as_of_date=fy.end_date,
            asset_sections=asset_sections,
            liability_sections=liability_sections,
            equity_sections=equity_sections,
            total_assets=total_assets,
            total_liabilities_and_equity=total_liabilities_and_equity,
        )

    def cash_flow(self, fy_id: int) -> CashFlowReport:
        fy = self._get_fy(fy_id)
        pl = self.profit_loss(fy_id)
        groups = {g.id: g for g in self._s.exec(select(AccountGroup)).all()}
        accounts = self._s.exec(select(Account)).all()
        movements = self._entry_movements(fy_id)
        opening = self._opening_balances(fy_id)

        # Cash accounts (nature=asset, cash_flow_tag=operating) are the measure of cash itself.
        # They must be excluded from working-capital adjustments — their movement IS the result
        # that the three sections should reconcile to.
        cash_account_ids = {
            acc.id
            for acc in accounts
            if groups[acc.group_id].nature == "asset"
            and groups[acc.group_id].cash_flow_tag == "operating"
        }
        opening_cash = sum(opening.get(aid or 0, 0) for aid in cash_account_ids)

        # Group non-cash balance-sheet account movements by cash_flow_tag
        tagged: dict[str, list[dict]] = {"operating": [], "investing": [], "financing": []}

        for acc in accounts:
            if acc.id in cash_account_ids:
                continue  # cash itself — not an adjustment
            grp = groups[acc.group_id]
            if grp.nature in ("income", "expense"):
                continue  # captured in net_profit
            tag = grp.cash_flow_tag
            if tag not in tagged:
                continue
            net = movements.get(acc.id or 0, 0)
            if net == 0:
                continue
            # Indirect method: increase in any non-cash BS account is a use/source of cash.
            # Both asset and liability cases map to cf_amount = -net because liabilities
            # store their increase as Cr (negative net), so negating gives a positive inflow.
            cf_amount = -net
            tagged[tag].append({"label": acc.name, "amount": cf_amount})

        sections: list[CashFlowSection] = []
        for tag in ("operating", "investing", "financing"):
            items = tagged[tag]
            subtotal = sum(i["amount"] for i in items)
            sections.append(CashFlowSection(tag=tag, items=items, subtotal=subtotal))

        # Add net profit as first item in operating section, then compute net change
        op_section = sections[0]
        op_section.items.insert(0, {"label": "Net Profit / (Loss)", "amount": pl.net_profit})
        op_section.subtotal += pl.net_profit
        net_change = sum(s.subtotal for s in sections)

        return CashFlowReport(
            fy_id=fy_id,
            fy_start_date=fy.start_date,
            fy_end_date=fy.end_date,
            net_profit=pl.net_profit,
            sections=sections,
            net_change_in_cash=net_change,
            opening_cash=opening_cash,
            closing_cash=opening_cash + net_change,
        )
