"""O'quv yillari orasida kafedra biriktirish va yuklamalarni ko'chirib o'tkazish."""

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
    keshni_tozala,
    tasdiq_qulflanganmi,
)

_GURUH_TURLARI = (SoatTuri.AMALIYOT, SoatTuri.LABORATORIYA, SoatTuri.SEMINAR)
ToliqKalit = tuple[str, str, int, str, str]
NomKalit = tuple[str, str, int, str]


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


def _variant_kaliti_toliq(fs: FanSemestr) -> ToliqKalit:
    reja = fs.variant.fan.reja
    return (
        _norm(reja.yonalish_kodi),
        _norm(reja.talim_shakli),
        fs.semestr,
        _norm(fs.variant.kodi),
        _norm(fs.variant.nomi),
    )


def _variant_kaliti_nom(fs: FanSemestr) -> NomKalit:
    reja = fs.variant.fan.reja
    return (
        _norm(reja.yonalish_kodi),
        _norm(reja.talim_shakli),
        fs.semestr,
        _norm(fs.variant.nomi),
    )


def manba_yillar_royxati(
    maqsad_yil: int, *, kafedra: Department | None = None
) -> list[int]:
    """Maqsad yildan oldingi, manba ma'lumoti bor o'quv yillari ro'yxatini qaytaradi."""
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
    dict[ToliqKalit, tuple[int | None, bool]],
    dict[NomKalit, tuple[int | None, bool]],
]:
    toliq: dict[ToliqKalit, tuple[int | None, bool]] = {}
    nom: dict[NomKalit, tuple[int | None, bool]] = {}
    nom_kodi: dict[NomKalit, str] = {}
    manba_fs = (
        FanSemestr.objects.akademik_yilda(manba_yil)
        .select_related("variant__fan__reja")
        .order_by("pk")
    )
    for fs in manba_fs:
        v = fs.variant
        tanlangan = v.fan.tanlangan_variant_id == v.pk
        if v.kafedra_id is None and not tanlangan:
            continue
        qiymat = (v.kafedra_id, tanlangan)
        toliq.setdefault(_variant_kaliti_toliq(fs), qiymat)
        k2 = _variant_kaliti_nom(fs)
        kod = _norm(v.kodi)
        if nom_kodi.setdefault(k2, kod) == kod:
            nom.setdefault(k2, qiymat)
    return toliq, nom


def _top_manba_ofis(
    fs: FanSemestr,
    toliq: dict[ToliqKalit, tuple[int | None, bool]],
    nom: dict[NomKalit, tuple[int | None, bool]],
) -> tuple[int | None, bool] | None:
    return toliq.get(_variant_kaliti_toliq(fs)) or nom.get(_variant_kaliti_nom(fs))


def _fan_va_variantlarni_qulfla(
    maqsad_fs: list[FanSemestr],
) -> tuple[dict[int, Fan], dict[int, FanVariant]]:
    fan_ids = sorted({fs.variant.fan_id for fs in maqsad_fs})
    var_ids = sorted({fs.variant_id for fs in maqsad_fs})
    fanlar = (
        {
            f.pk: f
            for f in Fan.objects.select_for_update()
            .filter(pk__in=fan_ids)
            .order_by("pk")
        }
        if fan_ids
        else {}
    )
    variantlar = (
        {
            v.pk: v
            for v in FanVariant.objects.select_for_update()
            .filter(pk__in=var_ids)
            .order_by("pk")
        }
        if var_ids
        else {}
    )
    return fanlar, variantlar


def _ofis_maqsad_qulflash(
    maqsad_yil: int, manba_kaf_idlar: set[int]
) -> tuple[list[FanSemestr], dict[int, Fan], dict[int, FanVariant], set[int]]:
    maqsad_fs = list(
        FanSemestr.objects.akademik_yilda(maqsad_yil)
        .select_related("variant__fan__reja")
        .order_by("pk")
    )
    tasdiq_qs = KafedraYuklamaTasdiq.objects.filter(
        akademik_yil=maqsad_yil,
        holat__in=[KafedraTasdiqHolati.TASDIQDA, KafedraTasdiqHolati.TASDIQLANGAN],
    )
    kaf_ids = (
        manba_kaf_idlar
        | {fs.variant.kafedra_id for fs in maqsad_fs if fs.variant.kafedra_id}
        | set(tasdiq_qs.values_list("kafedra_id", flat=True))
    )
    if kaf_ids:
        list(
            Department.objects.select_for_update()
            .filter(pk__in=sorted(kaf_ids))
            .order_by("pk")
        )
    fanlar, variantlar = _fan_va_variantlarni_qulfla(maqsad_fs)
    qulflangan_ids = set(
        tasdiq_qs.select_for_update().values_list("kafedra_id", flat=True)
    )
    return maqsad_fs, fanlar, variantlar, qulflangan_ids


def _ofis_nusxa_yigish(
    maqsad_fs: list[FanSemestr],
    toliq: dict[ToliqKalit, tuple[int | None, bool]],
    nom: dict[NomKalit, tuple[int | None, bool]],
    fanlar: dict[int, Fan],
    variantlar: dict[int, FanVariant],
    qulflangan_ids: set[int],
) -> tuple[list[Fan], list[FanVariant], int]:
    fanlar_yangilash: dict[int, Fan] = {}
    variantlar_yangilash: dict[int, FanVariant] = {}
    otkazildi_kafedralar: set[int] = set()
    for fs in maqsad_fs:
        topildi = _top_manba_ofis(fs, toliq, nom)
        if topildi is None:
            continue
        manba_kaf_id, manba_tanlangan = topildi
        v = variantlar[fs.variant_id]
        fan = fanlar[v.fan_id]
        if manba_tanlangan and fan.tanlangan_variant_id is None:
            maqsad_kaf_id = v.kafedra_id if v.kafedra_id is not None else manba_kaf_id
            if maqsad_kaf_id is not None and maqsad_kaf_id in qulflangan_ids:
                otkazildi_kafedralar.add(maqsad_kaf_id)
                continue
            fan.tanlangan_variant_id = v.pk
            fanlar_yangilash[fan.pk] = fan
        if manba_kaf_id and v.kafedra_id is None and fan.tanlangan_variant_id == v.pk:
            if manba_kaf_id in qulflangan_ids:
                otkazildi_kafedralar.add(manba_kaf_id)
            else:
                v.kafedra_id = manba_kaf_id
                variantlar_yangilash[v.pk] = v
    return (
        list(fanlar_yangilash.values()),
        list(variantlar_yangilash.values()),
        len(otkazildi_kafedralar),
    )


@transaction.atomic
def ofis_taqsimotini_nusxalash(manba_yil: int, maqsad_yil: int) -> OfisNusxaNatija:
    """`manba_yil` dan tanlov va biriktirilmagan kafedra bog'lamalarini ko'chiradi."""
    if manba_yil >= maqsad_yil:
        raise ValidationError(
            "Manba o'quv yili maqsad yildan oldingi yil bo'lishi kerak."
        )
    toliq, nom = _manba_ofis_xaritasi(manba_yil)
    manba_kaf_idlar = {k for k, _ in toliq.values() if k is not None} | {
        k for k, _ in nom.values() if k is not None
    }
    maqsad_fs, fanlar, variantlar, qulflangan_ids = _ofis_maqsad_qulflash(
        maqsad_yil, manba_kaf_idlar
    )
    fanlar_y, variantlar_y, otkazildi = _ofis_nusxa_yigish(
        maqsad_fs, toliq, nom, fanlar, variantlar, qulflangan_ids
    )
    if fanlar_y:
        Fan.objects.bulk_update(fanlar_y, ["tanlangan_variant"])
    if variantlar_y:
        FanVariant.objects.bulk_update(variantlar_y, ["kafedra"])
    if fanlar_y or variantlar_y:
        keshni_tozala()
    return OfisNusxaNatija(
        manba_yil=manba_yil,
        maqsad_yil=maqsad_yil,
        tanlangan_variantlar=len(fanlar_y),
        biriktirilgan_kafedralar=len(variantlar_y),
        otkazildi_qulflangan=otkazildi,
    )


def _manba_kafedra_xaritasi(
    kafedra: Department, manba_yil: int
) -> tuple[
    dict[ToliqKalit, list[Yuklama]],
    dict[NomKalit, list[Yuklama]],
]:
    toliq: dict[ToliqKalit, list[Yuklama]] = {}
    nom: dict[NomKalit, list[Yuklama]] = {}
    nom_kodi: dict[NomKalit, str] = {}
    yuklamalar = (
        Yuklama.objects.filter(
            fan_semestr__variant__kafedra=kafedra,
            fan_semestr__variant__fan__tanlangan_variant=F("fan_semestr__variant"),
            oqituvchi__kafedra=kafedra,
            oqituvchi__foydalanuvchi__is_active=True,
        )
        .akademik_yilda(manba_yil)
        .select_related("fan_semestr__variant__fan__reja", "guruh", "oqituvchi")
        .order_by("pk")
    )
    for y in yuklamalar:
        fs = y.fan_semestr
        toliq.setdefault(_variant_kaliti_toliq(fs), []).append(y)
        k2 = _variant_kaliti_nom(fs)
        kod = _norm(fs.variant.kodi)
        if nom_kodi.setdefault(k2, kod) == kod:
            nom.setdefault(k2, []).append(y)
    return toliq, nom


def _guruhlar_xaritasi(reja_idlar: set[int]) -> dict[tuple[int, int], Guruh]:
    if not reja_idlar:
        return {}
    return {
        (g.reja_id, g.raqam): g
        for g in Guruh.objects.select_for_update()
        .filter(reja_id__in=reja_idlar)
        .order_by("pk")
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
    if not fs_idlar:
        return maruzalar, guruhlar, kurs_jami, kurs_oqit
    for y in Yuklama.objects.select_for_update().filter(fan_semestr_id__in=fs_idlar):
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


def _yangi_maruza_nusxa(
    fs: FanSemestr, manba: Yuklama, maruzalar: set[tuple[int, str]]
) -> Yuklama | None:
    if fs.maruza_soat <= 0 or (fs.pk, SoatTuri.MARUZA) in maruzalar:
        return None
    maruzalar.add((fs.pk, SoatTuri.MARUZA))
    return Yuklama(fan_semestr=fs, tur=SoatTuri.MARUZA, oqituvchi=manba.oqituvchi)


def _yangi_guruh_nusxa(
    fs: FanSemestr,
    manba: Yuklama,
    guruh_xaritasi: dict[tuple[int, int], Guruh],
    guruhlar: set[tuple[int, str, int]],
) -> Yuklama | None:
    tur = manba.tur
    if fs.tur_soat(tur) <= 0 or manba.guruh is None:
        return None
    mg = guruh_xaritasi.get((fs.variant.fan.reja_id, manba.guruh.raqam))
    if mg is None or (fs.pk, tur, mg.pk) in guruhlar:
        return None
    guruhlar.add((fs.pk, tur, mg.pk))
    return Yuklama(fan_semestr=fs, tur=tur, oqituvchi=manba.oqituvchi, guruh=mg)


def _yangi_kurs_ishi_nusxa(
    fs: FanSemestr,
    manba: Yuklama,
    kurs_jami: dict[int, int],
    kurs_oqit: set[tuple[int, int]],
) -> Yuklama | None:
    reja = fs.variant.fan.reja
    if not fs.kurs_ishi_bor or reja.talabalar_soni is None:
        return None
    if (fs.pk, manba.oqituvchi_id) in kurs_oqit:
        return None
    soni = manba.talabalar_soni or 0
    if soni < 1 or kurs_jami.get(fs.pk, 0) + soni > reja.talabalar_soni:
        return None
    kurs_jami[fs.pk] = kurs_jami.get(fs.pk, 0) + soni
    kurs_oqit.add((fs.pk, manba.oqituvchi_id))
    return Yuklama(
        fan_semestr=fs,
        tur=SoatTuri.KURS_ISHI,
        oqituvchi=manba.oqituvchi,
        talabalar_soni=soni,
    )


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
    for manba in manba_yuklamalar:
        if manba.tur == SoatTuri.MARUZA:
            yangi = _yangi_maruza_nusxa(fs, manba, maruzalar)
        elif manba.tur in _GURUH_TURLARI:
            yangi = _yangi_guruh_nusxa(fs, manba, guruh_xaritasi, guruhlar)
        elif manba.tur == SoatTuri.KURS_ISHI:
            yangi = _yangi_kurs_ishi_nusxa(fs, manba, kurs_jami, kurs_oqit)
        else:
            yangi = None
        if yangi is not None:
            yangi.soat = yangi.hisoblangan_soat()
            natija.append(yangi)
    return natija


def _kafedra_maqsad_qulfla(kafedra: Department, maqsad_yil: int) -> list[FanSemestr]:
    Department.objects.select_for_update().filter(pk=kafedra.pk).first()
    tasdiq = (
        KafedraYuklamaTasdiq.objects.select_for_update()
        .filter(kafedra=kafedra, akademik_yil=maqsad_yil)
        .first()
    )
    if tasdiq_qulflanganmi(tasdiq):
        raise ValidationError(
            "Maqsad o'quv yili yuklamasi qulflangan. Avval o'quv bo'limi qaytarsin."
        )
    return list(
        FanSemestr.objects.select_for_update()
        .filter(
            variant__kafedra=kafedra,
            variant__fan__tanlangan_variant=F("variant"),
        )
        .akademik_yilda(maqsad_yil)
        .select_related("variant__fan__reja")
        .order_by("pk")
    )


@transaction.atomic
def kafedra_taqsimotini_nusxalash(
    kafedra: Department, manba_yil: int, maqsad_yil: int
) -> KafedraNusxaNatija:
    """`manba_yil` dagi yuklamalarni `maqsad_yil` dagi bo'sh o'rinlarga ko'chiradi."""
    if manba_yil >= maqsad_yil:
        raise ValidationError(
            "Manba o'quv yili maqsad yildan oldingi yil bo'lishi kerak."
        )
    maqsad_fs = _kafedra_maqsad_qulfla(kafedra, maqsad_yil)
    toliq, nom = _manba_kafedra_xaritasi(kafedra, manba_yil)
    guruh_xaritasi = _guruhlar_xaritasi({fs.variant.fan.reja_id for fs in maqsad_fs})
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
