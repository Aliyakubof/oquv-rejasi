"""Delegation state for the kafedra head's assignment panel.

Shapes one FanSemestr's demand into per-type sections the UI can render:
a single lecture slot, one slot per guruh for group types, and a
student-count ledger for kurs ishi.
"""

from collections import defaultdict
from dataclasses import dataclass

from accounts.models import Department
from plans.models import PER_GURUH_TURLAR, FanSemestr, Guruh, SoatTuri, Yuklama
from plans.services import (
    TalabSatri,
    fan_semestr_talabi,
    kafedra_taqsimoti,
    taqsimlangan_soatlar,
)


@dataclass(frozen=True)
class GuruhSlot:
    guruh: Guruh
    yuklama: Yuklama | None


@dataclass(frozen=True)
class TurHolati:
    """One hour type's delegation section inside the panel."""

    tur: str
    tur_nomi: str
    talab_soat: int | None
    taqsimlangan_soat: int
    guruh_soat: int
    maruza_yuklama: Yuklama | None
    guruh_slotlar: list[GuruhSlot]
    kurs_ishi_yuklamalar: list[Yuklama]
    qolgan_talabalar: int | None

    @property
    def qoldiq_soat(self) -> int | None:
        if self.talab_soat is None:
            return None
        return self.talab_soat - self.taqsimlangan_soat

    @property
    def band_oqituvchi_idlar(self) -> set[int]:
        return {y.oqituvchi_id for y in self.kurs_ishi_yuklamalar}


def fan_semestr_holati(fs: FanSemestr) -> list[TurHolati]:
    reja = fs.variant.fan.reja
    yuklamalar = list(fs.yuklamalar.select_related("oqituvchi__foydalanuvchi", "guruh"))
    guruhlar = list(reja.guruhlar.all())
    return [
        _tur_holati(fs, tur, talab, yuklamalar, guruhlar, reja.talabalar_soni)
        for tur, talab in fan_semestr_talabi(fs, reja).items()
    ]


def _tur_holati(
    fs: FanSemestr,
    tur: str,
    talab: int | None,
    yuklamalar: list[Yuklama],
    guruhlar: list[Guruh],
    talabalar_soni: int | None,
) -> TurHolati:
    turdagilar = [y for y in yuklamalar if y.tur == tur]
    slotlar: list[GuruhSlot] = []
    if tur in PER_GURUH_TURLAR:
        guruh_boyicha = {y.guruh_id: y for y in turdagilar}
        slotlar = [GuruhSlot(g, guruh_boyicha.get(g.pk)) for g in guruhlar]
    kurs_ishi = turdagilar if tur == SoatTuri.KURS_ISHI else []
    qolgan = None
    if tur == SoatTuri.KURS_ISHI and talabalar_soni is not None:
        qolgan = talabalar_soni - sum(y.talabalar_soni or 0 for y in kurs_ishi)
    return TurHolati(
        tur=tur,
        tur_nomi=SoatTuri(tur).label,
        talab_soat=talab,
        taqsimlangan_soat=sum(y.soat for y in turdagilar),
        guruh_soat=fs.tur_soat(tur) if tur != SoatTuri.KURS_ISHI else 0,
        maruza_yuklama=(
            turdagilar[0] if tur == SoatTuri.MARUZA and turdagilar else None
        ),
        guruh_slotlar=slotlar,
        kurs_ishi_yuklamalar=kurs_ishi,
        qolgan_talabalar=qolgan,
    )


@dataclass(frozen=True)
class FsSatri:
    """One dashboard row: a fan-semester with its per-type demand lines."""

    fan_semestr: FanSemestr
    turlar: dict[str, TalabSatri]

    @property
    def qoldiq_bor(self) -> bool:
        return any(
            t.talab_soat is None or (t.qoldiq_soat or 0) > 0
            for t in self.turlar.values()
        )


def kafedra_fs_satrlari(kafedra: Department, akademik_yil: int) -> list[FsSatri]:
    guruhlangan: dict[int, dict[str, TalabSatri]] = defaultdict(dict)
    for satr in kafedra_taqsimoti(kafedra, akademik_yil):
        guruhlangan[satr.fan_semestr.pk][satr.tur] = satr
    satrlar = [
        FsSatri(next(iter(turlar.values())).fan_semestr, turlar)
        for turlar in guruhlangan.values()
    ]
    return sorted(
        satrlar,
        key=lambda s: (
            s.fan_semestr.variant.fan.reja_id,
            s.fan_semestr.variant.fan.raqam,
            s.fan_semestr.semestr,
        ),
    )


def fs_satri(fs: FanSemestr) -> FsSatri:
    """Rebuild a single row after a mutation, without the full-year query."""
    reja = fs.variant.fan.reja
    taqsimlangan = taqsimlangan_soatlar(FanSemestr.objects.filter(pk=fs.pk))
    turlar = {
        tur: TalabSatri(fs, tur, talab, taqsimlangan.get((fs.pk, tur), 0))
        for tur, talab in fan_semestr_talabi(fs, reja).items()
    }
    return FsSatri(fan_semestr=fs, turlar=turlar)
