"""Cache-backed login rate-limiting helpers."""

import hashlib
import logging

from django.conf import settings
from django.core.cache import cache
from django.http import HttpRequest

from accounts.phone import normalize_phone
from plans.audit import sorovdan_ip

_LOGGER = logging.getLogger(__name__)


def _kalit(turi: str, qiymat: str) -> str:
    xesh = hashlib.sha256(qiymat.encode("utf-8")).hexdigest()[:24]
    return f"kirish_cheklov:{turi}:{xesh}"


def _cheklov_kalitlari(request: HttpRequest, telefon: str) -> list[str]:
    kalitlar: list[str] = []
    ip = sorovdan_ip(request)
    if ip:
        kalitlar.append(_kalit("ip", ip))
    toza_tel = normalize_phone(telefon) if telefon else ""
    if toza_tel:
        kalitlar.append(_kalit("tel", toza_tel))
    return kalitlar


def _max_urinish() -> int:
    return int(getattr(settings, "LOGIN_MAX_URINISH", 5))


def _blok_soniya() -> int:
    return max(60, int(getattr(settings, "LOGIN_BLOK_SONIYA", 300)))


def kirish_bloklanganmi(request: HttpRequest, telefon: str = "") -> tuple[bool, int]:
    """Return (blocked, block_duration_seconds) when login attempts exceed threshold."""
    chegara = _max_urinish()
    if chegara <= 0:
        return False, 0
    soni = max(
        (int(cache.get(k, 0)) for k in _cheklov_kalitlari(request, telefon)), default=0
    )
    if soni >= chegara:
        return True, _blok_soniya()
    return False, 0


def kirish_xatosini_qayd_et(request: HttpRequest, telefon: str = "") -> int:
    """Increment failed-login counters for both client IP and normalized phone."""
    chegara = _max_urinish()
    if chegara <= 0:
        return 0
    muddat = _blok_soniya()
    eng_katta = 0
    for kalit in _cheklov_kalitlari(request, telefon):
        yangi = int(cache.get(kalit, 0)) + 1
        cache.set(kalit, yangi, timeout=muddat)
        eng_katta = max(eng_katta, yangi)
    if eng_katta >= chegara:
        _LOGGER.warning(
            "Kirish vaqtincha bloklandi (ip=%s, urinishlar=%s)",
            sorovdan_ip(request),
            eng_katta,
        )
    return eng_katta


def kirish_muvaffaqiyatini_tozala(request: HttpRequest, telefon: str = "") -> None:
    """Clear failed-login counters after a successful authentication."""
    for kalit in _cheklov_kalitlari(request, telefon):
        cache.delete(kalit)
