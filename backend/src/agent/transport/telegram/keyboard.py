from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def confirm_decline_keyboard(confirm_data: str, decline_data: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Confirm", callback_data=confirm_data),
        InlineKeyboardButton(text="❌ Decline", callback_data=decline_data),
    ]])


def batch_confirm_decline_keyboard(proposal_ids: list[str]) -> InlineKeyboardMarkup:
    """Build a batch keyboard with confirm all, decline all, and per-transaction buttons."""
    rows: list[list[InlineKeyboardButton]] = []
    # First row: confirm all / decline all
    rows.append([
        InlineKeyboardButton(text="✅ Confirm All", callback_data="cfm:all"),
        InlineKeyboardButton(text="❌ Decline All", callback_data="dec:all"),
    ])
    # Per-transaction buttons
    for i, pid in enumerate(proposal_ids, 1):
        rows.append([
            InlineKeyboardButton(text=f"✅ #{i}", callback_data=f"cfm:{pid}"),
            InlineKeyboardButton(text=f"❌ #{i}", callback_data=f"dec:{pid}"),
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)
