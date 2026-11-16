"""Kirishda (`telefon`) ishlatiladigan O'zbekiston raqamini tekshirish va tozalash."""

import re

from django.core.exceptions import ValidationError

OZBEK_TELEFON_RE = re.compile(r"^\+998\d{9}$")


def telefonni_normallashtir(xom: str) -> str:
    """Bo'shliqlarni olib tashlaydi: masalan '+998 91 268 12 60' -> '+998912681260'."""
    return re.sub(r"\s+", "", xom)


def validate_uzbek_phone(value: str) -> None:
    """Faqat +998XXXXXXXXX (9 ta raqam) ko'rinishidagi raqamni qabul qiladi.

    Eslatma: funksiya nomi migratsiya tarixi bilan bog'liq bo'lgani uchun saqlanadi.
    """
    if not OZBEK_TELEFON_RE.match(value):
        raise ValidationError(
            "%(value)s — O'zbekiston telefon raqami formati noto'g'ri "
            "(+998XXXXXXXXX ko'rinishida bo'lishi kerak).",
            params={"value": value},
        )
