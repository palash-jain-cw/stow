"""Shared idempotent helpers for API-based test fixtures.

The test suite uses a session-scoped Postgres container; HTTP commits persist
across tests, so create-or-reuse avoids duplicate-key and overlap errors.
"""

from __future__ import annotations

from sqlmodel import Session, select

from stow.models import FinancialYear


def get_or_create_fy(
    client,
    start_date: str,
    end_date: str,
    *,
    status: str | None = None,
) -> dict:
    body: dict = {"start_date": start_date, "end_date": end_date}
    if status is not None:
        body["status"] = status
    resp = client.post("/financial-years", json=body)
    if resp.status_code == 201:
        return resp.json()
    for fy in client.get("/financial-years").json():
        if fy["start_date"] == start_date and fy["end_date"] == end_date:
            return fy
    raise AssertionError(
        f"Could not create or find FY {start_date}–{end_date}: "
        f"{resp.status_code} {resp.text}"
    )


def get_or_create_group(client, name: str, nature: str, **extra: object) -> dict:
    for group in client.get("/account-groups").json():
        if group["name"] == name:
            return group
    payload = {"name": name, "nature": nature, **extra}
    resp = client.post("/account-groups", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def get_or_create_account(client, name: str, group_name: str, **extra: object) -> dict:
    group = next(g for g in client.get("/account-groups").json() if g["name"] == group_name)
    for acc in client.get("/accounts?include_archived=true").json():
        if acc["name"] == name:
            return acc
    payload = {"name": name, "group_id": group["id"], **extra}
    resp = client.post("/accounts", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def fy_bounds_for_date(d) -> tuple[str, str]:
    if d.month >= 4:
        return f"{d.year}-04-01", f"{d.year + 1}-03-31"
    return f"{d.year - 1}-04-01", f"{d.year}-03-31"


def set_only_active_fy(session: Session, fy_id: int) -> None:
    """Ensure exactly one FY is active (others demoted from active to open)."""
    for fy in session.exec(select(FinancialYear)).all():
        if fy.id == fy_id:
            if fy.status == "locked":
                raise AssertionError(f"FY {fy_id} is locked; pick an unlocked FY for active scope tests")
            fy.status = "active"
        elif fy.status == "active":
            fy.status = "open"
        session.add(fy)
    session.commit()
