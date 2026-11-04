"""Submission and AOH review of the O'quv Dastur a teacher fills in and
sends back. Sibling module to `plans/dastur/service.py` (generation) — one
module per responsibility.
"""

from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from django.db.models import OuterRef, QuerySet, Subquery
from django.utils import timezone

from accounts.models import Foydalanuvchi, OqituvchiProfil
from plans.dastur.service import dastur_egasimi
from plans.models import (
    DasturTopshirish,
    FanVariant,
    SoatTuri,
    TopshirishHolati,
    Yuklama,
)


@dataclass(frozen=True)
class TopshirilmaganDastur:
    """A course variant that has a lecture owner assigned, but no submission."""

    variant: FanVariant
    oqituvchi: OqituvchiProfil


@transaction.atomic
def dastur_topshirish(
    variant: FanVariant, oqituvchi: OqituvchiProfil, fayl: UploadedFile
) -> DasturTopshirish:
    """Record a new submission attempt; only the lecture owner may submit.

    Past attempts are never touched — each resubmission is a new row, so
    earlier rejection reasons stay intact for both sides to review.
    """
    FanVariant.objects.select_for_update().filter(pk=variant.pk).first()
    if not dastur_egasimi(variant, oqituvchi):
        raise ValidationError(
            "Bu fan dasturini faqat ma'ruza egasi topshirishi mumkin."
        )
    oldingi = eng_songi_urinish(variant)
    if oldingi is not None and oldingi.holat == TopshirishHolati.KUTILMOQDA:
        raise ValidationError(
            "Joriy topshiriq hali ko'rib chiqilmoqda — javob kutilsin."
        )
    return DasturTopshirish.objects.create(
        variant=variant,
        urinish_raqami=(oldingi.urinish_raqami + 1 if oldingi else 1),
        oqituvchi=oqituvchi,
        fayl=fayl,
        holat=TopshirishHolati.KUTILMOQDA,
        yuborilgan_vaqt=timezone.now(),
    )


def dastur_qabul_qilish(topshirish: DasturTopshirish, admin: Foydalanuvchi) -> None:
    eng_songi = eng_songi_urinish(topshirish.variant)
    if eng_songi is not None and eng_songi.pk != topshirish.pk:
        raise ValidationError("Faqat eng so'nggi urinishni qabul qilish mumkin.")
    topshirish.holat = TopshirishHolati.QABUL_QILINDI
    topshirish.korib_chiqilgan_vaqt = timezone.now()
    topshirish.korib_chiqqan = admin
    topshirish.save(update_fields=["holat", "korib_chiqilgan_vaqt", "korib_chiqqan"])


def dastur_rad_etish(
    topshirish: DasturTopshirish, admin: Foydalanuvchi, izoh: str
) -> None:
    if not izoh.strip():
        raise ValidationError("Rad etish sababi ko'rsatilishi shart.")
    eng_songi = eng_songi_urinish(topshirish.variant)
    if eng_songi is not None and eng_songi.pk != topshirish.pk:
        raise ValidationError("Faqat eng so'nggi urinishni rad etish mumkin.")
    topshirish.holat = TopshirishHolati.RAD_ETILDI
    topshirish.izoh = izoh
    topshirish.korib_chiqilgan_vaqt = timezone.now()
    topshirish.korib_chiqqan = admin
    topshirish.save(
        update_fields=["holat", "izoh", "korib_chiqilgan_vaqt", "korib_chiqqan"]
    )


def eng_songi_urinish(variant: FanVariant) -> DasturTopshirish | None:
    """Latest submission attempt for `variant`, or None if never submitted."""
    return variant.dastur_topshirishlari.first()


def joriy_topshirishlar(
    qs: "QuerySet[DasturTopshirish] | None" = None,
) -> list[DasturTopshirish]:
    """One row per variant — its latest attempt only — for the AOH list page.

    Uses a correlated subquery so works on both SQLite and PostgreSQL without
    loading the full attempt history into Python memory.
    """
    if qs is None:
        qs = DasturTopshirish.objects.all()
    oxirgi_id = (
        DasturTopshirish.objects.filter(variant_id=OuterRef("variant_id"))
        .order_by("-yuborilgan_vaqt", "-pk")
        .values("pk")[:1]
    )
    return list(qs.filter(pk=Subquery(oxirgi_id)).order_by("-yuborilgan_vaqt", "-pk"))


def topshirilmagan_dasturlar(
    *, kafedra_id: int | None = None
) -> list[TopshirilmaganDastur]:
    """Courses with an assigned lecture (MARUZA) owner that have no submission yet."""
    qs = (
        Yuklama.objects.filter(
            tur=SoatTuri.MARUZA,
            fan_semestr__variant__dastur_topshirishlari__isnull=True,
        )
        .select_related(
            "fan_semestr__variant__fan__reja",
            "fan_semestr__variant__kafedra",
            "oqituvchi__foydalanuvchi",
        )
        .order_by("fan_semestr__variant__nomi", "fan_semestr__semestr")
    )
    if kafedra_id is not None:
        qs = qs.filter(fan_semestr__variant__kafedra_id=kafedra_id)
    korilgan: set[int] = set()
    natija: list[TopshirilmaganDastur] = []
    for y in qs:
        vid = y.fan_semestr.variant_id
        if vid in korilgan:
            continue
        korilgan.add(vid)
        natija.append(
            TopshirilmaganDastur(
                variant=y.fan_semestr.variant,
                oqituvchi=y.oqituvchi,
            )
        )
    return natija
