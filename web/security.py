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


def _cheklov_kalitlari(
    request: HttpRequest, telefon: str, *, chegara: int
) -> list[tuple[str, int]]:
    kalitlar: list[tuple[str, int]] = []
    ip = sorovdan_ip(request)
    toza_tel = normalize_phone(telefon) if telefon else ""
    if toza_tel:
        kalitlar.append((_kalit("tel", toza_tel), chegara))
    if ip and toza_tel:
        kalitlar.append((_kalit("iptel", f"{ip}:{toza_tel}"), chegara))
    if ip:
        # NAT/proksi ortida bitta foydalanuvchi boshqalarni bloklab qo'ymasligi uchun
        kalitlar.append((_kalit("ip", ip), max(chegara * 4, 20)))
    return kalitlar


def _max_urinish() -> int:
    return int(getattr(settings, "LOGIN_MAX_URINISH", 5))


def _blok_soniya() -> int:
    return max(60, int(getattr(settings, "LOGIN_BLOK_SONIYA", 300)))


def kesh_hisoblagichni_oshir(kalit: str, muddat: int) -> int:
    """Atomically initialize and increment a cache counter within the given TTL."""
    cache.add(kalit, 0, timeout=muddat)
    try:
        return int(cache.incr(kalit))
    except ValueError:
        cache.set(kalit, 1, timeout=muddat)
        return 1


def kirish_bloklanganmi(request: HttpRequest, telefon: str = "") -> tuple[bool, int]:
    """Return (blocked, block_duration_seconds) when login attempts exceed threshold."""
    chegara = _max_urinish()
    if chegara <= 0:
        return False, 0
    for kalit, limit in _cheklov_kalitlari(request, telefon, chegara=chegara):
        if int(cache.get(kalit, 0)) >= limit:
            return True, _blok_soniya()
    return False, 0


def kirish_xatosini_qayd_et(request: HttpRequest, telefon: str = "") -> int:
    """Increment failed-login counters atomically across IP and phone buckets."""
    chegara = _max_urinish()
    if chegara <= 0:
        return 0
    muddat = _blok_soniya()
    eng_katta = 0
    blok_bormi = False
    for kalit, limit in _cheklov_kalitlari(request, telefon, chegara=chegara):
        yangi = kesh_hisoblagichni_oshir(kalit, muddat)
        eng_katta = max(eng_katta, yangi)
        if yangi >= limit:
            blok_bormi = True
    if blok_bormi:
        _LOGGER.warning(
            "Kirish vaqtincha bloklandi (ip=%s, urinishlar=%s)",
            sorovdan_ip(request),
            eng_katta,
        )
    return eng_katta


def kirish_muvaffaqiyatini_tozala(request: HttpRequest, telefon: str = "") -> None:
    """Clear per-phone failed-login counters after a successful authentication."""
    chegara = max(1, _max_urinish())
    for kalit, _limit in _cheklov_kalitlari(request, telefon, chegara=chegara):
        if not kalit.startswith("kirish_cheklov:ip:"):
            cache.delete(kalit)


def api_sorov_limitdan_oshdimi(request: HttpRequest) -> bool:
    """Rate-limit API requests per client IP within a 60-second window."""
    limit = int(getattr(settings, "API_MAX_SOROV_DAQIQA", 120))
    if limit <= 0:
        return False
    ip = sorovdan_ip(request) or "lokal"
    kalit = _kalit("api_rl", ip)
    return kesh_hisoblagichni_oshir(kalit, 60) > limit
