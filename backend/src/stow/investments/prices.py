from __future__ import annotations

import asyncio
from datetime import date

import httpx
import yfinance as yf
from sqlmodel import Session, col, select

from stow.models import Account, PriceQuote
from stow.investments.schemas import PriceQuoteOut


class MfapiConnector:
    async def fetch(self, source_id: str) -> int:
        url = f"https://api.mfapi.in/mf/{source_id}/latest"
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            resp.raise_for_status()
        nav_str: str = resp.json()["data"][0]["nav"]
        return round(float(nav_str) * 100)  # paise per unit


class YfinanceConnector:
    def _ticker_symbol(self, source_id: str) -> str:
        return source_id if source_id.endswith(".NS") else f"{source_id}.NS"

    async def fetch(self, source_id: str) -> int:
        ticker = self._ticker_symbol(source_id)

        def _sync() -> float:
            t = yf.Ticker(ticker)
            price = t.fast_info.last_price
            if price is None:
                raise ValueError(f"No price available for {source_id}")
            return price

        price_inr: float = await asyncio.to_thread(_sync)
        return round(price_inr * 100)  # paise per unit


_CONNECTOR_MAP = {
    "equity_mf": MfapiConnector,
    "stock": YfinanceConnector,
}

_SOURCE_MAP = {
    "equity_mf": "mfapi",
    "stock": "yfinance",
}


class PriceRepository:
    def __init__(self, session: Session) -> None:
        self._s = session
        self._connectors = {k: v() for k, v in _CONNECTOR_MAP.items()}

    async def fetch(self, account_id: int) -> PriceQuoteOut:
        account = self._s.get(Account, account_id)
        if account is None:
            raise ValueError(f"Account {account_id} not found")
        if not account.price_source_id:
            raise ValueError(f"Account {account_id} has no price_source_id")
        subtype = account.investment_subtype or ""
        connector = self._connectors.get(subtype)
        if connector is None:
            raise ValueError(f"No price connector for investment_subtype={subtype!r}")

        price = await connector.fetch(account.price_source_id)
        today = date.today()
        source = _SOURCE_MAP[subtype]

        existing = self._s.exec(
            select(PriceQuote)
            .where(col(PriceQuote.account_id) == account_id)
            .where(col(PriceQuote.quote_date) == today)
        ).first()

        if existing:
            existing.price = price
            existing.source = source
            self._s.add(existing)
            self._s.commit()
            self._s.refresh(existing)
            quote = existing
        else:
            quote = PriceQuote(
                account_id=account_id, price=price, quote_date=today, source=source,
            )
            self._s.add(quote)
            self._s.commit()
            self._s.refresh(quote)

        return PriceQuoteOut(
            id=quote.id or 0,
            account_id=quote.account_id,
            price=quote.price,
            quote_date=quote.quote_date,
            source=quote.source,
        )

    async def fetch_all(self) -> list[PriceQuoteOut]:
        accounts = self._s.exec(
            select(Account)
            .where(col(Account.price_source_id).is_not(None))
            .where(Account.is_archived == False)  # noqa: E712
        ).all()
        results: list[PriceQuoteOut] = []
        for account in accounts:
            assert account.id is not None
            try:
                results.append(await self.fetch(account.id))
            except Exception:
                pass  # per-account errors are logged and swallowed
        return results

    def latest(self, account_id: int) -> PriceQuoteOut | None:
        quote = self._s.exec(
            select(PriceQuote)
            .where(col(PriceQuote.account_id) == account_id)
            .order_by(col(PriceQuote.quote_date).desc())
        ).first()
        if quote is None:
            return None
        return PriceQuoteOut(
            id=quote.id or 0,
            account_id=quote.account_id,
            price=quote.price,
            quote_date=quote.quote_date,
            source=quote.source,
        )
