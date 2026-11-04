"""Demand, allocation and workload calculations over the plans schema."""

from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from accounts.models import Department, Foydalanuvchi, OqituvchiProfil
from plans.managers import FanSemestrQuerySet
from plans.models import (
    AUDITORIYA_MAYDONLARI,
    KURS_ISHI_SOAT_TALABAGA,
    PER_GURUH_TURLAR,
    Fan,
    FanSemestr,
    FanTuri,
    FanVariant,
    Guruh,
    KafedraTasdiqHolati,
    KafedraYuklamaTasdiq,
    OquvReja,
    SoatTuri,
    Yuklama,
)


@dataclass(frozen=True)
class TalabSatri:
    """Demand vs allocation for one (fan-semester, hour type) line."""

    fan_semestr: FanSemestr
    tur: str
    talab_soat: int | None  # None until talabalar/guruhlar soni is entered
    taqsimlangan_soat: int

    @property
    def qoldiq_soat(self) -> int | None:
        if self.talab_soat is None:
            return None
        return self.talab_soat - self.taqsimlangan_soat


@dataclass(frozen=True)
class YuklamaHolati:
    """One teacher's annual standing against the position minimum."""

    oqituvchi: OqituvchiProfil
    jami_soat: int
    min_soat: int

    @property
    def kamomad(self) -> int:
        return max(0, self.min_soat - self.jami_soat)


@transaction.atomic
def guruhlarni_sinxronlash(reja: OquvReja) -> list[Guruh]:
    """Grow/shrink named groups to match guruhlar_soni.

    Surplus groups carrying yuklamalar are kept — deleting them would orphan
    real delegation work; the admin sees them until assignments move.
    """
    soni = reja.guruhlar_soni or 0
    prefiks = reja.guruh_prefiksi or reja.yonalish_kodi
    for raqam in range(1, soni + 1):
        Guruh.objects.update_or_create(
            reja=reja,
            raqam=raqam,
            defaults={"nomi": f"{prefiks}-{reja.boshlanish_yili}-{raqam}"},
        )
    reja.guruhlar.filter(raqam__gt=soni, yuklamalar__isnull=True).delete()
    return list(reja.guruhlar.all())


def fan_semestr_talabi(fs: FanSemestr, reja: OquvReja) -> dict[str, int | None]:
    """Hour demand per type: lecture x1, per-group types x groups, kurs ishi
    2h x students. Types with no hours are omitted."""
    talab: dict[str, int | None] = {}
    if fs.maruza_soat:
        talab[SoatTuri.MARUZA] = fs.maruza_soat
    for tur in PER_GURUH_TURLAR:
        soat = fs.tur_soat(tur)
        if soat:
            talab[tur] = soat * reja.guruhlar_soni if reja.guruhlar_soni else None
    if fs.kurs_ishi_bor:
        talab[SoatTuri.KURS_ISHI] = (
            KURS_ISHI_SOAT_TALABAGA * reja.talabalar_soni
            if reja.talabalar_soni
            else None
        )
    return talab


def taqsimot_hisoboti(
    reja: OquvReja,
    *,
    kurs: int | None = None,
    kafedra: Department | None = None,
) -> list[TalabSatri]:
    semestrlar = FanSemestr.objects.reja_uchun(reja).effektiv()
    if kurs is not None:
        semestrlar = semestrlar.oquv_yilida(kurs)
    if kafedra is not None:
        semestrlar = semestrlar.filter(variant__kafedra=kafedra)
    return _talab_satrlari(semestrlar)


def kafedra_taqsimoti(kafedra: Department, akademik_yil: int) -> list[TalabSatri]:
    semestrlar = (
        FanSemestr.objects.effektiv()
        .akademik_yilda(akademik_yil)
        .filter(variant__kafedra=kafedra)
    )
    return _talab_satrlari(semestrlar)


def ofis_taqsimoti(akademik_yil: int) -> list[TalabSatri]:
    """Institution-wide demand vs allocation for one academic year."""
    return _talab_satrlari(FanSemestr.objects.effektiv().akademik_yilda(akademik_yil))


def _talab_satrlari(semestrlar: FanSemestrQuerySet) -> list[TalabSatri]:
    semestrlar = semestrlar.select_related("variant__fan__reja")
    taqsimlangan = taqsimlangan_soatlar(semestrlar)
    return [
        TalabSatri(
            fan_semestr=fs,
            tur=tur,
            talab_soat=talab,
            taqsimlangan_soat=taqsimlangan.get((fs.pk, tur), 0),
        )
        for fs in semestrlar
        for tur, talab in fan_semestr_talabi(fs, fs.variant.fan.reja).items()
    ]


def taqsimlangan_soatlar(
    semestrlar: FanSemestrQuerySet,
) -> dict[tuple[int, str], int]:
    """Allocated hours grouped by (fan_semestr, tur); reused by dashboards."""
    qatorlar = (
        Yuklama.objects.filter(fan_semestr__in=semestrlar)
        .values("fan_semestr_id", "tur")
        .annotate(jami=Sum("soat"))
    )
    return {(q["fan_semestr_id"], q["tur"]): q["jami"] for q in qatorlar}


def oqituvchi_yillik_yuklamasi(oqituvchi: OqituvchiProfil, akademik_yil: int) -> int:
    jami = (
        Yuklama.objects.filter(oqituvchi=oqituvchi)
        .akademik_yilda(akademik_yil)
        .aggregate(jami=Sum("soat"))["jami"]
    )
    return jami or 0


def yuklama_kamomadi(
    akademik_yil: int, *, kafedra: Department | None = None
) -> list[YuklamaHolati]:
    """Every teacher's annual hours vs min_soat; zero-hour teachers included."""
    oqituvchilar = OqituvchiProfil.objects.select_related(
        "foydalanuvchi", "turi", "kafedra"
    )
    if kafedra is not None:
        oqituvchilar = oqituvchilar.filter(kafedra=kafedra)
    soatlar = dict(
        Yuklama.objects.akademik_yilda(akademik_yil)
        .values_list("oqituvchi_id")
        .annotate(jami=Sum("soat"))
    )
    holatlar = [
        YuklamaHolati(
            oqituvchi=o, jami_soat=soatlar.get(o.pk, 0), min_soat=o.turi.min_soat
        )
        for o in oqituvchilar
    ]
    return sorted(holatlar, key=lambda h: h.kamomad, reverse=True)


@dataclass(frozen=True)
class SemestrTahrir:
    """One office edit to a FanSemestr's classroom-hour split."""

    fan_semestr_id: int
    maruza_soat: int
    amaliyot_soat: int
    laboratoriya_soat: int
    seminar_soat: int
    kurs_ishi_bor: bool


_TAHRIR_MAYDONLARI = AUDITORIYA_MAYDONLARI


@transaction.atomic
def semestrovka_yangilash(reja: OquvReja, tahrirlar: list[SemestrTahrir]) -> None:
    """Persist office edits to a reja's per-semester hour split.

    Only the four classroom-hour fields and the kurs-ishi flag change; weekly
    hours and credits stay as parsed. A type cannot be zeroed (nor the kurs-ishi
    flag cleared) while a teacher is delegated that work; every touched yuklama's
    cached hours are refreshed to the new figures.
    """
    idlar = [t.fan_semestr_id for t in tahrirlar]
    semestrlar = {
        fs.pk: fs
        for fs in FanSemestr.objects.filter(
            pk__in=idlar, variant__fan__reja=reja
        ).select_related("variant")
    }
    variantlar: dict[int, FanVariant] = {}
    for tahrir in tahrirlar:
        fs = semestrlar.get(tahrir.fan_semestr_id)
        if fs is None:
            raise ValidationError("Semestr bu rejaga tegishli emas.")
        _semestrni_tahrirlash(fs, tahrir)
        variantlar[fs.variant_id] = fs.variant
    for variant in variantlar.values():
        _variant_soatlarini_yangilash(variant)


def _variant_soatlarini_yangilash(variant: FanVariant) -> None:
    """Keep FanVariant's aggregate classroom hours in sync with its semesters."""
    fslar = list(variant.semestrlar.all())
    variant.maruza_soat = sum(fs.maruza_soat for fs in fslar)
    variant.amaliyot_soat = sum(fs.amaliyot_soat for fs in fslar)
    variant.laboratoriya_soat = sum(fs.laboratoriya_soat for fs in fslar)
    variant.seminar_soat = sum(fs.seminar_soat for fs in fslar)
    variant.auditoriya_soat = (
        variant.maruza_soat
        + variant.amaliyot_soat
        + variant.laboratoriya_soat
        + variant.seminar_soat
    )
    kurs_ishi_bor = any(fs.kurs_ishi_bor for fs in fslar)
    if not kurs_ishi_bor:
        variant.kurs_ishi_soat = 0
    elif variant.kurs_ishi_soat == 0:
        variant.kurs_ishi_soat = KURS_ISHI_SOAT_TALABAGA
    variant.save(
        update_fields=[
            "maruza_soat",
            "amaliyot_soat",
            "laboratoriya_soat",
            "seminar_soat",
            "auditoriya_soat",
            "kurs_ishi_soat",
        ]
    )


def _semestrni_tahrirlash(fs: FanSemestr, tahrir: SemestrTahrir) -> None:
    yangi = {
        SoatTuri.MARUZA: tahrir.maruza_soat,
        SoatTuri.AMALIYOT: tahrir.amaliyot_soat,
        SoatTuri.LABORATORIYA: tahrir.laboratoriya_soat,
        SoatTuri.SEMINAR: tahrir.seminar_soat,
    }
    _band_soatni_himoyalash(fs, yangi, tahrir.kurs_ishi_bor)
    for tur, maydon in _TAHRIR_MAYDONLARI.items():
        setattr(fs, maydon, yangi[tur])
    fs.kurs_ishi_bor = tahrir.kurs_ishi_bor
    fs.save(update_fields=[*_TAHRIR_MAYDONLARI.values(), "kurs_ishi_bor"])
    for yuklama in fs.yuklamalar.all():
        yuklama.save(update_fields=["soat"])


def _band_soatni_himoyalash(
    fs: FanSemestr, yangi: dict[str, int], kurs_ishi_bor: bool
) -> None:
    """Refuse edits that would strip hours a teacher is already delegated."""
    band_turlar = set(fs.yuklamalar.values_list("tur", flat=True))
    for tur in _TAHRIR_MAYDONLARI:
        if yangi[tur] == 0 and tur in band_turlar:
            raise ValidationError(
                f"{SoatTuri(tur).label}: soat 0 ga o'zgartirilmaydi — "
                "yuklama taqsimlangan."
            )
    if not kurs_ishi_bor and SoatTuri.KURS_ISHI in band_turlar:
        raise ValidationError("Kurs ishi olib tashlanmaydi — yuklama taqsimlangan.")


def variantni_tanlash(fan: Fan, variant: FanVariant) -> None:
    """Office head picks the taught alternative of a selective slot."""
    if fan.turi != FanTuri.TANLOV:
        raise ValidationError("Faqat tanlov fanlari uchun variant tanlanadi.")
    if variant.fan_id != fan.pk:
        raise ValidationError("Variant boshqa fanga tegishli.")
    if fan.tanlangan_variant_id is not None and fan.tanlangan_variant_id != variant.pk:
        if Yuklama.objects.filter(
            fan_semestr__variant_id=fan.tanlangan_variant_id
        ).exists():
            raise ValidationError("Fanda yuklamalar bor — avval ularni bekor qiling.")
    fan.tanlangan_variant = variant
    fan.save(update_fields=["tanlangan_variant"])


def kafedraga_biriktirish(variant: FanVariant, kafedra: Department | None) -> None:
    """Office head delegates (or re-delegates) a course to a department."""
    if variant.fan.tanlangan_variant_id != variant.pk:
        raise ValidationError("Avval fan variantini tanlang.")
    if variant.kafedra_id is not None and kafedra != variant.kafedra:
        # Moving or clearing the kafedra would orphan its teachers' delegations.
        if Yuklama.objects.filter(fan_semestr__variant=variant).exists():
            raise ValidationError("Fanda yuklamalar bor — avval ularni bekor qiling.")
    variant.kafedra = kafedra
    variant.save(update_fields=["kafedra"])


def kafedra_tasdiq_holati(
    kafedra: Department, akademik_yil: int
) -> KafedraYuklamaTasdiq:
    """Return or initialize the approval record for a department-year."""
    tasdiq, _ = KafedraYuklamaTasdiq.objects.get_or_create(
        kafedra=kafedra,
        akademik_yil=akademik_yil,
        defaults={"holat": KafedraTasdiqHolati.QORALAMA},
    )
    return tasdiq


def kafedra_yuklama_qulflanganmi(kafedra: Department, akademik_yil: int) -> bool:
    """Check if the department's workload is locked against teacher modifications."""
    tasdiq = KafedraYuklamaTasdiq.objects.filter(
        kafedra=kafedra, akademik_yil=akademik_yil
    ).first()
    return tasdiq is not None and tasdiq.holat in (
        KafedraTasdiqHolati.TASDIQDA,
        KafedraTasdiqHolati.TASDIQLANGAN,
    )


def yuklamani_tasdiqqa_yuborish(
    kafedra: Department, akademik_yil: int, izoh: str = ""
) -> KafedraYuklamaTasdiq:
    """Submit department workload to office administration for review."""
    tasdiq = kafedra_tasdiq_holati(kafedra, akademik_yil)
    if tasdiq.holat == KafedraTasdiqHolati.TASDIQLANGAN:
        raise ValidationError("Yuklama allaqachon tasdiqlangan.")
    tasdiq.holat = KafedraTasdiqHolati.TASDIQDA
    tasdiq.yuborilgan_vaqt = timezone.now()
    tasdiq.izoh = izoh
    tasdiq.save()
    return tasdiq


def yuklamani_tasdiqlash(
    kafedra: Department,
    akademik_yil: int,
    admin: Foydalanuvchi,
    izoh: str = "",
) -> KafedraYuklamaTasdiq:
    """Office administrator approves and locks department workload."""
    tasdiq = kafedra_tasdiq_holati(kafedra, akademik_yil)
    tasdiq.holat = KafedraTasdiqHolati.TASDIQLANGAN
    tasdiq.tasdiqlangan_vaqt = timezone.now()
    tasdiq.tasdiqlagan = admin
    if izoh:
        tasdiq.izoh = izoh
    tasdiq.save()
    return tasdiq


def yuklamani_qaytarish(
    kafedra: Department,
    akademik_yil: int,
    admin: Foydalanuvchi,
    izoh: str = "",
) -> KafedraYuklamaTasdiq:
    """Office administrator returns department workload for corrections."""
    tasdiq = kafedra_tasdiq_holati(kafedra, akademik_yil)
    tasdiq.holat = KafedraTasdiqHolati.QAYTARILGAN
    tasdiq.tasdiqlagan = admin
    tasdiq.izoh = izoh
    tasdiq.save()
    return tasdiq
