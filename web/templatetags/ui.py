"""Small presentation filters for the web UI."""

from django import template

from accounts.models import OqituvchiProfil
from accounts.services import universitet_nomi

register = template.Library()


@register.filter
def rasmiy_matn(profil: OqituvchiProfil) -> str:
    """Official doc line, e.g. 'Husainov I. – Universitet, "Kafedra" o'qituvchisi.'"""
    nomi = universitet_nomi(bosh="—")
    return (
        f"{profil.foydalanuvchi.rasmiy_qisqa_ism} – {nomi}, "
        f"“{profil.kafedra.nomi}” kafedrasi {profil.turi.nomi}."
    )


@register.filter
def bosh_harflar(nomi: str) -> str:
    """Avatar initials: first letters of up to two words, apostrophes stripped."""
    sozlar = str(nomi).replace("'", "").replace("ʼ", "").split()
    return "".join(soz[0].upper() for soz in sozlar[:2])


@register.filter
def kalit(lugat: dict, k: object) -> object:
    """Dict lookup by a template variable (Django can't index dynamically)."""
    return lugat.get(k) if isinstance(lugat, dict) else None


@register.filter
def foiz(qism: int | None, jami: int | None) -> int:
    """Integer percentage of qism/jami, clamped to 0..100; 0 when unknown."""
    if not qism or not jami:
        return 0
    return min(100, round(100 * qism / jami))


@register.filter
def kopaytir(qiymat: int | None, marta: int | None) -> int | None:
    """Multiply two counts for the per-group demand tooltip; None if either is unset."""
    if not qiymat or not marta:
        return None
    return qiymat * marta
