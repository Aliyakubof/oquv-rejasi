"""Lightweight state-fingerprint endpoint for real-time UI synchronization."""

import hashlib

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Max, Q, Sum
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
    OquvReja,
    TalimYonalishi,
    Yuklama,
)


def holat_versiyasi() -> str:
    """Return a short hash that changes whenever any domain row is mutated."""
    qismlar = [
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
        tuple(
            DasturTopshirish.objects.values_list(
                "pk", "holat", "izoh", "korib_chiqilgan_vaqt"
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
    xom = repr(qismlar).encode("utf-8")
    return hashlib.sha256(xom).hexdigest()[:16]


@login_required
def jonli_holat(request: HttpRequest) -> JsonResponse:
    return JsonResponse({"versiya": holat_versiyasi()})
