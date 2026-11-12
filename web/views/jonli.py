"""Lightweight state-fingerprint endpoint for real-time UI synchronization."""

import hashlib

from django.core.cache import cache
from django.db.models.signals import post_delete, post_save
from django.http import HttpRequest, JsonResponse

from accounts.models import (
    Department,
    Foydalanuvchi,
    OqituvchiProfil,
    OqituvchiTuri,
    Universitet,
)
from plans.models import (
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
from plans.services import JONLI_KESH_KALITI, keshni_tozala

_KESH_KALITI = JONLI_KESH_KALITI
_KESH_MUDDATI = 5
_keshni_tozala = keshni_tozala

_KUZATILADIGAN_MODELLAR = (
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
    """Connect post_save/post_delete cache invalidators idempotently."""
    for model in _KUZATILADIGAN_MODELLAR:
        post_save.connect(
            keshni_tozala, sender=model, dispatch_uid=f"jonli_save_{model.__name__}"
        )
        post_delete.connect(
            keshni_tozala, sender=model, dispatch_uid=f"jonli_del_{model.__name__}"
        )


_KUZATILADIGAN_MAYDONLAR: tuple[tuple[type, tuple[str, ...]], ...] = (
    (
        OquvReja,
        (
            "pk",
            "talabalar_soni",
            "guruhlar_soni",
            "guruh_prefiksi",
            "yonalish_nomi",
            "import_vaqti",
        ),
    ),
    (Guruh, ("pk", "reja_id", "raqam", "nomi")),
    (Fan, ("pk", "reja_id", "raqam", "turi", "jami_soat", "tanlangan_variant_id")),
    (
        FanVariant,
        (
            "pk",
            "fan_id",
            "kodi",
            "nomi",
            "kafedra_id",
            "auditoriya_soat",
            "maruza_soat",
            "amaliyot_soat",
            "laboratoriya_soat",
            "seminar_soat",
            "kurs_ishi_soat",
        ),
    ),
    (
        FanSemestr,
        (
            "pk",
            "semestr",
            "maruza_soat",
            "amaliyot_soat",
            "laboratoriya_soat",
            "seminar_soat",
            "kurs_ishi_bor",
        ),
    ),
    (
        Yuklama,
        (
            "pk",
            "fan_semestr_id",
            "tur",
            "oqituvchi_id",
            "guruh_id",
            "soat",
            "talabalar_soni",
        ),
    ),
    (
        DasturTopshirish,
        (
            "pk",
            "variant_id",
            "urinish_raqami",
            "holat",
            "izoh",
            "yuborilgan_vaqt",
            "korib_chiqilgan_vaqt",
        ),
    ),
    (
        KafedraYuklamaTasdiq,
        (
            "pk",
            "kafedra_id",
            "akademik_yil",
            "holat",
            "izoh",
            "yuborilgan_vaqt",
            "tasdiqlangan_vaqt",
            "tasdiqlagan_id",
        ),
    ),
    (Department, ("pk", "nomi", "fakultet", "mudir_id")),
    (
        OqituvchiProfil,
        (
            "pk",
            "kafedra_id",
            "turi_id",
            "foydalanuvchi__first_name",
            "foydalanuvchi__last_name",
            "foydalanuvchi__is_active",
        ),
    ),
    (OqituvchiTuri, ("pk", "nomi", "min_soat")),
    (TalimYonalishi, ("pk", "kodi", "nomi")),
    (Universitet, ("pk", "rasmiy_nomi")),
    (
        Foydalanuvchi,
        ("pk", "telefon", "first_name", "last_name", "rol", "is_active"),
    ),
)


def _jadval_qismlari() -> list[tuple[object, ...]]:
    return [
        tuple(model.objects.values_list(*maydonlar).order_by("pk"))
        for model, maydonlar in _KUZATILADIGAN_MAYDONLAR
    ]


def holat_versiyasi() -> str:
    """Return a short hash that changes whenever any domain row is mutated."""
    keshdagi = cache.get(_KESH_KALITI)
    if isinstance(keshdagi, str):
        return keshdagi
    xom = repr(_jadval_qismlari()).encode("utf-8")
    versiya = hashlib.sha256(xom).hexdigest()[:16]
    cache.set(_KESH_KALITI, versiya, timeout=_KESH_MUDDATI)
    return versiya


def jonli_holat(request: HttpRequest) -> JsonResponse:
    if not request.user.is_authenticated or not request.user.is_active:
        return JsonResponse({"detail": "Autentifikatsiya talab qilinadi."}, status=401)
    return JsonResponse({"versiya": holat_versiyasi()})
