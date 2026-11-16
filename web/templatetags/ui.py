"""Veb-interfeys uchun kichik shablon filtrlari."""

from django import template

register = template.Library()


_APOSTROFLAR = str.maketrans("", "", "'ʼ’‘`ʻ")


@register.filter
def bosh_harflar(nomi: str) -> str:
    """Avatar initsiali: tutuq belgilarini olib, ilk 2 so'zning bosh harfini beradi."""
    sozlar = str(nomi).translate(_APOSTROFLAR).split()
    return "".join(soz[0].upper() for soz in sozlar[:2])


@register.filter
def kalit(lugat: dict, k: object) -> object:
    """Lug'atdan o'zgaruvchi kalit bo'yicha olish (Django dinamik indeks bermaydi)."""
    return lugat.get(k) if isinstance(lugat, dict) else None


@register.filter
def foiz(qism: int | None, jami: int | None) -> int:
    """qism/jami ning butun foizi (100% dan oshsa ham); noma'lum bo'lsa 0."""
    if not qism or not jami or qism <= 0 or jami <= 0:
        return 0
    return round(100 * qism / jami)


@register.filter
def kopaytir(qiymat: int | None, marta: int | None) -> int | None:
    """Guruhli talab ko'rsatkichi uchun ko'paytma; biri bo'sh bo'lsa None."""
    if not qiymat or not marta:
        return None
    return qiymat * marta
