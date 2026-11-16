"""Jonli interfeys sinxronizatsiyasi uchun yengil holat belgisi endpointi."""

import hashlib
import threading

from django.conf import settings
from django.core.cache import cache
from django.db.models import Count, Max, Q, Sum
from django.db.models.signals import post_delete, post_save
from django.http import HttpRequest, JsonResponse

from accounts.models import (
    Department,
    Foydalanuvchi,
    OqituvchiProfil,
    OqituvchiTuri,
    Universitet,
)
from plans.audit import sorovdan_ip
from plans.models import (
    Bildirishnoma,
    DasturTopshirish,
    Fan,
    FanSemestr,
    FanVariant,
    Guruh,
    KafedraYuklamaTasdiq,
    OquvReja,
    TalimYonalishi,
    Yuklama,
)
from plans.services import JONLI_EPOCH_KALITI, JONLI_KESH_KALITI, keshni_tozala
from web.security import kesh_hisoblagichni_oshir

_KESH_KALITI = JONLI_KESH_KALITI
_REDIS_KESH_MUDDATI = 3600
_LOKAL_KESH_MUDDATI = 5
_JONLI_LOCK = threading.Lock()
_JONLI_OYNA_SONIYA = 10
_JONLI_MAX_SOROV = 60


def _kesh_muddati() -> int:
    backend = str(settings.CACHES.get("default", {}).get("BACKEND", "")).lower()
    return _REDIS_KESH_MUDDATI if "redis" in backend else _LOKAL_KESH_MUDDATI


def _signal_keshni_tozala(**kwargs: object) -> None:
    update_fields = kwargs.get("update_fields")
    if (
        kwargs.get("sender") is Foydalanuvchi
        and isinstance(update_fields, (set, frozenset, list, tuple))
        and set(update_fields) <= {"last_login"}
    ):
        return
    keshni_tozala()


_KUZATILADIGAN_MODELLAR = (
    Bildirishnoma,
    OquvReja,
    Guruh,
    Fan,
    FanVariant,
    FanSemestr,
    Yuklama,
    DasturTopshirish,
    KafedraYuklamaTasdiq,
    Department,
    OqituvchiProfil,
    OqituvchiTuri,
    TalimYonalishi,
    Universitet,
    Foydalanuvchi,
)


def signallarni_ulash() -> None:
    """post_save/post_delete kesh tozalovchi signallarni bir martalik ulaydi."""
    for model in _KUZATILADIGAN_MODELLAR:
        post_save.connect(
            _signal_keshni_tozala,
            sender=model,
            dispatch_uid=f"jonli_save_{model.__name__}",
        )
        post_delete.connect(
            _signal_keshni_tozala,
            sender=model,
            dispatch_uid=f"jonli_del_{model.__name__}",
        )


_KUZATILADIGAN_AGREGATLAR: tuple[tuple[type, dict[str, object]], ...] = (
    (OquvReja, {"t": Sum("talabalar_soni"), "g": Sum("guruhlar_soni")}),
    (Guruh, {"r": Sum("raqam")}),
    (Fan, {"tv": Count("tanlangan_variant_id"), "sv": Sum("tanlangan_variant_id")}),
    (
        FanVariant,
        {
            "ck": Count("kafedra_id"),
            "sk": Sum("kafedra_id"),
            "sa": Sum("auditoriya_soat"),
        },
    ),
    (
        FanSemestr,
        {
            "sm": Sum("maruza_soat"),
            "sa": Sum("amaliyot_soat"),
            "sl": Sum("laboratoriya_soat"),
            "ss": Sum("seminar_soat"),
        },
    ),
    (
        Yuklama,
        {
            "s": Sum("soat"),
            "st": Sum("talabalar_soni"),
            "so": Sum("oqituvchi_id"),
            "sg": Sum("guruh_id"),
        },
    ),
    (
        DasturTopshirish,
        {
            "ck": Count("korib_chiqilgan_vaqt"),
            "qa": Count("pk", filter=Q(holat="QABUL_QILINDI")),
            "ra": Count("pk", filter=Q(holat="RAD_ETILDI")),
        },
    ),
    (
        KafedraYuklamaTasdiq,
        {
            "ca": Count("tasdiqlagan_id"),
            "ct": Count("tasdiqlangan_vaqt"),
            "cy": Count("yuborilgan_vaqt"),
            "td": Count("pk", filter=Q(holat="TASDIQDA")),
            "tl": Count("pk", filter=Q(holat="TASDIQLANGAN")),
            "qr": Count("pk", filter=Q(holat="QAYTARILGAN")),
        },
    ),
    (Department, {"cm": Count("mudir_id"), "sm": Sum("mudir_id")}),
    (OqituvchiProfil, {"sk": Sum("kafedra_id"), "st": Sum("turi_id")}),
    (OqituvchiTuri, {"sm": Sum("min_soat")}),
    (TalimYonalishi, {}),
    (Universitet, {}),
    (Bildirishnoma, {"oq": Count("pk", filter=Q(oqilgan=False))}),
    (Foydalanuvchi, {"act": Count("pk", filter=Q(is_active=True))}),
)


def _jadval_qismlari() -> list[object]:
    qismlar: list[object] = [cache.get(JONLI_EPOCH_KALITI, 0)]
    for model, qoshimcha in _KUZATILADIGAN_AGREGATLAR:
        agg = model.objects.aggregate(n=Count("pk"), m=Max("pk"), **qoshimcha)
        qismlar.append(tuple(sorted(agg.items())))
    return qismlar


def holat_versiyasi() -> str:
    """Bazadagi har qanday o'zgarishda yangilanadigan qisqa xesh qaytaradi."""
    keshdagi = cache.get(_KESH_KALITI)
    if isinstance(keshdagi, str):
        return keshdagi
    with _JONLI_LOCK:
        keshdagi = cache.get(_KESH_KALITI)
        if isinstance(keshdagi, str):
            return keshdagi
        epoch_boshi = cache.get(JONLI_EPOCH_KALITI)
        xom = repr(_jadval_qismlari()).encode("utf-8")
        versiya = hashlib.sha256(xom).hexdigest()[:16]
        if cache.get(JONLI_EPOCH_KALITI) == epoch_boshi:
            cache.set(_KESH_KALITI, versiya, timeout=_kesh_muddati())
        return versiya


def _jonli_limitdan_oshdimi(request: HttpRequest) -> bool:
    kalit = f"jonli_rl:{request.user.pk}:{sorovdan_ip(request) or 'lokal'}"
    soni = kesh_hisoblagichni_oshir(kalit, _JONLI_OYNA_SONIYA)
    return soni > _JONLI_MAX_SOROV


def jonli_holat(request: HttpRequest) -> JsonResponse:
    if not request.user.is_authenticated or not request.user.is_active:
        return JsonResponse({"detail": "Autentifikatsiya talab qilinadi."}, status=401)
    if _jonli_limitdan_oshdimi(request):
        return JsonResponse(
            {"detail": "Juda ko'p so'rov yuborildi. Biroz kuting."}, status=429
        )
    return JsonResponse({"versiya": holat_versiyasi()})
