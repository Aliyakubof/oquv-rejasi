"""Small presentation filters for the web UI."""

from django import template

register = template.Library()


_APOSTROFLAR = str.maketrans("", "", "'ʼ’‘`ʻ")


@register.filter
def bosh_harflar(nomi: str) -> str:
    """Avatar initials: first letters of up to two words, apostrophes stripped."""
    sozlar = str(nomi).translate(_APOSTROFLAR).split()
    return "".join(soz[0].upper() for soz in sozlar[:2])


@register.filter
def kalit(lugat: dict, k: object) -> object:
    """Dict lookup by a template variable (Django can't index dynamically)."""
    return lugat.get(k) if isinstance(lugat, dict) else None


@register.filter
def foiz(qism: int | None, jami: int | None) -> int:
    """Integer percentage of qism/jami (uncapped above 100); 0 when unknown."""
    if not qism or not jami or qism <= 0 or jami <= 0:
        return 0
    return round(100 * qism / jami)


@register.filter
def kopaytir(qiymat: int | None, marta: int | None) -> int | None:
    """Multiply two counts for the per-group demand tooltip; None if either is unset."""
    if not qiymat or not marta:
        return None
    return qiymat * marta
