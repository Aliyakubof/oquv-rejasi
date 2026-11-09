"""Lightweight state-fingerprint endpoint for real-time UI synchronization."""

import hashlib

from django.contrib.auth.decorators import login_required
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

_KESH_KALITI = "jonli_holat_versiyasi"
_KESH_MUDDATI = 5

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


def _keshni_tozala(**_kwargs: object) -> None:
    cache.delete(_KESH_KALITI)


for _model in _KUZATILADIGAN_MODELLAR:
    post_save.connect(
        _keshni_tozala, sender=_model, dispatch_uid=f"jonli_save_{_model.__name__}"
    )
    post_delete.connect(
        _keshni_tozala, sender=_model, dispatch_uid=f"jonli_del_{_model.__name__}"
    )


def _reja_va_yuklama_qismlari() -> list[object]:
    return [
        tuple(
            OquvReja.objects.values_list(
                "pk",
                "talabalar_soni",
                "guruhlar_soni",
                "guruh_prefiksi",
                "yonalish_nomi",
                "import_vaqti",
            ).order_by("pk")
        ),
        Guruh.objects.aggregate(c=Count("pk"), m=Max("pk")),
        tuple(
            Fan.objects.exclude(tanlangan_variant=None)
            .values_list("pk", "tanlangan_variant_id")
            .order_by("pk")
        ),
        tuple(
            FanVariant.objects.values_list(
                "pk", "kafedra_id", "auditoriya_soat", "kurs_ishi_soat"
            ).order_by("pk")
        ),
        FanSemestr.objects.aggregate(
            c=Count("pk"),
            m=Sum("maruza_soat"),
            a=Sum("amaliyot_soat"),
            l=Sum("laboratoriya_soat"),
            s=Sum("seminar_soat"),
            k=Count("pk", filter=Q(kurs_ishi_bor=True)),
        ),
        Yuklama.objects.aggregate(
            c=Count("pk"), m=Max("pk"), s=Sum("soat"), t=Sum("talabalar_soni")
        ),
    ]


def _hisob_va_kafedra_qismlari() -> list[object]:
    return [
        tuple(
            DasturTopshirish.objects.values_list(
                "pk", "holat", "izoh", "korib_chiqilgan_vaqt"
            ).order_by("pk")
        ),
        tuple(
            KafedraYuklamaTasdiq.objects.values_list(
                "pk",
                "kafedra_id",
                "akademik_yil",
                "holat",
                "izoh",
                "tasdiqlangan_vaqt",
            ).order_by("pk")
        ),
        tuple(
            Department.objects.values_list(
                "pk", "nomi", "fakultet", "mudir_id"
            ).order_by("pk")
        ),
        tuple(
            OqituvchiProfil.objects.values_list(
                "pk",
                "kafedra_id",
                "turi_id",
                "foydalanuvchi__first_name",
                "foydalanuvchi__last_name",
                "foydalanuvchi__is_active",
            ).order_by("pk")
        ),
        tuple(
            OqituvchiTuri.objects.values_list("pk", "nomi", "min_soat").order_by("pk")
        ),
        tuple(TalimYonalishi.objects.values_list("pk", "kodi", "nomi").order_by("pk")),
        tuple(Universitet.objects.values_list("pk", "rasmiy_nomi").order_by("pk")),
        Foydalanuvchi.objects.aggregate(c=Count("pk"), m=Max("pk")),
    ]


def holat_versiyasi() -> str:
    """Return a short hash that changes whenever any domain row is mutated."""
    keshdagi = cache.get(_KESH_KALITI)
    if isinstance(keshdagi, str):
        return keshdagi
    qismlar = [*_reja_va_yuklama_qismlari(), *_hisob_va_kafedra_qismlari()]
    xom = repr(qismlar).encode("utf-8")
    versiya = hashlib.sha256(xom).hexdigest()[:16]
    cache.set(_KESH_KALITI, versiya, timeout=_KESH_MUDDATI)
    return versiya


@login_required
def jonli_holat(request: HttpRequest) -> JsonResponse:
    return JsonResponse({"versiya": holat_versiyasi()})
