"""Uzbek phone number validation and normalization for login (`telefon`)."""

import re

from django.core.exceptions import ValidationError

UZBEK_PHONE_RE = re.compile(r"^\+998\d{9}$")


def normalize_phone(raw: str) -> str:
    """Strip whitespace so "+998 91 268 12 60" and "+998912681260" are equal."""
    return re.sub(r"\s+", "", raw)


def validate_uzbek_phone(value: str) -> None:
    """Reject anything not in canonical +998XXXXXXXXX form (9 digits after code)."""
    if not UZBEK_PHONE_RE.match(value):
        raise ValidationError(
            "%(value)s is not a valid Uzbek phone number (expected +998XXXXXXXXX)",
            params={"value": value},
        )
