"""Input validation utilities."""

from __future__ import annotations

import re

# Simplified RFC 5321 pattern (covers the common case without full RFC complexity)
_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")

# RFC 5321 length limits
_MAX_LOCAL_LEN = 64
_MAX_TOTAL_LEN = 254


def validate_email(address: str | None) -> bool:
    """Return True if address is a syntactically valid email address.

    Validates against RFC 5321 length limits (254 total, 64 local part) and a
    simplified RFC 5321 pattern. Returns False for None or empty input.

    Args:
        address: Email address to validate, or None.

    Returns:
        True if the address is valid, False otherwise.
    """
    if not isinstance(address, str) or not address.strip():
        return False
    local_part = address.split("@")[0] if "@" in address else address
    length_ok = len(address) <= _MAX_TOTAL_LEN and len(local_part) <= _MAX_LOCAL_LEN
    return length_ok and bool(_EMAIL_RE.match(address))
