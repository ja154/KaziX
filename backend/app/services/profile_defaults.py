"""
app/services/profile_defaults.py
───────────────────────────────
Shared helpers for bootstrapping default profile rows.
"""

from __future__ import annotations

import hashlib
import re

_PHONE_PATTERN = re.compile(r"^\+254[0-9]{9}$")


def _placeholder_phone(user_id: str) -> str:
    """
    Generate a deterministic placeholder phone that satisfies the DB regex
    while remaining obviously non-user-entered.
    """
    digest = hashlib.sha256(user_id.encode("utf-8")).hexdigest()
    suffix = f"{int(digest[:16], 16) % 100_000_000:08d}"
    return f"+2540{suffix}"


def build_default_profile_row(
    user_id: str,
    *,
    phone: str | None = None,
    email: str | None = None,
) -> dict[str, str | None]:
    normalized_phone = str(phone or "").strip()
    normalized_email = str(email or "").strip() or None

    if not _PHONE_PATTERN.fullmatch(normalized_phone):
        normalized_phone = _placeholder_phone(user_id)

    return {
        "id": user_id,
        "role": "client",
        "full_name": "User",
        "phone": normalized_phone,
        "email": normalized_email,
        "preferred_language": "en",
    }
