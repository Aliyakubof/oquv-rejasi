"""O'qilgan o'quv rejani ma'lumotlar bazasiga saqlash moduli."""

import math
from dataclasses import dataclass, field
from pathlib import Path

from django.db import transaction
from django.utils import timezone

from parser.models import MajburiyFan, TahlilXatosi, TanlovFani, TanlovVarianti
from parser.parser import kitobni_tahlil_qil
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
from plans.services import keshni_tozala, reja_qulflanganmi
from plans.split import soatni_semestrlarga_bol


class ImportXato(Exception):
    """Faylni import qilib bo'lmaganda ko'tariladigan tushunarli xato."""


@dataclass(frozen=True)
class TahlilQilinganReja:
    yonalish_kodi: str
    boshlanish_yili: int
    daraja: str
    davomiylik_yil: int
    talim_shakli: str
    fayl_nomi: str
    majburiy_fanlar: list[MajburiyFan]
    tanlov_fanlar: list[TanlovFani]
    ogohlantirishlar: list[str] = field(default_factory=list)


@dataclass
class ImportNatija:
    reja: OquvReja
    fan_soni: int
    variant_soni: int
    yaratildi: bool
    ogohlantirishlar: list[str]


def excel_reja_oqi(yol: Path, boshlanish_yili: int | None = None) -> TahlilQilinganReja:
    try:
        natija = kitobni_tahlil_qil(yol)
    except TahlilXatosi as exc:
        raise ImportXato(str(exc)) from exc

    if not natija.yonalish_kodi:
        raise ImportXato("yo'nalish kodi topilmadi — reja identifikatsiya qilinmaydi")
    if boshlanish_yili is None:
        if not natija.boshlanish_yili:
            raise ImportXato(
                "o'quv yili topilmadi — boshlanish yilini --yil bilan ko'rsating"
            )
        boshlanish_yili = int(natija.boshlanish_yili)

    ogohlantirishlar = list(natija.ogohlantirishlar)
    davomiylik_yil = math.ceil(natija.davomiylik_yil)
    if davomiylik_yil != natija.davomiylik_yil:
        ogohlantirishlar.append(
            f"o'qish muddati {natija.davomiylik_yil:g} yil —"
            f" {davomiylik_yil} yilga yaxlitlandi"
        )

    return TahlilQilinganReja(
        yonalish_kodi=natija.yonalish_kodi,
        boshlanish_yili=boshlanish_yili,
        daraja=_bir_qatorga(natija.daraja, 100),
        davomiylik_yil=davomiylik_yil,
        talim_shakli=_bir_qatorga(natija.talim_shakli, 100),
        fayl_nomi=yol.name,
        majburiy_fanlar=natija.majburiy_fanlar,
        tanlov_fanlar=natija.tanlov_fanlar,
        ogohlantirishlar=ogohlantirishlar,
    )


def _bir_qatorga(matn: str, uzunlik: int) -> str:
    # Ba'zi varaqlarda katak ichiga bir nechta qator birlashtirilgan bo'ladi;
    # bitta qatorga tushirib, maydon sig'imidan oshirmaymiz.
    return " ".join(matn.split())[:uzunlik]


@transaction.atomic
def import_reja(
    tahlil: TahlilQilinganReja, *, almashtirish: bool = False
) -> ImportNatija:
    try:
        yonalish = TalimYonalishi.objects.get(kodi=tahlil.yonalish_kodi)
    except TalimYonalishi.DoesNotExist as exc:
        raise ImportXato(
            f"{tahlil.yonalish_kodi} yo'nalishi klassifikatorda topilmadi — "
            "avval admin panelda bilim/ta'lim sohasini qo'shing"
        ) from exc
    reja, yaratildi, holat = _rejani_tayyorlash(tahlil, yonalish, almashtirish)
    fanlar, variantlar, ogohlantirishlar = _fan_va_variantlarni_yaratish(reja, tahlil)
    if holat is not None:
        ogohlantirishlar += _qoldiq_holatni_tiklash(reja, holat)
    keshni_tozala()
    return ImportNatija(
        reja=reja,
        fan_soni=len(fanlar),
        variant_soni=len(variantlar),
        yaratildi=yaratildi,
        ogohlantirishlar=ogohlantirishlar,
    )


def _mavjud_rejani_tekshir(reja: OquvReja, almashtirish: bool) -> None:
    if not almashtirish:
        raise ImportXato(
            f"{reja} allaqachon import qilingan; --replace bilan qayta yuklang"
        )
    if reja_qulflanganmi(reja):
        raise ImportXato(
            f"{reja} bo'yicha kafedra yuklamasi qulflangan; "
            "avval tasdiqni qaytarib oling"
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
    tahlil: TahlilQilinganReja,
    yonalish: TalimYonalishi,
    almashtirish: bool,
) -> tuple[OquvReja, bool, dict | None]:
    """Yangi reja ochadi yoki qayta yuklashda bog'langan yuklamalarni saqlab qoladi."""
    yangilanadigan = {
        "bilim_sohasi_kodi": yonalish.bilim_sohasi_kodi,
        "bilim_sohasi_nomi": yonalish.bilim_sohasi_nomi,
        "talim_sohasi_kodi": yonalish.talim_sohasi_kodi,
        "talim_sohasi_nomi": yonalish.talim_sohasi_nomi,
        "yonalish_nomi": yonalish.nomi,
        "daraja": tahlil.daraja,
        "davomiylik_yil": tahlil.davomiylik_yil,
        "manba_fayl": tahlil.fayl_nomi[:255],
        "import_vaqti": timezone.now(),
    }
    reja, yaratildi = OquvReja.objects.get_or_create(
        yonalish_kodi=tahlil.yonalish_kodi,
        boshlanish_yili=tahlil.boshlanish_yili,
        talim_shakli=tahlil.talim_shakli,
        defaults=yangilanadigan,
    )
    if yaratildi:
        return reja, True, None
    reja = OquvReja.objects.select_for_update().get(pk=reja.pk)
    _mavjud_rejani_tekshir(reja, almashtirish)
    holat = _qoldiq_holatni_saqlash(reja)
    reja.fanlar.all().delete()
    for maydon, qiymat in yangilanadigan.items():
        setattr(reja, maydon, qiymat)
    reja.save()
    return reja, False, holat


def _noyob_raqam_toplamda(raqam: str, mavjud: set[str]) -> tuple[str, str | None]:
    """Bir xil raqamli fanlar tushib qolsa, oxiriga .2, .3 qo'shib farqlaydi."""
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
    fan: Fan, kodi: str, nomi: str, soatlar: MajburiyFan | TanlovVarianti
) -> FanVariant:
    return FanVariant(
        fan=fan,
        kodi=kodi or "",
        nomi=nomi,
        auditoriya_soat=soatlar.auditoriya,
        maruza_soat=soatlar.maruza,
        amaliyot_soat=soatlar.amaliyot,
        laboratoriya_soat=soatlar.laboratoriya,
        seminar_soat=soatlar.seminar,
        kurs_ishi_soat=soatlar.kurs_ishi,
    )


def _variant_semestr_royxati(
    variant: FanVariant, kreditlar: dict[int, int], haftalik: dict[int, int]
) -> tuple[list[FanSemestr], list[str]]:
    satrlar, ogohlantirishlar = soatni_semestrlarga_bol(
        variant.maruza_soat,
        variant.amaliyot_soat,
        variant.laboratoriya_soat,
        variant.seminar_soat,
        haftalik,
        kreditlar,
    )
    semestrlar = [
        FanSemestr(
            variant=variant,
            semestr=semestr,
            kredit=kreditlar.get(semestr, 0),
            haftalik_soat=haftalik.get(semestr, 0),
            **maydonlar,
        )
        for semestr, maydonlar in sorted(satrlar.items())
    ]
    if variant.kurs_ishi_soat > 0 and semestrlar:
        # Qoida bo'yicha kurs ishi fanning oxirgi semestriga yoziladi.
        semestrlar[-1].kurs_ishi_bor = True
    return semestrlar, ogohlantirishlar


def _fan_va_variantlarni_yaratish(
    reja: OquvReja, tahlil: TahlilQilinganReja
) -> tuple[list[Fan], list[FanVariant], list[str]]:
    mavjud_raqamlar: set[str] = set()
    ogohlantirishlar = list(tahlil.ogohlantirishlar)
    fanlar: list[Fan] = []
    for fan_m in tahlil.majburiy_fanlar:
        raqam, raqam_ogoh = _noyob_raqam_toplamda(fan_m.raqam, mavjud_raqamlar)
        if raqam_ogoh:
            ogohlantirishlar.append(raqam_ogoh)
        fanlar.append(
            Fan(reja=reja, raqam=raqam, turi=FanTuri.MAJBURIY, jami_soat=fan_m.soat)
        )
    for blok in tahlil.tanlov_fanlar:
        raqam, raqam_ogoh = _noyob_raqam_toplamda(blok.raqam, mavjud_raqamlar)
        if raqam_ogoh:
            ogohlantirishlar.append(raqam_ogoh)
        fanlar.append(
            Fan(reja=reja, raqam=raqam, turi=FanTuri.TANLOV, jami_soat=blok.soat)
        )
    if not fanlar:
        return [], [], ogohlantirishlar
    Fan.objects.bulk_create(fanlar)

    majburiy_soni = len(tahlil.majburiy_fanlar)
    variantlar, semestr_rejalari, tanlangan_fanlar = _variantlarni_yigish(
        fanlar[:majburiy_soni], fanlar[majburiy_soni:], tahlil, ogohlantirishlar
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
    blok: TanlovFani,
    ogohlantirishlar: list[str],
    variantlar: list[FanVariant],
    semestr_rejalari: list[SemestrRejasi],
) -> None:
    if not blok.variantlar:
        ogohlantirishlar.append(f"{fan.raqam}: tanlov slotida variantlar topilmadi")
        return
    korilgan: set[tuple[str, str]] = set()
    for alt in blok.variantlar:
        kalit = (alt.kod or "", alt.nom)
        if kalit in korilgan:
            ogohlantirishlar.append(
                f"{fan.raqam} {alt.nom}: takroriy variant tashlab yuborildi"
            )
            continue
        korilgan.add(kalit)
        variant = _variant_obyekti(fan, alt.kod, alt.nom, alt)
        variantlar.append(variant)
        semestr_rejalari.append(
            (
                fan,
                variant,
                alt.nom,
                blok.semestr_kreditlari,
                blok.semestr_haftalik_soatlar,
            )
        )


def _variantlarni_yigish(
    majburiy_fanlar: list[Fan],
    tanlov_fanlar: list[Fan],
    tahlil: TahlilQilinganReja,
    ogohlantirishlar: list[str],
) -> tuple[list[FanVariant], list[SemestrRejasi], list[Fan]]:
    variantlar: list[FanVariant] = []
    semestr_rejalari: list[SemestrRejasi] = []
    tanlangan_fanlar: list[Fan] = []
    for fan, fan_m in zip(majburiy_fanlar, tahlil.majburiy_fanlar, strict=True):
        variant = _variant_obyekti(fan, fan_m.kod, fan_m.nom, fan_m)
        fan.tanlangan_variant = variant
        tanlangan_fanlar.append(fan)
        variantlar.append(variant)
        semestr_rejalari.append(
            (
                fan,
                variant,
                fan_m.nom,
                fan_m.semestr_kreditlari,
                fan_m.semestr_haftalik_soatlar,
            )
        )
    for fan, blok in zip(tanlov_fanlar, tahlil.tanlov_fanlar, strict=True):
        _tanlov_slot_variantlari(
            fan, blok, ogohlantirishlar, variantlar, semestr_rejalari
        )
    return variantlar, semestr_rejalari, tanlangan_fanlar


def _semestrlarni_saqlash(
    semestr_rejalari: list[SemestrRejasi],
    ogohlantirishlar: list[str],
) -> None:
    barcha_semestrlar: list[FanSemestr] = []
    for fan, variant, nom, kreditlar, haftalik in semestr_rejalari:
        semestrlar, sem_ogoh = _variant_semestr_royxati(variant, kreditlar, haftalik)
        barcha_semestrlar.extend(semestrlar)
        ogohlantirishlar.extend(f"{fan.raqam} {nom}: {o}" for o in sem_ogoh)
    if barcha_semestrlar:
        FanSemestr.objects.bulk_create(barcha_semestrlar)


def _qoldiq_holatni_saqlash(reja: OquvReja) -> dict:
    """Qayta yuklashda kafedra biriktirmalari va tanlov qarorlarini eslab qoladi."""
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


def _qoldiq_holatni_tiklash(reja: OquvReja, holat: dict) -> list[str]:
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
