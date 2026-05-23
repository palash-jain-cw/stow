from __future__ import annotations

import json
import logging
import traceback
import uuid
from typing import Any

import httpx

logger = logging.getLogger(__name__)

PROPOSAL_PREFIX = "PROPOSAL:"

_REQUIRED_FIELDS = ("type", "date", "from_account_id", "to_account_id", "fy_id")

# user_key -> {proposal_id: normalized proposal}
_pending: dict[str, dict[str, dict[str, Any]]] = {}


def parse_proposal(text: str) -> tuple[dict | None, str]:
    """Extract a PROPOSAL: JSON line from an orchestrator response.

    Returns (proposal_dict, display_text). proposal_dict is None when no
    valid proposal line is found. display_text has the PROPOSAL: line removed.
    """
    lines = text.splitlines()
    proposal: dict | None = None
    remaining: list[str] = []

    for line in lines:
        if line.startswith(PROPOSAL_PREFIX):
            try:
                proposal = json.loads(line[len(PROPOSAL_PREFIX):])
            except json.JSONDecodeError as exc:
                logger.warning("Invalid PROPOSAL JSON: %s", exc)
                remaining.append(line)
        else:
            remaining.append(line)

    display = "\n".join(remaining).strip()
    return proposal, display


def normalize_proposal(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize orchestrator/subagent proposal JSON to the confirm/post schema."""
    data = dict(raw)

    if "amount_paise" not in data and "amount" in data:
        data["amount_paise"] = data["amount"]

    if isinstance(data.get("date"), str):
        data["date"] = data["date"][:10]

    missing = [field for field in _REQUIRED_FIELDS if data.get(field) in (None, "")]
    amount = data.get("amount_paise")
    if not isinstance(amount, int) or amount <= 0:
        missing.append("amount_paise")

    if missing:
        raise ValueError(f"Proposal missing or invalid fields: {', '.join(missing)}")

    data.setdefault("narration", data.get("narration") or "")
    data.setdefault("from_account_name", data.get("from_account_name") or "")
    data.setdefault("to_account_name", data.get("to_account_name") or "")
    return data


def store_pending(user_key: str, proposal: dict[str, Any]) -> str:
    """Store a proposal for later confirm/decline. Returns a short callback id."""
    normalized = normalize_proposal(proposal)
    proposal_id = uuid.uuid4().hex[:8]
    _pending.setdefault(user_key, {})[proposal_id] = normalized
    logger.info("Stored pending proposal %s for user %s", proposal_id, user_key)
    return proposal_id


def pop_pending(user_key: str, proposal_id: str) -> dict[str, Any] | None:
    """Remove and return a pending proposal, if it exists."""
    return _pending.get(user_key, {}).pop(proposal_id, None)


def clear_pending_for_user(user_key: str) -> None:
    _pending.pop(user_key, None)


async def execute_proposal(
    proposal: dict[str, Any],
    http_client: httpx.AsyncClient,
    base_url: str,
) -> dict[str, Any]:
    """Post a confirmed proposal directly to POST /transactions."""
    data = normalize_proposal(proposal)
    payload = {
        "type": data["type"],
        "date": data["date"],
        "narration": data["narration"],
        "fy_id": data["fy_id"],
        "entries": [
            {"account_id": data["from_account_id"], "amount": -data["amount_paise"]},
            {"account_id": data["to_account_id"], "amount": data["amount_paise"]},
        ],
    }
    try:
        response = await http_client.post(f"{base_url}/transactions", json=payload)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        logger.error("execute_proposal HTTP error: %s", traceback.format_exc())
        raise ValueError(f"Could not create transaction: {exc.response.text}") from exc
    except Exception:
        logger.error("execute_proposal failed: %s", traceback.format_exc())
        raise

    txn = response.json()
    logger.info("Posted transaction %s from proposal", txn.get("number"))
    return txn


def format_post_success(txn: dict[str, Any]) -> str:
    number = txn.get("number", "transaction")
    narration = txn.get("narration") or "Entry posted"
    return f"✓ Posted {number} — {narration}"


async def try_handle_proposal_action(
    message: str,
    http_client: httpx.AsyncClient,
    base_url: str,
) -> str | None:
    """Handle confirm:/decline messages without invoking the orchestrator."""
    text = message.strip()
    if not text:
        return None

    if text.lower() == "decline":
        return "Transaction discarded."

    if text.startswith("confirm:"):
        raw_json = text[len("confirm:"):].strip()
        try:
            raw = json.loads(raw_json)
            txn = await execute_proposal(raw, http_client, base_url)
            return format_post_success(txn)
        except Exception as exc:
            logger.error("Failed to confirm proposal: %s", traceback.format_exc())
            return f"Could not post transaction: {exc}"

    if text.startswith("cfm:"):
        return None  # Telegram callbacks handled separately with user_key

    return None


async def confirm_pending_proposal(
    user_key: str,
    proposal_id: str,
    http_client: httpx.AsyncClient,
    base_url: str,
) -> str:
    proposal = pop_pending(user_key, proposal_id)
    if proposal is None:
        return "That proposal expired. Please describe the transaction again."
    try:
        txn = await execute_proposal(proposal, http_client, base_url)
        return format_post_success(txn)
    except Exception as exc:
        logger.error("Failed to confirm pending proposal: %s", traceback.format_exc())
        return f"Could not post transaction: {exc}"


def decline_pending_proposal(user_key: str, proposal_id: str) -> str:
    pop_pending(user_key, proposal_id)
    return "Transaction discarded."
