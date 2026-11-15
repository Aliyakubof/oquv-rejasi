"""O'quv reja sxemasi bo'yicha soat talabi, taqsimot va yuklama hisob-kitoblari."""

from dataclasses import dataclass

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q, Sum
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

JONLI_KESH_KALITI = "jonli_holat_versiyasi"
JONLI_EPOCH_KALITI = "jonli_holat_epoch"


def keshni_tozala(**_kwargs: object) -> None:
    """Jonli yangilanish hisoblagichini oshiradi va keshdagi versiyani tozalaydi."""
    if not cache.add(JONLI_EPOCH_KALITI, 1, timeout=None):
        try:
            cache.incr(JONLI_EPOCH_KALITI)
        except ValueError:
            cache.set(JONLI_EPOCH_KALITI, 1, timeout=None)
    cache.delete(JONLI_KESH_KALITI)


@dataclass(frozen=True)
class TalabSatri:
    """Bitta (fan-semestr, soat turi) bo'yicha talab va taqsimot qatori."""

    fan_semestr: FanSemestr
    tur: str
    talab_soat: int | None  # Talaba/guruhlar soni kiritilmaguncha None bo'ladi
    taqsimlangan_soat: int

    @property
    def qoldiq_soat(self) -> int | None:
        if self.talab_soat is None:
            return None
        return self.talab_soat - self.taqsimlangan_soat


@dataclass(frozen=True)
class YuklamaHolati:
    """Bitta o'qituvchining lavozim normasiga nisbatan yillik yuklama holati."""

    oqituvchi: OqituvchiProfil
    jami_soat: int
    min_soat: int

    @property
    def kamomad(self) -> int:
        return max(0, self.min_soat - self.jami_soat)


@transaction.atomic
def guruhlarni_sinxronlash(reja: OquvReja) -> list[Guruh]:
    """Guruhlarni `guruhlar_soni` ga moslab qo'shadi yoki ortiqchasini o'chiradi.

    Yuklamasi bor ortiqcha guruhlar o'chirilmaydi — aks holda taqsimlangan
    soatlar yetim qoladi; admin ularni yuklamani ko'chirguncha ko'rib turadi.
    """
    soni = reja.guruhlar_soni or 0
    prefiks = reja.guruh_prefiksi or reja.yonalish_kodi
    mavjud = {g.raqam: g for g in reja.guruhlar.all()}
    yangi_guruhlar: list[Guruh] = []
    ozgargan_guruhlar: list[Guruh] = []
    for raqam in range(1, soni + 1):
        nomi = f"{prefiks}-{reja.boshlanish_yili}-{raqam}"
        guruh = mavjud.get(raqam)
        if guruh is None:
            yangi_guruhlar.append(Guruh(reja=reja, raqam=raqam, nomi=nomi))
        elif guruh.nomi != nomi:
            guruh.nomi = nomi
            ozgargan_guruhlar.append(guruh)
    if yangi_guruhlar:
        Guruh.objects.bulk_create(yangi_guruhlar)
    if ozgargan_guruhlar:
        Guruh.objects.bulk_update(ozgargan_guruhlar, ["nomi"])
    reja.guruhlar.filter(raqam__gt=soni, yuklamalar__isnull=True).delete()
    keshni_tozala()
    return list(reja.guruhlar.all())


def fan_semestr_talabi(fs: FanSemestr, reja: OquvReja) -> dict[str, int | None]:
    """Soat turlari bo'yicha talab: ma'ruza x1, guruhli x guruh, kurs ishi 2x talaba."""
    talab: dict[str, int | None] = {}
    if fs.maruza_soat:
        talab[SoatTuri.MARUZA] = fs.maruza_soat
    for tur in PER_GURUH_TURLAR:
        soat = fs.tur_soat(tur)
        if soat:
            talab[tur] = (
                soat * reja.guruhlar_soni
                if reja.guruhlar_soni is not None and reja.guruhlar_soni > 0
                else None
            )
    if fs.kurs_ishi_bor:
        talab[SoatTuri.KURS_ISHI] = (
            KURS_ISHI_SOAT_TALABAGA * reja.talabalar_soni
            if reja.talabalar_soni is not None and reja.talabalar_soni > 0
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
    """Tanlangan o'quv yili uchun butun OTM bo'yicha talab va taqsimot."""
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
    """(fan_semestr, tur) bo'yicha taqsimlangan soatlar; dashboardlarda ishlatiladi."""
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


def _oqituvchi_qidiruv_sharti(q: str) -> Q:
    shart = Q()
    for soz in q.split():
        shart &= (
            Q(foydalanuvchi__first_name__icontains=soz)
            | Q(foydalanuvchi__last_name__icontains=soz)
            | Q(foydalanuvchi__telefon__icontains=soz)
            | Q(kafedra__nomi__icontains=soz)
            | Q(turi__nomi__icontains=soz)
        )
    return shart


def yuklama_kamomadi(
    akademik_yil: int,
    *,
    kafedra: Department | None = None,
    q: str = "",
) -> list[YuklamaHolati]:
    """Faol hamda joriy o'quv yilida darsi bor nofaol o'qituvchilar."""
    yuklama_qs = Yuklama.objects.akademik_yilda(akademik_yil)
    if kafedra is not None:
        yuklama_qs = yuklama_qs.filter(oqituvchi__kafedra=kafedra)
    soatlar = dict(yuklama_qs.values_list("oqituvchi_id").annotate(jami=Sum("soat")))
    oqituvchilar = OqituvchiProfil.objects.filter(
        Q(foydalanuvchi__is_active=True) | Q(pk__in=soatlar.keys())
    ).select_related("foydalanuvchi", "turi", "kafedra")
    if kafedra is not None:
        oqituvchilar = oqituvchilar.filter(kafedra=kafedra)
    if q.strip():
        oqituvchilar = oqituvchilar.filter(_oqituvchi_qidiruv_sharti(q.strip()))
    holatlar = [
        YuklamaHolati(
            oqituvchi=o, jami_soat=soatlar.get(o.pk, 0), min_soat=o.turi.min_soat
        )
        for o in oqituvchilar
    ]
    return sorted(holatlar, key=lambda h: h.kamomad, reverse=True)


@dataclass(frozen=True)
class SemestrTahrir:
    """FanSemestr dars soatlari taqsimotiga ofis tomonidan kiritilgan bitta tahrir."""

    fan_semestr_id: int
    maruza_soat: int
    amaliyot_soat: int
    laboratoriya_soat: int
    seminar_soat: int
    kurs_ishi_bor: bool


_TAHRIR_MAYDONLARI = AUDITORIYA_MAYDONLARI


@transaction.atomic
def semestrovka_yangilash(reja: OquvReja, tahrirlar: list[SemestrTahrir]) -> None:
    """Rejadagi semestrlar kesimidagi soat o'zgarishlarini bazaga saqlaydi."""
    idlar = [t.fan_semestr_id for t in tahrirlar]
    kaf_idlar = set(
        FanSemestr.objects.filter(
            pk__in=idlar, variant__fan__reja=reja, variant__kafedra__isnull=False
        ).values_list("variant__kafedra_id", flat=True)
    )
    _kafedralarni_qulflash(kaf_idlar)
    semestrlar = {
        fs.pk: fs
        for fs in FanSemestr.objects.select_for_update()
        .filter(pk__in=idlar, variant__fan__reja=reja)
        .select_related("variant__fan__reja", "variant__kafedra")
        .prefetch_related("yuklamalar")
        .order_by("pk")
    }
    ozgargan_fs, variantlar, ozgargan_yuklama = _semestrovka_yigish(
        tahrirlar, semestrlar, kaf_idlar
    )
    if ozgargan_fs:
        FanSemestr.objects.bulk_update(
            ozgargan_fs, [*_TAHRIR_MAYDONLARI.values(), "kurs_ishi_bor"]
        )
    if ozgargan_yuklama:
        Yuklama.objects.bulk_update(ozgargan_yuklama, ["soat"])
    _variantlar_soatini_yangila(variantlar)
    if variantlar:
        keshni_tozala()


def _semestrovka_yigish(
    tahrirlar: list[SemestrTahrir],
    semestrlar: dict[int, FanSemestr],
    kaf_idlar: set[int],
) -> tuple[list[FanSemestr], dict[int, FanVariant], list[Yuklama]]:
    qulflar = (
        {
            (k, y)
            for k, y in KafedraYuklamaTasdiq.objects.select_for_update()
            .filter(
                kafedra_id__in=kaf_idlar,
                holat__in=[
                    KafedraTasdiqHolati.TASDIQDA,
                    KafedraTasdiqHolati.TASDIQLANGAN,
                ],
            )
            .values_list("kafedra_id", "akademik_yil")
        }
        if kaf_idlar
        else set()
    )
    ozgargan_fs: list[FanSemestr] = []
    ozgargan_yuklama: list[Yuklama] = []
    variantlar: dict[int, FanVariant] = {}
    for tahrir in tahrirlar:
        fs = semestrlar.get(tahrir.fan_semestr_id)
        if fs is None:
            raise ValidationError("Semestr bu rejaga tegishli emas.")
        if not _semestr_ozgardimi(fs, tahrir):
            continue
        kaf = fs.variant.kafedra
        if kaf is not None and (kaf.pk, fs.akademik_yil) in qulflar:
            raise ValidationError(
                f"{kaf.nomi}: {fs.akademik_yil}/{fs.akademik_yil + 1} yuklamasi "
                "qulflangan — avval qaytarib oling."
            )
        _semestrni_ozgartir(fs, tahrir, ozgargan_yuklama)
        ozgargan_fs.append(fs)
        variantlar[fs.variant_id] = fs.variant
    return ozgargan_fs, variantlar, ozgargan_yuklama


def _semestrni_ozgartir(
    fs: FanSemestr, tahrir: SemestrTahrir, ozgargan_yuklama: list[Yuklama]
) -> None:
    yangi = {
        SoatTuri.MARUZA: tahrir.maruza_soat,
        SoatTuri.AMALIYOT: tahrir.amaliyot_soat,
        SoatTuri.LABORATORIYA: tahrir.laboratoriya_soat,
        SoatTuri.SEMINAR: tahrir.seminar_soat,
    }
    yuklamalar = list(fs.yuklamalar.all())
    _band_soatni_himoyalash(yuklamalar, yangi, tahrir.kurs_ishi_bor)
    for tur, maydon in _TAHRIR_MAYDONLARI.items():
        setattr(fs, maydon, yangi[tur])
    fs.kurs_ishi_bor = tahrir.kurs_ishi_bor
    for yuklama in yuklamalar:
        yuklama.fan_semestr = fs
        yuklama.soat = yuklama.hisoblangan_soat()
        ozgargan_yuklama.append(yuklama)


def _variantlar_soatini_yangila(variantlar: dict[int, FanVariant]) -> None:
    if not variantlar:
        return
    sem_guruh: dict[int, list[FanSemestr]] = {}
    for fs in FanSemestr.objects.filter(variant_id__in=variantlar):
        sem_guruh.setdefault(fs.variant_id, []).append(fs)
    for vid, variant in variantlar.items():
        fslar = sem_guruh.get(vid, [])
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
        if not any(fs.kurs_ishi_bor for fs in fslar):
            variant.kurs_ishi_soat = 0
        elif variant.kurs_ishi_soat == 0:
            variant.kurs_ishi_soat = KURS_ISHI_SOAT_TALABAGA
    FanVariant.objects.bulk_update(
        list(variantlar.values()),
        [
            "maruza_soat",
            "amaliyot_soat",
            "laboratoriya_soat",
            "seminar_soat",
            "auditoriya_soat",
            "kurs_ishi_soat",
        ],
    )


def _semestr_ozgardimi(fs: FanSemestr, tahrir: SemestrTahrir) -> bool:
    return (
        fs.maruza_soat != tahrir.maruza_soat
        or fs.amaliyot_soat != tahrir.amaliyot_soat
        or fs.laboratoriya_soat != tahrir.laboratoriya_soat
        or fs.seminar_soat != tahrir.seminar_soat
        or fs.kurs_ishi_bor != tahrir.kurs_ishi_bor
    )


def _band_soatni_himoyalash(
    yuklamalar: list[Yuklama], yangi: dict[str, int], kurs_ishi_bor: bool
) -> None:
    """O'qituvchiga taqsimlab bo'lingan soatlarni o'chiradigan tahrirni rad etadi."""
    band_turlar = {y.tur for y in yuklamalar}
    for tur in _TAHRIR_MAYDONLARI:
        if yangi[tur] == 0 and tur in band_turlar:
            raise ValidationError(
                f"{SoatTuri(tur).label}: soat 0 ga o'zgartirilmaydi — "
                "yuklama taqsimlangan."
            )
    if not kurs_ishi_bor and SoatTuri.KURS_ISHI in band_turlar:
        raise ValidationError("Kurs ishi olib tashlanmaydi — yuklama taqsimlangan.")


def _kafedralarni_qulflash(kafedra_idlar: set[int]) -> None:
    if not kafedra_idlar:
        return
    list(
        Department.objects.select_for_update()
        .filter(pk__in=sorted(kafedra_idlar))
        .order_by("pk")
    )


def _variant_yillari(variant_idlar: list[int]) -> dict[int, set[int]]:
    natija: dict[int, set[int]] = {}
    if not variant_idlar:
        return natija
    qatorlar = (
        FanSemestr.objects.filter(variant_id__in=variant_idlar)
        .values_list("variant_id", "variant__fan__reja__boshlanish_yili", "semestr")
        .distinct()
    )
    for v_id, bosh, sem in qatorlar:
        natija.setdefault(v_id, set()).add(bosh + (sem - 1) // 2)
    return natija


def _qulflangan_juftliklarni_tekshir(juftliklar: set[tuple[int, int]]) -> None:
    if not juftliklar:
        return
    kaf_ids = {k for k, _ in juftliklar}
    yillar = {y for _, y in juftliklar}
    tasdiqlar = (
        KafedraYuklamaTasdiq.objects.select_for_update()
        .filter(
            kafedra_id__in=kaf_ids,
            akademik_yil__in=yillar,
            holat__in=[KafedraTasdiqHolati.TASDIQDA, KafedraTasdiqHolati.TASDIQLANGAN],
        )
        .values_list("kafedra_id", "akademik_yil")
    )
    if any((k, y) in juftliklar for k, y in tasdiqlar):
        raise ValidationError(
            "Kafedra yuklamasi tasdiqqa yuborilgan yoki tasdiqlangan — qulflangan."
        )


@transaction.atomic
def variantni_tanlash(fan: Fan, variant: FanVariant) -> None:
    """Ofis admini tanlov bloki ichidan o'tiladigan aniq fanni tanlaydi."""
    kaf_idlar = set(
        FanVariant.objects.filter(fan_id=fan.pk, kafedra__isnull=False).values_list(
            "kafedra_id", flat=True
        )
    )
    _kafedralarni_qulflash(kaf_idlar)
    fan = (
        Fan.objects.select_for_update()
        .select_related("tanlangan_variant")
        .get(pk=fan.pk)
    )
    if fan.turi != FanTuri.TANLOV:
        raise ValidationError("Faqat tanlov fanlari uchun variant tanlanadi.")
    if variant.fan_id != fan.pk:
        raise ValidationError("Variant boshqa fanga tegishli.")
    if fan.tanlangan_variant_id is not None and fan.tanlangan_variant_id != variant.pk:
        if Yuklama.objects.filter(
            fan_semestr__variant_id=fan.tanlangan_variant_id
        ).exists():
            raise ValidationError("Fanda yuklamalar bor — avval ularni bekor qiling.")
        variant = FanVariant.objects.select_for_update().get(pk=variant.pk)
        yillar_map = _variant_yillari([fan.tanlangan_variant_id, variant.pk])
        juftliklar: set[tuple[int, int]] = set()
        if fan.tanlangan_variant and fan.tanlangan_variant.kafedra_id is not None:
            for y in yillar_map.get(fan.tanlangan_variant_id, set()):
                juftliklar.add((fan.tanlangan_variant.kafedra_id, y))
        if variant.kafedra_id is not None:
            for y in yillar_map.get(variant.pk, set()):
                juftliklar.add((variant.kafedra_id, y))
        _qulflangan_juftliklarni_tekshir(juftliklar)
    fan.tanlangan_variant = variant
    fan.save(update_fields=["tanlangan_variant"])


@transaction.atomic
def kafedraga_biriktirish(variant: FanVariant, kafedra: Department | None) -> None:
    """Ofis fanni bitta kafedraga biriktiradi (yoki boshqa kafedraga o'tkazadi)."""
    eski_kaf_id = (
        FanVariant.objects.filter(pk=variant.pk)
        .values_list("kafedra_id", flat=True)
        .first()
    )
    _kafedralarni_qulflash(
        {k for k in (eski_kaf_id, kafedra.pk if kafedra else None) if k is not None}
    )
    Fan.objects.select_for_update().filter(pk=variant.fan_id).first()
    variant = (
        FanVariant.objects.select_for_update()
        .select_related("fan", "kafedra")
        .get(pk=variant.pk)
    )
    if variant.fan.tanlangan_variant_id != variant.pk:
        raise ValidationError("Avval fan variantini tanlang.")
    yangi_kaf_id = kafedra.pk if kafedra else None
    if variant.kafedra_id != yangi_kaf_id:
        if (
            variant.kafedra_id is not None
            and Yuklama.objects.filter(fan_semestr__variant=variant).exists()
        ):
            raise ValidationError("Fanda yuklamalar bor — avval ularni bekor qiling.")
        yillar = _variant_yillari([variant.pk]).get(variant.pk, set())
        juftliklar = {
            (k, y)
            for k in (variant.kafedra_id, yangi_kaf_id)
            if k is not None
            for y in yillar
        }
        _qulflangan_juftliklarni_tekshir(juftliklar)
    variant.kafedra = kafedra
    variant.save(update_fields=["kafedra"])


@transaction.atomic
def kafedraga_ommaviy_biriktirish(
    variant_idlar: list[int], kafedra: Department | None
) -> int:
    """Bir nechta FanVariant qatorini bitta kafedraga biriktiradi (yoki yechadi)."""
    noyob_idlar = sorted(set(variant_idlar))
    if not noyob_idlar:
        return 0
    kaf_idlar = set(
        FanVariant.objects.filter(
            pk__in=noyob_idlar, kafedra__isnull=False
        ).values_list("kafedra_id", flat=True)
    )
    if kafedra is not None:
        kaf_idlar.add(kafedra.pk)
    _kafedralarni_qulflash(kaf_idlar)
    fan_ids = sorted(
        set(
            FanVariant.objects.filter(pk__in=noyob_idlar).values_list(
                "fan_id", flat=True
            )
        )
    )
    list(Fan.objects.select_for_update().filter(pk__in=fan_ids).order_by("pk"))
    variantlar = list(
        FanVariant.objects.select_for_update()
        .select_related("fan")
        .filter(pk__in=noyob_idlar)
        .order_by("pk")
    )
    if len(variantlar) != len(noyob_idlar):
        raise ValidationError("Tanlangan fanlarning ayrimlari topilmadi.")
    return _ommaviy_biriktirish_qolla(variantlar, noyob_idlar, kafedra)


def _ommaviy_biriktirish_qolla(
    variantlar: list[FanVariant], noyob_idlar: list[int], kafedra: Department | None
) -> int:
    band_variantlar = set(
        Yuklama.objects.filter(fan_semestr__variant_id__in=noyob_idlar).values_list(
            "fan_semestr__variant_id", flat=True
        )
    )
    yillar_map = _variant_yillari(noyob_idlar)
    yangi_kaf_id = kafedra.pk if kafedra else None
    juftliklar: set[tuple[int, int]] = set()
    yangilanadigan: list[FanVariant] = []
    for variant in variantlar:
        if variant.fan.tanlangan_variant_id != variant.pk:
            raise ValidationError("Tanlangan fanlar orasida varianti tanlanmagani bor.")
        if variant.kafedra_id is not None and variant.kafedra_id != yangi_kaf_id:
            if variant.pk in band_variantlar:
                raise ValidationError(
                    f"«{variant.nomi}» fanida yuklamalar bor — avval bekor qiling."
                )
        if variant.kafedra_id != yangi_kaf_id:
            for k in (variant.kafedra_id, yangi_kaf_id):
                if k is not None:
                    for y in yillar_map.get(variant.pk, set()):
                        juftliklar.add((k, y))
            variant.kafedra = kafedra
            yangilanadigan.append(variant)
    _qulflangan_juftliklarni_tekshir(juftliklar)
    if yangilanadigan:
        FanVariant.objects.bulk_update(yangilanadigan, ["kafedra"])
        keshni_tozala()
    return len(yangilanadigan)


def eng_kop_kurs_ishi_talabasi(reja: OquvReja) -> int:
    """Rejadagi istalgan semestrda kurs ishiga biriktirilgan eng ko'p talaba soni."""
    return (
        Yuklama.objects.filter(
            fan_semestr__variant__fan__reja=reja,
            tur=SoatTuri.KURS_ISHI,
        )
        .values("fan_semestr_id")
        .annotate(jami=Sum("talabalar_soni"))
        .order_by("-jami")
        .values_list("jami", flat=True)
        .first()
        or 0
    )


def eng_katta_band_guruh(reja: OquvReja) -> int:
    """Rejadagi Yuklamasi bor eng katta tartib raqamli guruhni qaytaradi."""
    return (
        Yuklama.objects.filter(
            fan_semestr__variant__fan__reja=reja,
            guruh__isnull=False,
        )
        .order_by("-guruh__raqam")
        .values_list("guruh__raqam", flat=True)
        .first()
        or 0
    )


def reja_qulflanganmi(reja: OquvReja) -> bool:
    """Rejadagi biror kafedra yuklamani tasdiqqa yuborgan bo'lsa True qaytaradi."""
    fslar = (
        FanSemestr.objects.reja_uchun(reja)
        .filter(variant__kafedra__isnull=False)
        .values_list("variant__kafedra_id", "semestr")
    )
    juftlar = {
        (kafedra_id, reja.boshlanish_yili + (semestr - 1) // 2)
        for kafedra_id, semestr in fslar
    }
    if not juftlar:
        return False
    shart = Q()
    for kafedra_id, yil in juftlar:
        shart |= Q(kafedra_id=kafedra_id, akademik_yil=yil)
    return KafedraYuklamaTasdiq.objects.filter(
        shart,
        holat__in=(
            KafedraTasdiqHolati.TASDIQDA,
            KafedraTasdiqHolati.TASDIQLANGAN,
        ),
    ).exists()


def kafedra_tasdiq_oqish(
    kafedra: Department, akademik_yil: int
) -> KafedraYuklamaTasdiq | None:
    """Bazaga yozmasdan mavjud tasdiq yozuvini o'qib beradi."""
    return KafedraYuklamaTasdiq.objects.filter(
        kafedra=kafedra, akademik_yil=akademik_yil
    ).first()


def tasdiq_qulflanganmi(tasdiq: KafedraYuklamaTasdiq | None) -> bool:
    """Tasdiq holati o'qituvchi yuklamasini o'zgartirishni qulflagan bo'lsa True."""
    return tasdiq is not None and tasdiq.holat in (
        KafedraTasdiqHolati.TASDIQDA,
        KafedraTasdiqHolati.TASDIQLANGAN,
    )


def kafedra_tasdiq_holati(
    kafedra: Department, akademik_yil: int
) -> KafedraYuklamaTasdiq:
    """Kafedra va o'quv yili uchun tasdiq yozuvini topadi yoki yangi yaratadi."""
    tasdiq, _ = KafedraYuklamaTasdiq.objects.get_or_create(
        kafedra=kafedra,
        akademik_yil=akademik_yil,
        defaults={"holat": KafedraTasdiqHolati.QORALAMA},
    )
    return tasdiq


def kafedra_yuklama_qulflanganmi(kafedra: Department, akademik_yil: int) -> bool:
    """Kafedra yuklamasi tahrirlashdan qulflanganmi yo'qmi tekshiradi."""
    return tasdiq_qulflanganmi(kafedra_tasdiq_oqish(kafedra, akademik_yil))


@transaction.atomic
def yuklamani_tasdiqqa_yuborish(
    kafedra: Department, akademik_yil: int, izoh: str = ""
) -> KafedraYuklamaTasdiq:
    """Kafedra yuklamasini o'quv bo'limi tasdig'iga yuboradi."""
    Department.objects.select_for_update().filter(pk=kafedra.pk).first()
    tasdiq = kafedra_tasdiq_holati(kafedra, akademik_yil)
    tasdiq = KafedraYuklamaTasdiq.objects.select_for_update().get(pk=tasdiq.pk)
    if tasdiq.holat == KafedraTasdiqHolati.TASDIQLANGAN:
        raise ValidationError("Yuklama allaqachon tasdiqlangan.")
    if tasdiq.holat == KafedraTasdiqHolati.TASDIQDA:
        raise ValidationError("Yuklama allaqachon tasdiqqa yuborilgan.")
    tasdiq.holat = KafedraTasdiqHolati.TASDIQDA
    tasdiq.yuborilgan_vaqt = timezone.now()
    tasdiq.tasdiqlagan = None
    tasdiq.tasdiqlangan_vaqt = None
    tasdiq.izoh = izoh
    tasdiq.save()
    return tasdiq


@transaction.atomic
def yuklamani_tasdiqlash(
    kafedra: Department,
    akademik_yil: int,
    admin: Foydalanuvchi,
    izoh: str = "",
) -> KafedraYuklamaTasdiq:
    """Ofis admini kafedraning yillik yuklamasini tasdiqlaydi va qulflaydi."""
    Department.objects.select_for_update().filter(pk=kafedra.pk).first()
    tasdiq = kafedra_tasdiq_holati(kafedra, akademik_yil)
    tasdiq = KafedraYuklamaTasdiq.objects.select_for_update().get(pk=tasdiq.pk)
    if tasdiq.holat == KafedraTasdiqHolati.TASDIQLANGAN:
        raise ValidationError("Yuklama allaqachon tasdiqlangan.")
    if tasdiq.holat != KafedraTasdiqHolati.TASDIQDA:
        raise ValidationError(
            "Tasdiqlash uchun yuklama avval kafedra tomonidan yuborilishi kerak."
        )
    tasdiq.holat = KafedraTasdiqHolati.TASDIQLANGAN
    tasdiq.tasdiqlangan_vaqt = timezone.now()
    tasdiq.tasdiqlagan = admin
    tasdiq.izoh = izoh
    tasdiq.save()
    return tasdiq


def _bosh_guruhlar_tanlash(
    fs: FanSemestr, tur: str, reja_guruhlar: list[Guruh]
) -> list[Guruh]:
    band_guruh_idlar = set(
        Yuklama.objects.select_for_update()
        .filter(fan_semestr=fs, tur=tur)
        .values_list("guruh_id", flat=True)
    )
    bosh_guruhlar = [g for g in reja_guruhlar if g.pk not in band_guruh_idlar]
    if not bosh_guruhlar:
        raise ValidationError("Barcha guruhlar allaqachon taqsimlangan.")
    return bosh_guruhlar


def _guruh_yuklamalarini_yarat(
    fs: FanSemestr, oqituvchi: OqituvchiProfil, tur: str, bosh_guruhlar: list[Guruh]
) -> list[Yuklama]:
    namuna = Yuklama(
        fan_semestr=fs, tur=tur, oqituvchi=oqituvchi, guruh=bosh_guruhlar[0]
    )
    namuna.full_clean()
    soat = namuna.hisoblangan_soat()
    yangi_yuklamalar = [
        Yuklama(
            fan_semestr=fs,
            tur=tur,
            oqituvchi=oqituvchi,
            guruh=guruh,
            soat=soat,
        )
        for guruh in bosh_guruhlar
    ]
    Yuklama.objects.bulk_create(yangi_yuklamalar)
    keshni_tozala()
    return yangi_yuklamalar


@transaction.atomic
def guruhlarga_ommaviy_taqsimlash(
    fs: FanSemestr, oqituvchi: OqituvchiProfil, tur: str
) -> list[Yuklama]:
    """`fs` ning `tur` bo'yicha hali bo'sh guruhlarini `oqituvchi` ga biriktiradi."""
    if not tur or tur not in PER_GURUH_TURLAR:
        raise ValidationError("O'qituvchi yoki mashg'ulot turi tanlanmadi.")
    if not oqituvchi.foydalanuvchi.is_active:
        raise ValidationError("Faolsizlantirilgan o'qituvchiga yuklama berilmaydi.")
    if fs.variant.kafedra_id is not None:
        _kafedralarni_qulflash({fs.variant.kafedra_id})
    fs = (
        FanSemestr.objects.select_for_update()
        .select_related("variant__fan__reja", "variant__kafedra")
        .get(pk=fs.pk)
    )
    if fs.variant.kafedra_id is not None:
        _qulflangan_juftliklarni_tekshir({(fs.variant.kafedra_id, fs.akademik_yil)})
    reja_guruhlar = list(
        fs.variant.fan.reja.guruhlar.select_for_update().order_by("raqam")
    )
    bosh_guruhlar = _bosh_guruhlar_tanlash(fs, tur, reja_guruhlar)
    return _guruh_yuklamalarini_yarat(fs, oqituvchi, tur, bosh_guruhlar)


@transaction.atomic
def yuklamani_qaytarish(
    kafedra: Department,
    akademik_yil: int,
    admin: Foydalanuvchi,
    izoh: str = "",
) -> KafedraYuklamaTasdiq:
    """Ofis admini kafedra yuklamasini qayta ko'rib chiqish uchun orqaga qaytaradi."""
    Department.objects.select_for_update().filter(pk=kafedra.pk).first()
    tasdiq = kafedra_tasdiq_holati(kafedra, akademik_yil)
    tasdiq = KafedraYuklamaTasdiq.objects.select_for_update().get(pk=tasdiq.pk)
    if tasdiq.holat not in (
        KafedraTasdiqHolati.TASDIQDA,
        KafedraTasdiqHolati.TASDIQLANGAN,
    ):
        raise ValidationError(
            "Qaytarib yuborish uchun avval yuklama tasdiqqa yuborilgan bo'lishi kerak."
        )
    tasdiq.holat = KafedraTasdiqHolati.QAYTARILGAN
    tasdiq.tasdiqlagan = admin
    tasdiq.tasdiqlangan_vaqt = None
    tasdiq.izoh = izoh
    tasdiq.save()
    return tasdiq
