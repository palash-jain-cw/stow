from __future__ import annotations

from datetime import date

from sqlmodel import Session, col, select

from stow.models import (
    Account, CapitalGainEntry, CapitalGainsTaxRule,
    Entry, FinancialYear, Lot, Transaction,
)
from stow.investments.schemas import (
    BuyIn, SellIn, LotOut, CapitalGainEntryOut, HoldingOut, CapitalGainsSummary,
)

_ASSET_TYPE = {"equity_mf": "equity", "stock": "equity"}


class LotRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def _get_cg_account_id(self, name: str) -> int:
        acc = self._s.exec(select(Account).where(col(Account.name) == name)).first()
        if acc is None:
            raise RuntimeError(f"Seed account '{name}' not found — run seed_account_groups first")
        assert acc.id is not None
        return acc.id

    def _tax_rule(self, asset_type: str, sale_date: date) -> CapitalGainsTaxRule:
        rules = self._s.exec(
            select(CapitalGainsTaxRule)
            .where(col(CapitalGainsTaxRule.asset_type) == asset_type)
            .where(col(CapitalGainsTaxRule.effective_from) <= sale_date)
            .order_by(col(CapitalGainsTaxRule.effective_from).desc())
        ).first()
        if rules is None:
            raise ValueError(f"No tax rule found for asset_type={asset_type} on {sale_date}")
        return rules

    def buy(self, account_id: int, data: BuyIn) -> LotOut:
        fy = self._s.get(FinancialYear, data.fy_id)
        if fy is None:
            raise ValueError(f"FinancialYear {data.fy_id} not found")
        if fy.status == "locked":
            raise PermissionError("Cannot post to a locked financial year")

        # Activate FY on first transaction
        if fy.status == "open":
            fy.status = "active"

        total_cost = data.units * data.cost_per_unit // 1000  # paise

        txn = Transaction(
            number=self._next_number(data.fy_id, "JRN"),
            type="journal",
            date=data.date,
            narration=data.narration,
            fy_id=data.fy_id,
        )
        self._s.add(txn)
        self._s.flush()
        assert txn.id is not None

        self._s.add(Entry(transaction_id=txn.id, account_id=account_id, amount=total_cost))
        self._s.add(Entry(transaction_id=txn.id, account_id=data.bank_account_id, amount=-total_cost))

        lot = Lot(
            account_id=account_id,
            transaction_id=txn.id,
            acquisition_date=data.date,
            units=data.units,
            cost_per_unit=data.cost_per_unit,
            remaining_units=data.units,
        )
        self._s.add(lot)
        self._s.flush()
        assert lot.id is not None
        self._s.commit()

        return LotOut(
            id=lot.id,
            account_id=lot.account_id,
            transaction_id=lot.transaction_id,
            acquisition_date=lot.acquisition_date,
            units=lot.units,
            cost_per_unit=lot.cost_per_unit,
            remaining_units=lot.remaining_units,
        )

    def sell(self, account_id: int, data: SellIn) -> list[CapitalGainEntryOut]:
        fy = self._s.get(FinancialYear, data.fy_id)
        if fy is None:
            raise ValueError(f"FinancialYear {data.fy_id} not found")
        if fy.status == "locked":
            raise PermissionError("Cannot post to a locked financial year")

        acc = self._s.get(Account, account_id)
        if acc is None:
            raise ValueError(f"Account {account_id} not found")
        asset_type = _ASSET_TYPE.get(acc.investment_subtype or "")
        if asset_type is None:
            raise ValueError(f"Account {account_id} is not an equity investment account")

        open_lots = self._s.exec(
            select(Lot)
            .where(col(Lot.account_id) == account_id)
            .where(col(Lot.remaining_units) > 0)
            .order_by(col(Lot.acquisition_date).asc(), col(Lot.id).asc())
        ).all()

        total_available = sum(lot.remaining_units for lot in open_lots)
        if total_available < data.units:
            raise ValueError(
                f"Cannot sell {data.units} milliunits — only {total_available} available"
            )

        rule = self._tax_rule(asset_type, data.date)
        stcg_id = self._get_cg_account_id("Short Term Capital Gains")
        ltcg_id = self._get_cg_account_id("Long Term Capital Gains")
        loss_id = self._get_cg_account_id("Capital Loss")

        if fy.status == "open":
            fy.status = "active"

        total_proceeds = data.units * data.price_per_unit // 1000

        txn = Transaction(
            number=self._next_number(data.fy_id, "JRN"),
            type="journal",
            date=data.date,
            narration=data.narration,
            fy_id=data.fy_id,
        )
        self._s.add(txn)
        self._s.flush()
        assert txn.id is not None

        self._s.add(Entry(transaction_id=txn.id, account_id=data.bank_account_id, amount=total_proceeds))

        remaining_to_sell = data.units
        entries_out: list[CapitalGainEntryOut] = []
        total_cost_basis = 0

        for lot in open_lots:
            if remaining_to_sell <= 0:
                break
            consumed = min(lot.remaining_units, remaining_to_sell)
            holding_days = (data.date - lot.acquisition_date).days
            gain_type = "ltcg" if holding_days >= rule.holding_threshold_days else "stcg"
            gain = (data.price_per_unit - lot.cost_per_unit) * consumed // 1000
            cost_basis = lot.cost_per_unit * consumed // 1000
            total_cost_basis += cost_basis

            lot.remaining_units -= consumed
            remaining_to_sell -= consumed

            cge = CapitalGainEntry(
                lot_id=lot.id or 0,
                sale_transaction_id=txn.id,
                units_sold=consumed,
                sale_date=data.date,  # type: ignore[arg-type]
                sale_price_per_unit=data.price_per_unit,
                gain=gain,
                gain_type=gain_type,
            )
            self._s.add(cge)
            self._s.flush()
            assert cge.id is not None

            if gain >= 0:
                cg_account_id = ltcg_id if gain_type == "ltcg" else stcg_id
                if gain > 0:
                    self._s.add(Entry(transaction_id=txn.id, account_id=cg_account_id, amount=-gain))
            else:
                self._s.add(Entry(transaction_id=txn.id, account_id=loss_id, amount=-gain))

            entries_out.append(CapitalGainEntryOut(
                id=cge.id,
                lot_id=cge.lot_id,
                sale_transaction_id=cge.sale_transaction_id,
                units_sold=cge.units_sold,
                sale_date=cge.sale_date,
                sale_price_per_unit=cge.sale_price_per_unit,
                gain=cge.gain,
                gain_type=cge.gain_type,
            ))

        # Credit the investment account at cost basis
        self._s.add(Entry(transaction_id=txn.id, account_id=account_id, amount=-total_cost_basis))

        self._s.commit()
        return entries_out

    def holdings(self, account_id: int) -> list[HoldingOut]:
        lots = self._s.exec(
            select(Lot)
            .where(col(Lot.account_id) == account_id)
            .where(col(Lot.remaining_units) > 0)
            .order_by(col(Lot.acquisition_date).asc())
        ).all()
        return [
            HoldingOut(
                lot_id=lot.id or 0,
                acquisition_date=lot.acquisition_date,
                units=lot.units,
                remaining_units=lot.remaining_units,
                cost_per_unit=lot.cost_per_unit,
                cost_basis=lot.remaining_units * lot.cost_per_unit // 1000,
            )
            for lot in lots
        ]

    def capital_gains(self, account_id: int, fy_id: int) -> CapitalGainsSummary:
        fy = self._s.get(FinancialYear, fy_id)
        if fy is None:
            raise ValueError(f"FinancialYear {fy_id} not found")

        entries = self._s.exec(
            select(CapitalGainEntry)
            .join(Lot, col(CapitalGainEntry.lot_id) == col(Lot.id))
            .where(col(Lot.account_id) == account_id)
            .where(col(CapitalGainEntry.sale_date) >= fy.start_date)
            .where(col(CapitalGainEntry.sale_date) <= fy.end_date)
        ).all()

        total_stcg = sum(e.gain for e in entries if e.gain_type == "stcg" and e.gain > 0)
        total_ltcg = sum(e.gain for e in entries if e.gain_type == "ltcg" and e.gain > 0)
        total_loss = sum(-e.gain for e in entries if e.gain < 0)

        return CapitalGainsSummary(
            fy_id=fy_id,
            entries=[
                CapitalGainEntryOut(
                    id=e.id or 0,
                    lot_id=e.lot_id,
                    sale_transaction_id=e.sale_transaction_id,
                    units_sold=e.units_sold,
                    sale_date=e.sale_date,
                    sale_price_per_unit=e.sale_price_per_unit,
                    gain=e.gain,
                    gain_type=e.gain_type,
                )
                for e in entries
            ],
            total_stcg=total_stcg,
            total_ltcg=total_ltcg,
            total_loss=total_loss,
        )

    def _next_number(self, fy_id: int, prefix: str) -> str:
        fy = self._s.get(FinancialYear, fy_id)
        assert fy is not None
        year = fy.start_date.year
        count = len(self._s.exec(
            select(Transaction)
            .where(col(Transaction.fy_id) == fy_id)
            .where(col(Transaction.type) == "journal")
        ).all())
        return f"{prefix}-{year}-{count + 1:03d}"
