"""Persist a parsed o'quv reja into the plans schema."""

import math
from dataclasses import dataclass, field
from pathlib import Path

from django.db import transaction
from django.utils import timezone

from parser.models import Alternative, Course, ParseError, SelectiveSlot
from parser.parser import parse_workbook
from plans.models import (
    DasturTopshirish,
    Fan,
    FanSemestr,
    FanTuri,
    FanVariant,
    OquvReja,
    TalimYonalishi,
    Yuklama,
)
from plans.services import keshni_tozala
from plans.split import split_breakdown


class ImportXato(Exception):
    """A file cannot be imported; the message is user-facing."""


@dataclass(frozen=True)
class ParsedReja:
    yonalish_kodi: str
    boshlanish_yili: int
    daraja: str
    davomiylik_yil: int
    talim_shakli: str
    fayl_nomi: str
    core: list[Course]
    slots: list[SelectiveSlot]
    ogohlantirishlar: list[str] = field(default_factory=list)


@dataclass
class ImportNatija:
    reja: OquvReja
    fan_soni: int
    variant_soni: int
    yaratildi: bool
    ogohlantirishlar: list[str]


def parse_xlsx(path: Path, boshlanish_yili: int | None = None) -> ParsedReja:
    try:
        natija = parse_workbook(path)
    except ParseError as exc:
        raise ImportXato(str(exc)) from exc

    if not natija.direction_code:
        raise ImportXato("yo'nalish kodi topilmadi — reja identifikatsiya qilinmaydi")
    if boshlanish_yili is None:
        if not natija.start_year:
            raise ImportXato(
                "o'quv yili topilmadi — boshlanish yilini --yil bilan ko'rsating"
            )
        boshlanish_yili = int(natija.start_year)

    ogohlantirishlar = list(natija.warnings)
    davomiylik_yil = math.ceil(natija.duration_years)
    if davomiylik_yil != natija.duration_years:
        ogohlantirishlar.append(
            f"o'qish muddati {natija.duration_years:g} yil —"
            f" {davomiylik_yil} yilga yaxlitlandi"
        )

    return ParsedReja(
        yonalish_kodi=natija.direction_code,
        boshlanish_yili=boshlanish_yili,
        daraja=_bir_qatorga(natija.degree, 100),
        davomiylik_yil=davomiylik_yil,
        talim_shakli=_bir_qatorga(natija.edu_type, 100),
        fayl_nomi=path.name,
        core=natija.core,
        slots=natija.slots,
        ogohlantirishlar=ogohlantirishlar,
    )


def _bir_qatorga(matn: str, uzunlik: int) -> str:
    # Some sheets merge several metadata labels into one multi-line cell;
    # store a single-line, field-length-safe version.
    return " ".join(matn.split())[:uzunlik]


@transaction.atomic
def import_reja(parsed: ParsedReja, *, replace: bool = False) -> ImportNatija:
    try:
        yonalish = TalimYonalishi.objects.get(kodi=parsed.yonalish_kodi)
    except TalimYonalishi.DoesNotExist as exc:
        raise ImportXato(
            f"{parsed.yonalish_kodi} yo'nalishi klassifikatorda topilmadi — "
            "avval admin panelda bilim/ta'lim sohasini qo'shing"
        ) from exc
    reja, yaratildi, holat = _rejani_tayyorlash(parsed, yonalish, replace)
    fanlar, variantlar, ogohlantirishlar = _fan_va_variantlarni_yaratish(reja, parsed)
    if holat is not None:
        ogohlantirishlar += _manual_holatni_tiklash(reja, holat)
    keshni_tozala()
    return ImportNatija(
        reja=reja,
        fan_soni=len(fanlar),
        variant_soni=len(variantlar),
        yaratildi=yaratildi,
        ogohlantirishlar=ogohlantirishlar,
    )


def _mavjud_rejani_tekshir(reja: OquvReja, replace: bool) -> None:
    if not replace:
        raise ImportXato(
            f"{reja} allaqachon import qilingan; --replace bilan qayta yuklang"
        )
    yuklamalar = Yuklama.objects.filter(fan_semestr__variant__fan__reja=reja).count()
    if yuklamalar:
        raise ImportXato(
            f"{reja} bo'yicha {yuklamalar} ta yuklama taqsimlangan; "
            "avval yuklamalarni o'chiring"
        )
    topshirishlar = DasturTopshirish.objects.filter(variant__fan__reja=reja).count()
    if topshirishlar:
        raise ImportXato(
            f"{reja} bo'yicha {topshirishlar} ta fan dasturi topshirig'i mavjud; "
            "qayta yuklash taqiqlanadi"
        )


def _rejani_tayyorlash(
    parsed: ParsedReja,
    yonalish: TalimYonalishi,
    replace: bool,
) -> tuple[OquvReja, bool, dict | None]:
    """Create the reja or, on re-import, empty it while keeping manual state."""
    yangilanadigan = {
        "bilim_sohasi_kodi": yonalish.bilim_sohasi_kodi,
        "bilim_sohasi_nomi": yonalish.bilim_sohasi_nomi,
        "talim_sohasi_kodi": yonalish.talim_sohasi_kodi,
        "talim_sohasi_nomi": yonalish.talim_sohasi_nomi,
        "yonalish_nomi": yonalish.nomi,
        "daraja": parsed.daraja,
        "davomiylik_yil": parsed.davomiylik_yil,
        "manba_fayl": parsed.fayl_nomi[:255],
        "import_vaqti": timezone.now(),
    }
    reja, yaratildi = OquvReja.objects.get_or_create(
        yonalish_kodi=parsed.yonalish_kodi,
        boshlanish_yili=parsed.boshlanish_yili,
        talim_shakli=parsed.talim_shakli,
        defaults=yangilanadigan,
    )
    if yaratildi:
        return reja, True, None
    _mavjud_rejani_tekshir(reja, replace)
    holat = _manual_holatni_saqlash(reja)
    reja.fanlar.all().delete()
    for maydon, qiymat in yangilanadigan.items():
        setattr(reja, maydon, qiymat)
    reja.save()
    return reja, False, holat


def _noyob_raqam_toplamda(raqam: str, mavjud: set[str]) -> tuple[str, str | None]:
    """Disambiguate a duplicate course raqam inside an in-memory set."""
    if raqam not in mavjud:
        mavjud.add(raqam)
        return raqam, None
    n = 2
    while f"{raqam}.{n}" in mavjud:
        n += 1
    yangi = f"{raqam}.{n}"
    mavjud.add(yangi)
    return yangi, f"{raqam}: varaqda takroriy raqam; {yangi} sifatida saqlandi"


def _variant_obyekti(
    fan: Fan, kodi: str, nomi: str, soatlar: Course | Alternative
) -> FanVariant:
    return FanVariant(
        fan=fan,
        kodi=kodi or "",
        nomi=nomi,
        auditoriya_soat=soatlar.classroom,
        maruza_soat=soatlar.lecture,
        amaliyot_soat=soatlar.practice,
        laboratoriya_soat=soatlar.lab,
        seminar_soat=soatlar.seminar,
        kurs_ishi_soat=soatlar.course_proj,
    )


def _variant_semestr_royxati(
    variant: FanVariant, credits: dict[int, int], weekly: dict[int, int]
) -> tuple[list[FanSemestr], list[str]]:
    satrlar, ogohlantirishlar = split_breakdown(
        variant.maruza_soat,
        variant.amaliyot_soat,
        variant.laboratoriya_soat,
        variant.seminar_soat,
        weekly,
        credits,
    )
    semestrlar = [
        FanSemestr(
            variant=variant,
            semestr=semestr,
            kredit=credits.get(semestr, 0),
            haftalik_soat=weekly.get(semestr, 0),
            **maydonlar,
        )
        for semestr, maydonlar in sorted(satrlar.items())
    ]
    if variant.kurs_ishi_soat > 0 and semestrlar:
        # Owner's rule: the course project lands in the course's final semester.
        semestrlar[-1].kurs_ishi_bor = True
    return semestrlar, ogohlantirishlar


def _fan_va_variantlarni_yaratish(
    reja: OquvReja, parsed: ParsedReja
) -> tuple[list[Fan], list[FanVariant], list[str]]:
    mavjud_raqamlar: set[str] = set()
    ogohlantirishlar = list(parsed.ogohlantirishlar)
    fanlar: list[Fan] = []
    for course in parsed.core:
        raqam, raqam_ogoh = _noyob_raqam_toplamda(course.num, mavjud_raqamlar)
        if raqam_ogoh:
            ogohlantirishlar.append(raqam_ogoh)
        fanlar.append(
            Fan(reja=reja, raqam=raqam, turi=FanTuri.MAJBURIY, jami_soat=course.hours)
        )
    for slot in parsed.slots:
        raqam, raqam_ogoh = _noyob_raqam_toplamda(slot.num, mavjud_raqamlar)
        if raqam_ogoh:
            ogohlantirishlar.append(raqam_ogoh)
        fanlar.append(
            Fan(reja=reja, raqam=raqam, turi=FanTuri.TANLOV, jami_soat=slot.hours)
        )
    if not fanlar:
        return [], [], ogohlantirishlar
    Fan.objects.bulk_create(fanlar)

    core_soni = len(parsed.core)
    variantlar, semestr_rejalari, tanlangan_fanlar = _variantlarni_yigish(
        fanlar[:core_soni], fanlar[core_soni:], parsed, ogohlantirishlar
    )
    if variantlar:
        FanVariant.objects.bulk_create(variantlar)
    if tanlangan_fanlar:
        Fan.objects.bulk_update(tanlangan_fanlar, ["tanlangan_variant"])
    _semestrlarni_saqlash(semestr_rejalari, ogohlantirishlar)
    return fanlar, variantlar, ogohlantirishlar


SemestrRejasi = tuple[Fan, FanVariant, str, dict[int, int], dict[int, int]]


def _tanlov_slot_variantlari(
    fan: Fan,
    slot: object,
    ogohlantirishlar: list[str],
    variantlar: list[FanVariant],
    semestr_rejalari: list[SemestrRejasi],
) -> None:
    if not slot.alternatives:
        ogohlantirishlar.append(f"{fan.raqam}: tanlov slotida variantlar topilmadi")
        return
    korilgan: set[tuple[str, str]] = set()
    for alt in slot.alternatives:
        kalit = (alt.code or "", alt.name)
        if kalit in korilgan:
            ogohlantirishlar.append(
                f"{fan.raqam} {alt.name}: takroriy variant tashlab yuborildi"
            )
            continue
        korilgan.add(kalit)
        variant = _variant_obyekti(fan, alt.code, alt.name, alt)
        variantlar.append(variant)
        semestr_rejalari.append(
            (fan, variant, alt.name, slot.semester_credits, slot.semester_weekly_hours)
        )


def _variantlarni_yigish(
    majburiy_fanlar: list[Fan],
    tanlov_fanlar: list[Fan],
    parsed: ParsedReja,
    ogohlantirishlar: list[str],
) -> tuple[list[FanVariant], list[SemestrRejasi], list[Fan]]:
    variantlar: list[FanVariant] = []
    semestr_rejalari: list[SemestrRejasi] = []
    tanlangan_fanlar: list[Fan] = []
    for fan, course in zip(majburiy_fanlar, parsed.core, strict=True):
        variant = _variant_obyekti(fan, course.code, course.name, course)
        fan.tanlangan_variant = variant
        tanlangan_fanlar.append(fan)
        variantlar.append(variant)
        semestr_rejalari.append(
            (
                fan,
                variant,
                course.name,
                course.semester_credits,
                course.semester_weekly_hours,
            )
        )
    for fan, slot in zip(tanlov_fanlar, parsed.slots, strict=True):
        _tanlov_slot_variantlari(
            fan, slot, ogohlantirishlar, variantlar, semestr_rejalari
        )
    return variantlar, semestr_rejalari, tanlangan_fanlar


def _semestrlarni_saqlash(
    semestr_rejalari: list[tuple[Fan, FanVariant, str, dict[int, int], dict[int, int]]],
    ogohlantirishlar: list[str],
) -> None:
    barcha_semestrlar: list[FanSemestr] = []
    for fan, variant, nom, credits, weekly in semestr_rejalari:
        semestrlar, sem_ogoh = _variant_semestr_royxati(variant, credits, weekly)
        barcha_semestrlar.extend(semestrlar)
        ogohlantirishlar.extend(f"{fan.raqam} {nom}: {o}" for o in sem_ogoh)
    if barcha_semestrlar:
        FanSemestr.objects.bulk_create(barcha_semestrlar)


def _manual_holatni_saqlash(reja: OquvReja) -> dict:
    """Snapshot kafedra links and tanlov selections keyed by stable identity."""
    kafedralar = {
        (v.fan.raqam, v.kodi, v.nomi): v.kafedra_id
        for v in FanVariant.objects.filter(
            fan__reja=reja, kafedra__isnull=False
        ).select_related("fan")
    }
    tanlovlar = {
        fan.raqam: (fan.tanlangan_variant.kodi, fan.tanlangan_variant.nomi)
        for fan in reja.fanlar.filter(
            turi=FanTuri.TANLOV, tanlangan_variant__isnull=False
        ).select_related("tanlangan_variant")
    }
    return {"kafedralar": kafedralar, "tanlovlar": tanlovlar}


def _manual_holatni_tiklash(reja: OquvReja, holat: dict) -> list[str]:
    ogohlantirishlar = []
    kalitga = {
        (v.fan.raqam, v.kodi, v.nomi): v
        for v in FanVariant.objects.filter(fan__reja=reja).select_related("fan")
    }
    yangilangan_variantlar: list[FanVariant] = []
    for (raqam, kodi, nomi), kafedra_id in holat["kafedralar"].items():
        variant = kalitga.get((raqam, kodi, nomi))
        if variant is None:
            ogohlantirishlar.append(
                f"{raqam} {nomi}: kafedra biriktirmasi tiklanmadi (fan o'zgargan)"
            )
        else:
            variant.kafedra_id = kafedra_id
            yangilangan_variantlar.append(variant)
    if yangilangan_variantlar:
        FanVariant.objects.bulk_update(yangilangan_variantlar, ["kafedra"])

    yangilangan_fanlar: list[Fan] = []
    for raqam, (kodi, nomi) in holat["tanlovlar"].items():
        variant = kalitga.get((raqam, kodi, nomi))
        if variant is None:
            ogohlantirishlar.append(
                f"{raqam} {nomi}: tanlov qarori tiklanmadi (variant o'zgargan)"
            )
        else:
            fan = variant.fan
            fan.tanlangan_variant = variant
            yangilangan_fanlar.append(fan)
    if yangilangan_fanlar:
        Fan.objects.bulk_update(yangilangan_fanlar, ["tanlangan_variant"])
    return ogohlantirishlar
