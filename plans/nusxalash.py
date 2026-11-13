"""Year-to-year assignment and workload copying between academic years."""

from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F

from accounts.models import Department
from plans.models import (
    Fan,
    FanSemestr,
    FanVariant,
    Guruh,
    KafedraTasdiqHolati,
    KafedraYuklamaTasdiq,
    SoatTuri,
    Yuklama,
)
from plans.services import (
    kafedra_tasdiq_oqish,
    keshni_tozala,
    tasdiq_qulflanganmi,
)

_GURUH_TURLARI = (SoatTuri.AMALIYOT, SoatTuri.LABORATORIYA, SoatTuri.SEMINAR)


@dataclass(frozen=True)
class OfisNusxaNatija:
    manba_yil: int
    maqsad_yil: int
    tanlangan_variantlar: int
    biriktirilgan_kafedralar: int
    otkazildi_qulflangan: int


@dataclass(frozen=True)
class KafedraNusxaNatija:
    manba_yil: int
    maqsad_yil: int
    yaratilgan_yuklamalar: int
    qamrab_olingan_fanlar: int


def _norm(matn: str) -> str:
    return " ".join((matn or "").lower().split())


def _variant_kaliti_toliq(
    fs: FanSemestr,
) -> tuple[str, str, int, str, str]:
    reja = fs.variant.fan.reja
    return (
        _norm(reja.yonalish_kodi),
        _norm(reja.talim_shakli),
        fs.semestr,
        _norm(fs.variant.kodi),
        _norm(fs.variant.nomi),
    )


def _variant_kaliti_nom(fs: FanSemestr) -> tuple[str, int, str]:
    reja = fs.variant.fan.reja
    return (
        _norm(reja.yonalish_kodi),
        fs.semestr,
        _norm(fs.variant.nomi),
    )


def manba_yillar_royxati(
    maqsad_yil: int, *, kafedra: Department | None = None
) -> list[int]:
    """Return past academic years strictly below maqsad_yil containing source data."""
    if kafedra is not None:
        juftliklar = (
            Yuklama.objects.filter(fan_semestr__variant__kafedra=kafedra)
            .values_list(
                "fan_semestr__variant__fan__reja__boshlanish_yili",
                "fan_semestr__semestr",
            )
            .distinct()
        )
    else:
        juftliklar = (
            FanSemestr.objects.filter(variant__kafedra__isnull=False)
            .values_list(
                "variant__fan__reja__boshlanish_yili",
                "semestr",
            )
            .distinct()
        )
    yillar = {
        bosh + (sem - 1) // 2
        for bosh, sem in juftliklar
        if bosh + (sem - 1) // 2 < maqsad_yil
    }
    return sorted(yillar, reverse=True)


def _manba_ofis_xaritasi(
    manba_yil: int,
) -> tuple[
    dict[tuple[str, str, int, str, str], tuple[int | None, bool]],
    dict[tuple[str, int, str], tuple[int | None, bool]],
]:
    toliq: dict[tuple[str, str, int, str, str], tuple[int | None, bool]] = {}
    nom: dict[tuple[str, int, str], tuple[int | None, bool]] = {}
    manba_fs = FanSemestr.objects.akademik_yilda(manba_yil).select_related(
        "variant__fan__reja"
    )
    for fs in manba_fs:
        v = fs.variant
        tanlangan = v.fan.tanlangan_variant_id == v.pk
        qiymat = (v.kafedra_id, tanlangan)
        if v.kafedra_id is None and not tanlangan:
            continue
        k1 = _variant_kaliti_toliq(fs)
        toliq.setdefault(k1, qiymat)
        k2 = _variant_kaliti_nom(fs)
        nom.setdefault(k2, qiymat)
    return toliq, nom


def _top_manba_ofis(
    fs: FanSemestr,
    toliq: dict[tuple[str, str, int, str, str], tuple[int | None, bool]],
    nom: dict[tuple[str, int, str], tuple[int | None, bool]],
) -> tuple[int | None, bool] | None:
    return toliq.get(_variant_kaliti_toliq(fs)) or nom.get(_variant_kaliti_nom(fs))


@transaction.atomic
def ofis_taqsimotini_nusxalash(manba_yil: int, maqsad_yil: int) -> OfisNusxaNatija:
    """Copy variant selections and unassigned kafedra links from manba_yil."""
    if manba_yil >= maqsad_yil:
        raise ValidationError(
            "Manba o'quv yili maqsad yildan oldingi yil bo'lishi kerak."
        )
    toliq, nom = _manba_ofis_xaritasi(manba_yil)
    qulflangan_ids = set(
        KafedraYuklamaTasdiq.objects.filter(
            akademik_yil=maqsad_yil,
            holat__in=[KafedraTasdiqHolati.TASDIQDA, KafedraTasdiqHolati.TASDIQLANGAN],
        ).values_list("kafedra_id", flat=True)
    )
    maqsad_fs = FanSemestr.objects.akademik_yilda(maqsad_yil).select_related(
        "variant__fan__reja"
    )
    fanlar_yangilash: dict[int, Fan] = {}
    variantlar_yangilash: dict[int, FanVariant] = {}
    otkazildi = 0
    for fs in maqsad_fs:
        topildi = _top_manba_ofis(fs, toliq, nom)
        if topildi is None:
            continue
        manba_kaf_id, manba_tanlangan = topildi
        v = fs.variant
        if manba_tanlangan and v.fan.tanlangan_variant_id is None:
            v.fan.tanlangan_variant_id = v.pk
            fanlar_yangilash[v.fan_id] = v.fan
        if manba_kaf_id and v.kafedra_id is None:
            if manba_kaf_id in qulflangan_ids:
                otkazildi += 1
            else:
                v.kafedra_id = manba_kaf_id
                variantlar_yangilash[v.pk] = v
    if fanlar_yangilash:
        Fan.objects.bulk_update(list(fanlar_yangilash.values()), ["tanlangan_variant"])
    if variantlar_yangilash:
        FanVariant.objects.bulk_update(list(variantlar_yangilash.values()), ["kafedra"])
    if fanlar_yangilash or variantlar_yangilash:
        keshni_tozala()
    return OfisNusxaNatija(
        manba_yil=manba_yil,
        maqsad_yil=maqsad_yil,
        tanlangan_variantlar=len(fanlar_yangilash),
        biriktirilgan_kafedralar=len(variantlar_yangilash),
        otkazildi_qulflangan=otkazildi,
    )


def _manba_kafedra_xaritasi(
    kafedra: Department, manba_yil: int
) -> tuple[
    dict[tuple[str, str, int, str, str], list[Yuklama]],
    dict[tuple[str, int, str], list[Yuklama]],
]:
    toliq: dict[tuple[str, str, int, str, str], list[Yuklama]] = {}
    nom: dict[tuple[str, int, str], list[Yuklama]] = {}
    yuklamalar = (
        Yuklama.objects.filter(
            fan_semestr__variant__kafedra=kafedra,
            fan_semestr__variant__fan__tanlangan_variant=F("fan_semestr__variant"),
            oqituvchi__kafedra=kafedra,
            oqituvchi__foydalanuvchi__is_active=True,
        )
        .akademik_yilda(manba_yil)
        .select_related("fan_semestr__variant__fan__reja", "guruh", "oqituvchi")
    )
    for y in yuklamalar:
        fs = y.fan_semestr
        toliq.setdefault(_variant_kaliti_toliq(fs), []).append(y)
        nom.setdefault(_variant_kaliti_nom(fs), []).append(y)
    return toliq, nom


def _guruhlar_xaritasi(reja_idlar: set[int]) -> dict[tuple[int, int], Guruh]:
    return {
        (g.reja_id, g.raqam): g for g in Guruh.objects.filter(reja_id__in=reja_idlar)
    }


def _mavjud_kalitlar(
    fs_idlar: list[int],
) -> tuple[
    set[tuple[int, str]],
    set[tuple[int, str, int]],
    dict[int, int],
    set[tuple[int, int]],
]:
    maruzalar: set[tuple[int, str]] = set()
    guruhlar: set[tuple[int, str, int]] = set()
    kurs_jami: dict[int, int] = {}
    kurs_oqit: set[tuple[int, int]] = set()
    for y in Yuklama.objects.filter(fan_semestr_id__in=fs_idlar):
        if y.tur == SoatTuri.MARUZA:
            maruzalar.add((y.fan_semestr_id, y.tur))
        elif y.tur == SoatTuri.KURS_ISHI:
            kurs_jami[y.fan_semestr_id] = kurs_jami.get(y.fan_semestr_id, 0) + (
                y.talabalar_soni or 0
            )
            kurs_oqit.add((y.fan_semestr_id, y.oqituvchi_id))
        elif y.guruh_id is not None:
            guruhlar.add((y.fan_semestr_id, y.tur, y.guruh_id))
    return maruzalar, guruhlar, kurs_jami, kurs_oqit


def _fan_semestrdan_nusxa(
    fs: FanSemestr,
    manba_yuklamalar: list[Yuklama],
    guruh_xaritasi: dict[tuple[int, int], Guruh],
    mavjud: tuple[
        set[tuple[int, str]],
        set[tuple[int, str, int]],
        dict[int, int],
        set[tuple[int, int]],
    ],
) -> list[Yuklama]:
    maruzalar, guruhlar, kurs_jami, kurs_oqit = mavjud
    natija: list[Yuklama] = []
    reja = fs.variant.fan.reja
    for manba in manba_yuklamalar:
        tur = manba.tur
        if tur == SoatTuri.MARUZA:
            if fs.maruza_soat <= 0 or (fs.pk, tur) in maruzalar:
                continue
            maruzalar.add((fs.pk, tur))
            yangi = Yuklama(fan_semestr=fs, tur=tur, oqituvchi=manba.oqituvchi)
        elif tur in _GURUH_TURLARI:
            if fs.tur_soat(tur) <= 0 or manba.guruh is None:
                continue
            mg = guruh_xaritasi.get((reja.pk, manba.guruh.raqam))
            if mg is None or (fs.pk, tur, mg.pk) in guruhlar:
                continue
            guruhlar.add((fs.pk, tur, mg.pk))
            yangi = Yuklama(
                fan_semestr=fs, tur=tur, oqituvchi=manba.oqituvchi, guruh=mg
            )
        elif tur == SoatTuri.KURS_ISHI:
            if not fs.kurs_ishi_bor or reja.talabalar_soni is None:
                continue
            if (fs.pk, manba.oqituvchi_id) in kurs_oqit:
                continue
            soni = manba.talabalar_soni or 0
            if soni < 1 or kurs_jami.get(fs.pk, 0) + soni > reja.talabalar_soni:
                continue
            kurs_jami[fs.pk] = kurs_jami.get(fs.pk, 0) + soni
            kurs_oqit.add((fs.pk, manba.oqituvchi_id))
            yangi = Yuklama(
                fan_semestr=fs,
                tur=tur,
                oqituvchi=manba.oqituvchi,
                talabalar_soni=soni,
            )
        else:
            continue
        yangi.soat = yangi.hisoblangan_soat()
        natija.append(yangi)
    return natija


@transaction.atomic
def kafedra_taqsimotini_nusxalash(
    kafedra: Department, manba_yil: int, maqsad_yil: int
) -> KafedraNusxaNatija:
    """Copy kafedra teacher allocations from manba_yil into empty maqsad_yil slots."""
    if manba_yil >= maqsad_yil:
        raise ValidationError(
            "Manba o'quv yili maqsad yildan oldingi yil bo'lishi kerak."
        )
    tasdiq = kafedra_tasdiq_oqish(kafedra, maqsad_yil)
    if tasdiq_qulflanganmi(tasdiq):
        raise ValidationError(
            "Maqsad o'quv yili yuklamasi qulflangan. Avval o'quv bo'limi qaytarsin."
        )
    toliq, nom = _manba_kafedra_xaritasi(kafedra, manba_yil)
    maqsad_fs = list(
        FanSemestr.objects.filter(
            variant__kafedra=kafedra,
            variant__fan__tanlangan_variant=F("variant"),
        )
        .akademik_yilda(maqsad_yil)
        .select_related("variant__fan__reja")
    )
    reja_idlar = {fs.variant.fan.reja_id for fs in maqsad_fs}
    guruh_xaritasi = _guruhlar_xaritasi(reja_idlar)
    mavjud = _mavjud_kalitlar([fs.pk for fs in maqsad_fs])
    yaratiladiganlar: list[Yuklama] = []
    qamrab_olingan = 0
    for fs in maqsad_fs:
        manbalar = toliq.get(_variant_kaliti_toliq(fs)) or nom.get(
            _variant_kaliti_nom(fs)
        )
        if not manbalar:
            continue
        qoshildi = _fan_semestrdan_nusxa(fs, manbalar, guruh_xaritasi, mavjud)
        if qoshildi:
            qamrab_olingan += 1
            yaratiladiganlar.extend(qoshildi)
    if yaratiladiganlar:
        Yuklama.objects.bulk_create(yaratiladiganlar)
        keshni_tozala()
    return KafedraNusxaNatija(
        manba_yil=manba_yil,
        maqsad_yil=maqsad_yil,
        yaratilgan_yuklamalar=len(yaratiladiganlar),
        qamrab_olingan_fanlar=qamrab_olingan,
    )
