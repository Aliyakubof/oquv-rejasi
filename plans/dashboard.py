"""Read-only aggregation feeding the office and kafedra dashboards.

Past academic years are never offered: the UI's year selector is built only
from tanlanadigan_yillar(), which floors at the current academic year.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from django.db.models import Count, Prefetch, Q, Sum
from django.utils import timezone

from accounts.models import Department, OqituvchiProfil
from plans.models import (
    Fan,
    FanSemestr,
    FanVariant,
    Guruh,
    KafedraYuklamaTasdiq,
    OquvReja,
    Yuklama,
)
from plans.services import (
    TalabSatri,
    fan_semestr_talabi,
    ofis_taqsimoti,
    taqsimlangan_soatlar,
    taqsimot_hisoboti,
)


def joriy_akademik_yil(bugun: date | None = None) -> int:
    """O'quv yili sentyabrda boshlanadi: 2026-07 -> 2025 ("2025/2026")."""
    bugun = bugun or timezone.localdate()
    return bugun.year if bugun.month >= 9 else bugun.year - 1


def tanlanadigan_yillar() -> list[int]:
    """Academic years offered in the UI: current and future only.

    Built over ALL FanSemestr rows (not just effektiv) so a year containing
    only unselected tanlov slots still appears.
    """
    joriy = joriy_akademik_yil()
    yillar = (
        FanSemestr.objects.akademik_yil_bilan()
        # Model ordering leaks semestr into SELECT DISTINCT; clear it.
        .order_by()
        .values_list("akademik_yili", flat=True)
        .distinct()
    )
    return sorted(y for y in yillar if y >= joriy)


def yilni_tanlash(sorov_yil: str | None) -> tuple[list[int], int | None]:
    """Validate the requested year against the offered (non-past) list."""
    yillar = tanlanadigan_yillar()
    if not yillar:
        return [], None
    if (
        sorov_yil
        and sorov_yil.isascii()
        and sorov_yil.isdigit()
        and int(sorov_yil) in yillar
    ):
        return yillar, int(sorov_yil)
    joriy = joriy_akademik_yil()
    return yillar, joriy if joriy in yillar else yillar[0]


@dataclass(frozen=True)
class DashboardStat:
    """KPI card values computed from one list of TalabSatri rows."""

    jami_soat: int
    tur_soatlari: dict[str, int]
    kafedraga_biriktirilgan_soat: int
    kafedraga_biriktirilmagan_soat: int
    oqituvchiga_taqsimlangan_soat: int
    taqsimlanmagan_soat: int
    nomalum_talab_soni: int
    tur_taqsimlangan: dict[str, int] = field(default_factory=dict)


def statlarni_hisoblash(satrlar: list[TalabSatri]) -> DashboardStat:
    tur_soatlari: dict[str, int] = defaultdict(int)
    tur_taqsimlangan: dict[str, int] = defaultdict(int)
    biriktirilgan = biriktirilmagan = taqsimlangan = taqsimlanmagan = nomalum = 0
    for satr in satrlar:
        taqsimlangan += satr.taqsimlangan_soat
        tur_taqsimlangan[satr.tur] += satr.taqsimlangan_soat
        if satr.talab_soat is None:
            nomalum += 1
            continue
        tur_soatlari[satr.tur] += satr.talab_soat
        if satr.fan_semestr.variant.kafedra_id is None:
            biriktirilmagan += satr.talab_soat
        else:
            biriktirilgan += satr.talab_soat
        taqsimlanmagan += max(0, satr.qoldiq_soat)
    return DashboardStat(
        jami_soat=sum(tur_soatlari.values()),
        tur_soatlari=dict(tur_soatlari),
        kafedraga_biriktirilgan_soat=biriktirilgan,
        kafedraga_biriktirilmagan_soat=biriktirilmagan,
        oqituvchiga_taqsimlangan_soat=taqsimlangan,
        taqsimlanmagan_soat=taqsimlanmagan,
        nomalum_talab_soni=nomalum,
        tur_taqsimlangan=dict(tur_taqsimlangan),
    )


def jami_talabalar(akademik_yil: int) -> int:
    reja_idlar = (
        FanSemestr.objects.akademik_yilda(akademik_yil)
        .values_list("variant__fan__reja_id", flat=True)
        .distinct()
    )
    jami = OquvReja.objects.filter(pk__in=reja_idlar).aggregate(
        jami=Sum("talabalar_soni")
    )["jami"]
    return jami or 0


@dataclass(frozen=True)
class FanSatri:
    """One dashboard course row: a fan's in-year demand and allocation."""

    fan: Fan
    fan_semestrlar: list[FanSemestr]
    tur_soatlari: dict[str, int | None]
    taqsimlangan_soat: int
    kafedra: Department | None
    tanlanmagan: bool

    @property
    def jami_soat(self) -> int:
        return sum(soat for soat in self.tur_soatlari.values() if soat)

    @property
    def biriktirilmagan(self) -> bool:
        return self.kafedra is None

    @property
    def variant(self) -> "FanVariant":
        """Selected variant, or the representative one for unselected tanlov."""
        if not self.tanlanmagan and self.fan_semestrlar:
            return self.fan_semestrlar[0].variant
        if self.fan.tanlangan_variant_id is not None:
            return self.fan.tanlangan_variant
        return self.fan_semestrlar[0].variant


def ofis_fan_satrlari(
    akademik_yil: int, *, fan_id: int | None = None
) -> list[FanSatri]:
    """Course rows for the office dashboard, unallocated ones flagged.

    Unselected tanlov slots are included with their first variant's semesters
    as representative demand — alternatives share the slot's semester
    distribution by importer design.
    """
    satrlar = _effektiv_satrlar(akademik_yil, fan_id=fan_id) + _tanlov_satrlari(
        akademik_yil, fan_id=fan_id
    )
    return sorted(satrlar, key=lambda satr: (satr.fan.reja_id, satr.fan.raqam))


def _effektiv_satrlar(
    akademik_yil: int, *, fan_id: int | None = None
) -> list[FanSatri]:
    semestrlar = (
        FanSemestr.objects.effektiv()
        .akademik_yilda(akademik_yil)
        .select_related(
            "variant__fan__reja",
            "variant__fan__tanlangan_variant",
            "variant__kafedra",
        )
        .order_by("semestr")
    )
    if fan_id is not None:
        semestrlar = semestrlar.filter(variant__fan_id=fan_id)
    taqsimlangan = taqsimlangan_soatlar(semestrlar)
    fs_taqsimlangan: dict[int, int] = defaultdict(int)
    for (fs_pk, _), soat in taqsimlangan.items():
        fs_taqsimlangan[fs_pk] += soat
    guruhlar: dict[int, list[FanSemestr]] = defaultdict(list)
    for fs in semestrlar:
        guruhlar[fs.variant.fan_id].append(fs)
    return [
        FanSatri(
            fan=fslar[0].variant.fan,
            fan_semestrlar=fslar,
            tur_soatlari=_tur_yigindisi(fslar),
            taqsimlangan_soat=sum(fs_taqsimlangan[fs.pk] for fs in fslar),
            kafedra=fslar[0].variant.kafedra,
            tanlanmagan=False,
        )
        for fslar in guruhlar.values()
    ]


def _tanlov_satrlari(akademik_yil: int, *, fan_id: int | None = None) -> list[FanSatri]:
    semestrlar = (
        FanSemestr.objects.akademik_yilda(akademik_yil)
        .filter(variant__fan__in=Fan.objects.tanlov_kutilmoqda())
        .select_related("variant__fan__reja")
        .prefetch_related("variant__fan__variantlar")
        .order_by("variant_id", "semestr")
    )
    if fan_id is not None:
        semestrlar = semestrlar.filter(variant__fan_id=fan_id)
    guruhlar: dict[int, list[FanSemestr]] = defaultdict(list)
    for fs in semestrlar:
        guruhlar[fs.variant.fan_id].append(fs)
    satrlar = []
    for fslar in guruhlar.values():
        birinchi_variant = fslar[0].variant_id
        vakil_fslar = [fs for fs in fslar if fs.variant_id == birinchi_variant]
        satrlar.append(
            FanSatri(
                fan=vakil_fslar[0].variant.fan,
                fan_semestrlar=vakil_fslar,
                tur_soatlari=_tur_yigindisi(vakil_fslar),
                taqsimlangan_soat=0,
                kafedra=None,
                tanlanmagan=True,
            )
        )
    return satrlar


def _tur_yigindisi(fslar: list[FanSemestr]) -> dict[str, int | None]:
    """Sum per-type demand over semesters; None (count missing) is sticky."""
    jami: dict[str, int | None] = {}
    for fs in fslar:
        for tur, soat in fan_semestr_talabi(fs, fs.variant.fan.reja).items():
            if tur not in jami:
                jami[tur] = soat
            elif jami[tur] is None or soat is None:
                jami[tur] = None
            else:
                jami[tur] += soat
    return jami


@dataclass(frozen=True)
class SemestrovkaSatri:
    """One reja-detail row: a fan's weekly load across every semester."""

    fan: Fan
    variant: FanVariant
    semestr_soatlari: dict[int, FanSemestr]
    tanlanmagan: bool

    @property
    def kafedra(self) -> Department | None:
        return self.variant.kafedra if not self.tanlanmagan else None

    @property
    def biriktirilmagan(self) -> bool:
        return self.kafedra is None


def reja_semestrovkasi(reja: OquvReja) -> list[SemestrovkaSatri]:
    """The semestrovka: per-fan per-semester split rows for one reja."""
    fanlar = reja.fanlar.select_related("tanlangan_variant__kafedra").prefetch_related(
        "tanlangan_variant__semestrlar",
        "variantlar__semestrlar",
        "variantlar__kafedra",
    )
    satrlar = []
    for fan in fanlar:
        variant = fan.effektiv_variant
        if variant is None:
            continue
        satrlar.append(
            SemestrovkaSatri(
                fan=fan,
                variant=variant,
                semestr_soatlari={fs.semestr: fs for fs in variant.semestrlar.all()},
                tanlanmagan=fan.tanlangan_variant_id is None,
            )
        )
    return satrlar


@dataclass(frozen=True)
class OqituvchiYuklamasi:
    """One teacher's slice of a course-semester, for read-only display."""

    oqituvchi: OqituvchiProfil
    tur_matni: str
    guruh: Guruh | None


@dataclass(frozen=True)
class SemestrKesimSatri:
    """One reja-by-semester row: a course as taught in one specific semester."""

    fan: Fan
    variant: FanVariant
    fan_semestr: FanSemestr
    tanlanmagan: bool
    talab_satrlari: list[TalabSatri]
    yuklamalar: list[OqituvchiYuklamasi]

    @property
    def kafedra(self) -> Department | None:
        return self.variant.kafedra if not self.tanlanmagan else None

    @property
    def biriktirilmagan(self) -> bool:
        return self.kafedra is None

    @property
    def taqsimlangan(self) -> bool:
        return bool(self.talab_satrlari) and all(
            (t.qoldiq_soat or 0) <= 0 for t in self.talab_satrlari
        )


def reja_semestr_kesimi(
    reja: OquvReja,
    *,
    satrlar: list[SemestrovkaSatri] | None = None,
    taqsimot: list[TalabSatri] | None = None,
) -> dict[int, list[SemestrKesimSatri]]:
    """Per-semester course rows for one reja, keyed by semester number."""
    talablar: dict[int, list[TalabSatri]] = defaultdict(list)
    for satr in taqsimot if taqsimot is not None else taqsimot_hisoboti(reja):
        talablar[satr.fan_semestr.pk].append(satr)
    yuklamalar = _fan_semestr_yuklamalari(reja)

    kesim: dict[int, list[SemestrKesimSatri]] = defaultdict(list)
    semestrovka = satrlar if satrlar is not None else reja_semestrovkasi(reja)
    for fan_satri in semestrovka:
        for fs in fan_satri.semestr_soatlari.values():
            kesim[fs.semestr].append(
                SemestrKesimSatri(
                    fan=fan_satri.fan,
                    variant=fan_satri.variant,
                    fan_semestr=fs,
                    tanlanmagan=fan_satri.tanlanmagan,
                    talab_satrlari=talablar.get(fs.pk, []),
                    yuklamalar=yuklamalar.get(fs.pk, []),
                )
            )
    return dict(kesim)


def _fan_semestr_yuklamalari(
    reja: OquvReja,
) -> dict[int, list[OqituvchiYuklamasi]]:
    qatorlar = Yuklama.objects.filter(
        fan_semestr__variant__fan__reja=reja
    ).select_related("oqituvchi__foydalanuvchi", "guruh")
    natija: dict[int, list[OqituvchiYuklamasi]] = defaultdict(list)
    for yuklama in qatorlar:
        natija[yuklama.fan_semestr_id].append(
            OqituvchiYuklamasi(
                oqituvchi=yuklama.oqituvchi,
                tur_matni=yuklama.get_tur_display(),
                guruh=yuklama.guruh,
            )
        )
    return dict(natija)


@dataclass(frozen=True)
class KafedraQamrov:
    """Per-department coverage: delegated demand vs teacher-assigned hours."""

    kafedra: Department
    biriktirilgan_soat: int
    taqsimlangan_soat: int
    oqituvchilar_soni: int
    tasdiq: KafedraYuklamaTasdiq | None = None


def _kafedralar_oqituvchilar_bilan():
    return (
        Department.objects.select_related("mudir__foydalanuvchi")
        .prefetch_related(
            Prefetch(
                "oqituvchilar",
                queryset=OqituvchiProfil.objects.filter(
                    foydalanuvchi__is_active=True
                ).select_related("foydalanuvchi"),
            )
        )
        .annotate(
            oqituvchilar_soni=Count(
                "oqituvchilar",
                filter=Q(oqituvchilar__foydalanuvchi__is_active=True),
            )
        )
        .order_by("nomi")
    )


def kafedra_qamrovi(
    akademik_yil: int, *, taqsimot: list[TalabSatri] | None = None
) -> list[KafedraQamrov]:
    biriktirilgan: dict[int, int] = defaultdict(int)
    taqsimlangan: dict[int, int] = defaultdict(int)
    satrlar = taqsimot if taqsimot is not None else ofis_taqsimoti(akademik_yil)
    for satr in satrlar:
        kafedra_id = satr.fan_semestr.variant.kafedra_id
        if kafedra_id is None:
            continue
        if satr.talab_soat:
            biriktirilgan[kafedra_id] += satr.talab_soat
        taqsimlangan[kafedra_id] += satr.taqsimlangan_soat
    tasdiqlar = {
        t.kafedra_id: t
        for t in KafedraYuklamaTasdiq.objects.filter(akademik_yil=akademik_yil)
    }
    return [
        KafedraQamrov(
            kafedra=kafedra,
            biriktirilgan_soat=biriktirilgan.get(kafedra.pk, 0),
            taqsimlangan_soat=taqsimlangan.get(kafedra.pk, 0),
            oqituvchilar_soni=kafedra.oqituvchilar_soni,
            tasdiq=tasdiqlar.get(kafedra.pk),
        )
        for kafedra in _kafedralar_oqituvchilar_bilan()
    ]
