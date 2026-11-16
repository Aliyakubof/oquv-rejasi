"""O'qituvchi to'ldirib yuborgan O'quv Dasturni topshirish va AOH ko'rishi.

Hujjat yaratish `plans/dastur/service.py` da, topshirish oqimi esa shu yerda.
"""

from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from django.db.models import F, OuterRef, QuerySet, Subquery
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
    """Ma'ruza egasi biriktirilgan, lekin hali dastur topshirmagan fan varianti."""

    variant: FanVariant
    oqituvchi: OqituvchiProfil


@transaction.atomic
def dastur_topshirish(
    variant: FanVariant, oqituvchi: OqituvchiProfil, fayl: UploadedFile
) -> DasturTopshirish:
    """Yangi topshirish urinishini yozadi; faqat ma'ruza egasi yubora oladi.

    Avvalgi urinishlar o'chirilmaydi — har qayta yuborish yangi qator bo'ladi,
    shunda oldingi rad etish sabablari ikkala tomonda ham tarixda qoladi.
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


def _tekshir_va_qulfla(
    topshirish: DasturTopshirish, amal_nomi: str
) -> DasturTopshirish:
    FanVariant.objects.select_for_update().filter(pk=topshirish.variant_id).first()
    qulflangan = DasturTopshirish.objects.select_for_update().get(pk=topshirish.pk)
    eng_songi = eng_songi_urinish(qulflangan.variant)
    if eng_songi is not None and eng_songi.pk != qulflangan.pk:
        raise ValidationError(f"Faqat eng so'nggi urinishni {amal_nomi} mumkin.")
    if qulflangan.holat != TopshirishHolati.KUTILMOQDA:
        raise ValidationError("Bu topshiriq allaqachon ko'rib chiqilgan.")
    return qulflangan


@transaction.atomic
def dastur_qabul_qilish(topshirish: DasturTopshirish, admin: Foydalanuvchi) -> None:
    qulflangan = _tekshir_va_qulfla(topshirish, "qabul qilish")
    vaqt = timezone.now()
    qulflangan.holat = TopshirishHolati.QABUL_QILINDI
    qulflangan.izoh = ""
    qulflangan.korib_chiqilgan_vaqt = vaqt
    qulflangan.korib_chiqqan = admin
    qulflangan.save(
        update_fields=["holat", "izoh", "korib_chiqilgan_vaqt", "korib_chiqqan"]
    )
    topshirish.holat = qulflangan.holat
    topshirish.izoh = qulflangan.izoh
    topshirish.korib_chiqilgan_vaqt = vaqt
    topshirish.korib_chiqqan = admin


@transaction.atomic
def dastur_rad_etish(
    topshirish: DasturTopshirish, admin: Foydalanuvchi, izoh: str
) -> None:
    toza_izoh = izoh.strip()
    if not toza_izoh:
        raise ValidationError("Rad etish sababi ko'rsatilishi shart.")
    qulflangan = _tekshir_va_qulfla(topshirish, "rad etish")
    vaqt = timezone.now()
    qulflangan.holat = TopshirishHolati.RAD_ETILDI
    qulflangan.izoh = toza_izoh
    qulflangan.korib_chiqilgan_vaqt = vaqt
    qulflangan.korib_chiqqan = admin
    qulflangan.save(
        update_fields=["holat", "izoh", "korib_chiqilgan_vaqt", "korib_chiqqan"]
    )
    topshirish.holat = qulflangan.holat
    topshirish.izoh = qulflangan.izoh
    topshirish.korib_chiqilgan_vaqt = vaqt
    topshirish.korib_chiqqan = admin


def eng_songi_urinish(variant: FanVariant) -> DasturTopshirish | None:
    """Fanning eng oxirgi topshirish urinishi (hali topshirilmagan bo'lsa None)."""
    return variant.dastur_topshirishlari.first()


def joriy_topshirishlar(
    qs: "QuerySet[DasturTopshirish] | None" = None,
    *,
    holat: str | None = None,
) -> list[DasturTopshirish]:
    """Har bir fan bo'yicha faqat oxirgi urinishni AOH ro'yxati uchun oladi.

    Korrelyatsiyali ichki so'rov ishlatadi — SQLite da ham, PostgreSQL da ham
    barcha tarixni Python xotirasiga tortmasdan tez ishlaydi. `holat` filtri
    ham oxirgi urinish aniqlangandan keyin SQL darajasida qo'llanadi.
    """
    if qs is None:
        qs = DasturTopshirish.objects.all()
    oxirgi_id = (
        DasturTopshirish.objects.filter(variant_id=OuterRef("variant_id"))
        .order_by("-yuborilgan_vaqt", "-pk")
        .values("pk")[:1]
    )
    natija = qs.filter(pk=Subquery(oxirgi_id))
    if holat:
        natija = natija.filter(holat=holat)
    return list(natija.order_by("-yuborilgan_vaqt", "-pk"))


def _topshirilmagan_yuklamalar_qs(
    kafedra_id: int | None = None,
    *,
    yil: int | None = None,
) -> "QuerySet[Yuklama]":
    qs = Yuklama.objects.filter(
        tur=SoatTuri.MARUZA,
        fan_semestr__variant__fan__tanlangan_variant=F("fan_semestr__variant"),
        fan_semestr__variant__dastur_topshirishlari__isnull=True,
    )
    if kafedra_id is not None:
        qs = qs.filter(fan_semestr__variant__kafedra_id=kafedra_id)
    if yil is not None:
        qs = qs.akademik_yilda(yil)
    return qs


def topshirilmagan_dasturlar_soni(
    *, kafedra_id: int | None = None, yil: int | None = None
) -> int:
    """Ma'ruza egasi tayinlangan, lekin dastur topshirmagan fanlar sonini sanaydi."""
    return (
        _topshirilmagan_yuklamalar_qs(kafedra_id, yil=yil)
        .values("fan_semestr__variant_id", "oqituvchi_id")
        .distinct()
        .count()
    )


def topshirilmagan_dasturlar(
    *, kafedra_id: int | None = None, yil: int | None = None
) -> list[TopshirilmaganDastur]:
    """Ma'ruza egasi tayinlangan, lekin hali dastur topshirmagan fanlar ro'yxati."""
    qs = (
        _topshirilmagan_yuklamalar_qs(kafedra_id, yil=yil)
        .select_related(
            "fan_semestr__variant__fan__reja",
            "fan_semestr__variant__kafedra",
            "oqituvchi__foydalanuvchi",
        )
        .order_by("fan_semestr__variant__nomi", "fan_semestr__semestr")
    )
    korilgan: set[tuple[int, int]] = set()
    natija: list[TopshirilmaganDastur] = []
    for y in qs:
        kalit = (y.fan_semestr.variant_id, y.oqituvchi_id)
        if kalit in korilgan:
            continue
        korilgan.add(kalit)
        natija.append(
            TopshirilmaganDastur(
                variant=y.fan_semestr.variant,
                oqituvchi=y.oqituvchi,
            )
        )
    return natija
