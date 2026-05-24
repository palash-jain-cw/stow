#!/usr/bin/env python3
"""Reconcile opening balances from transaction history (carry-forward chain)."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import traceback
import urllib.error
import urllib.request
from collections import defaultdict
from dataclasses import dataclass

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BANK_GROUPS = {"Bank Accounts", "Cash-in-Hand"}
CREDIT_CARD_NAMES = {"Axis Atlas 1810", "Axis Flipkart 4809", "Axis Neo"}


@dataclass
class ReconcileSummary:
    updated: int
    skipped: int
    fy_count: int


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


def reconcile(base_url: str, *, dry_run: bool = False) -> ReconcileSummary:
    fys = sorted(_request(base_url, "/financial-years"), key=lambda f: f["start_date"])
    accs = _request(base_url, "/accounts?include_archived=true")
    txns = _request(base_url, "/transactions")

    active = next(f for f in fys if f["status"] == "active")
    acc_by_id = {a["id"]: a for a in accs}

    by_fy_acct: dict[int, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for txn in txns:
        for entry in txn["entries"]:
            by_fy_acct[txn["fy_id"]][entry["account_id"]] += entry["amount"]

    existing_ob: dict[int, dict[int, int]] = defaultdict(dict)
    for fy in fys:
        for acc in accs:
            row = _request(base_url, f"/accounts/{acc['id']}/opening-balance?fy_id={fy['id']}")
            if row["amount"]:
                existing_ob[fy["id"]][acc["id"]] = row["amount"]

    def preserve_manual_ob(acc: dict) -> bool:
        if acc["group_name"] in BANK_GROUPS and acc["id"] in existing_ob.get(active["id"], {}):
            return True
        if acc["nature"] == "liability" and acc["name"] in CREDIT_CARD_NAMES:
            if acc["id"] in existing_ob.get(active["id"], {}):
                return True
        return False

    suggested: dict[int, dict[int, int]] = {fy["id"]: {} for fy in fys}
    closing: dict[int, int] = defaultdict(int)

    for fy in fys:
        fid = fy["id"]
        for acc in accs:
            aid = acc["id"]
            if fid == active["id"] and preserve_manual_ob(acc):
                suggested[fid][aid] = existing_ob[active["id"]][aid]
            else:
                suggested[fid][aid] = closing[aid]

        for acc in accs:
            aid = acc["id"]
            closing[aid] = suggested[fid][aid] + by_fy_acct[fid].get(aid, 0)

        tb_total = sum(
            suggested[fid][acc["id"]] + by_fy_acct[fid].get(acc["id"], 0)
            for acc in accs
        )
        if fid == active["id"] and abs(tb_total) > 1:
            cap = next(a for a in accs if a["name"] == "Owner's Capital")
            suggested[fid][cap["id"]] -= tb_total
            tb_total = sum(
                suggested[fid][acc["id"]] + by_fy_acct[fid].get(acc["id"], 0)
                for acc in accs
            )
        logger.info(
            "FY %s–%s trial balance after OB: %.2f INR",
            fy["start_date"],
            fy["end_date"],
            tb_total / 100,
        )

    updated = 0
    skipped = 0
    for fy in fys:
        fid = fy["id"]
        for acc in accs:
            aid = acc["id"]
            amount = suggested[fid].get(aid, 0)
            current = existing_ob.get(fid, {}).get(aid, 0)
            if amount == current:
                skipped += 1
                continue
            if abs(amount) < 1 and current == 0:
                skipped += 1
                continue

            logger.info(
                "FY %s %s: %s -> %s",
                fy["start_date"][:4],
                acc["name"],
                current / 100,
                amount / 100,
            )
            if not dry_run:
                _request(
                    base_url,
                    f"/accounts/{aid}/opening-balance",
                    method="PUT",
                    body={"fy_id": fid, "amount": amount},
                )
            updated += 1

    return ReconcileSummary(updated=updated, skipped=skipped, fy_count=len(fys))


def main() -> int:
    parser = argparse.ArgumentParser(description="Reconcile opening balances from transactions")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--base-url", default=os.environ.get("STOW_API_URL", "http://localhost:8000"))
    args = parser.parse_args()

    try:
        summary = reconcile(args.base_url, dry_run=args.dry_run)
    except Exception:
        logger.error("Reconciliation failed\n%s", traceback.format_exc())
        return 1

    logger.info(
        "Done dry_run=%s updated=%s skipped=%s fys=%s",
        args.dry_run,
        summary.updated,
        summary.skipped,
        summary.fy_count,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
