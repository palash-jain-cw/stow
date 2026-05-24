#!/usr/bin/env python3
"""Apply active-FY cut-over opening balances and lock prior financial years.

Preserves manual bank/credit-card OB on the active FY, sets investment OB from
open lot cost basis (minus active-FY entries already posted), zeros P&L opening
balances, plugs Owner's Capital, then locks all non-active FYs.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import traceback
import urllib.error
import urllib.request
from dataclasses import dataclass, field

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BANK_GROUPS = {"Bank Accounts", "Cash-in-Hand"}
CREDIT_CARD_NAMES = {"Axis Atlas 1810", "Axis Flipkart 4809", "Axis Neo"}
INVESTMENT_SUBTYPES = {"equity_mf", "stock"}


@dataclass
class CutoverSummary:
    ob_updated: int = 0
    ob_unchanged: int = 0
    fys_locked: int = 0
    fys_already_locked: int = 0
    warnings: list[str] = field(default_factory=list)


def _request(base: str, path: str, *, method: str = "GET", body: dict | None = None) -> object:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{base}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    try:
        with urllib.request.urlopen(req) as resp:
            if resp.status == 204:
                return None
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode()
        logger.error("HTTP %s %s failed: %s\n%s", method, path, detail, traceback.format_exc())
        raise


def _preserve_manual_ob(acc: dict, existing_ob: dict[int, int]) -> bool:
    if acc["group_name"] in BANK_GROUPS and acc["id"] in existing_ob:
        return True
    if acc["nature"] == "liability" and acc["name"] in CREDIT_CARD_NAMES:
        return acc["id"] in existing_ob
    return False


def _lot_cost_basis(base: str, account_id: int) -> int:
    lots = _request(base, f"/investments/{account_id}/holdings")
    return sum(int(lot["cost_basis"]) for lot in lots)


def apply_cutover(base_url: str, *, dry_run: bool = True, lock_prior_fys: bool = True) -> CutoverSummary:
    summary = CutoverSummary()
    fys = sorted(_request(base_url, "/financial-years"), key=lambda f: f["start_date"])
    accs = _request(base_url, "/accounts?include_archived=true")
    txns = _request(base_url, "/transactions")

    active = next(f for f in fys if f["status"] == "active")
    active_id = active["id"]
    logger.info(
        "Active FY id=%s (%s to %s)",
        active_id,
        active["start_date"],
        active["end_date"],
    )

    entries: dict[int, int] = {}
    for txn in txns:
        if txn["fy_id"] != active_id:
            continue
        for entry in txn["entries"]:
            entries[entry["account_id"]] = entries.get(entry["account_id"], 0) + entry["amount"]

    existing_ob: dict[int, int] = {}
    for acc in accs:
        row = _request(base_url, f"/accounts/{acc['id']}/opening-balance?fy_id={active_id}")
        amount = int(row["amount"])
        if amount:
            existing_ob[acc["id"]] = amount

    proposed: dict[int, int] = {acc["id"]: 0 for acc in accs}

    for acc in accs:
        if _preserve_manual_ob(acc, existing_ob):
            proposed[acc["id"]] = existing_ob[acc["id"]]
            logger.info("Preserving manual OB for %s: %.2f INR", acc["name"], proposed[acc["id"]] / 100)

    for acc in accs:
        subtype = acc.get("investment_subtype")
        if subtype in INVESTMENT_SUBTYPES and not acc["is_archived"]:
            lot_cb = _lot_cost_basis(base_url, acc["id"])
            active_entries = entries.get(acc["id"], 0)
            proposed[acc["id"]] = lot_cb - active_entries
            ledger = proposed[acc["id"]] + active_entries
            if lot_cb and abs(ledger - lot_cb) > 1:
                msg = (
                    f"Investment {acc['name']}: ledger {ledger/100:.2f} != lots {lot_cb/100:.2f}"
                )
                summary.warnings.append(msg)
                logger.warning(msg)

    cap = next(a for a in accs if a["name"] == "Owner's Capital")
    tb_before_plug = sum(proposed[a["id"]] + entries.get(a["id"], 0) for a in accs)
    proposed[cap["id"]] = proposed.get(cap["id"], 0) - tb_before_plug
    tb_total = sum(proposed[a["id"]] + entries.get(a["id"], 0) for a in accs)
    logger.info("Trial balance after cut-over OB: %.2f INR", tb_total / 100)
    if abs(tb_total) > 1:
        msg = f"Trial balance not zero after plug: {tb_total/100:.2f} INR"
        summary.warnings.append(msg)
        logger.error(msg)

    for acc in accs:
        aid = acc["id"]
        old = existing_ob.get(aid, 0)
        new = proposed.get(aid, 0)
        if old == new:
            summary.ob_unchanged += 1
            continue
        logger.info(
            "OB %s: %.2f -> %.2f INR",
            acc["name"],
            old / 100,
            new / 100,
        )
        if not dry_run:
            _request(
                base_url,
                f"/accounts/{aid}/opening-balance",
                method="PUT",
                body={"fy_id": active_id, "amount": new},
            )
        summary.ob_updated += 1

    if lock_prior_fys:
        for fy in fys:
            if fy["id"] == active_id:
                continue
            if fy["status"] == "locked":
                summary.fys_already_locked += 1
                continue
            logger.info(
                "Locking FY id=%s (%s to %s), status=%s",
                fy["id"],
                fy["start_date"],
                fy["end_date"],
                fy["status"],
            )
            if not dry_run:
                _request(base_url, f"/financial-years/{fy['id']}/lock", method="POST", body={})
            summary.fys_locked += 1

    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply active-FY cut-over and lock prior FYs")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without applying")
    parser.add_argument("--no-lock", action="store_true", help="Skip locking prior financial years")
    parser.add_argument("--base-url", default=os.environ.get("STOW_API_URL", "http://localhost:8000"))
    args = parser.parse_args()

    try:
        summary = apply_cutover(
            args.base_url,
            dry_run=args.dry_run,
            lock_prior_fys=not args.no_lock,
        )
    except Exception:
        logger.error("Cut-over failed\n%s", traceback.format_exc())
        return 1

    logger.info(
        "Done dry_run=%s ob_updated=%s ob_unchanged=%s fys_locked=%s fys_already_locked=%s warnings=%s",
        args.dry_run,
        summary.ob_updated,
        summary.ob_unchanged,
        summary.fys_locked,
        summary.fys_already_locked,
        len(summary.warnings),
    )
    for warning in summary.warnings:
        logger.warning("  %s", warning)
    return 0 if not summary.warnings else 1


if __name__ == "__main__":
    sys.exit(main())
