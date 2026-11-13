"""Shared 1-shakl (individual teacher workload) row aggregation helpers."""

from collections import defaultdict

from accounts.models import OqituvchiProfil
from plans.models import SoatTuri, Yuklama


def shakl1_guruh_matni(qator: dict[str, object]) -> str:
    """Format group or stream description for a 1-shakl row."""
    guruh_nomi = qator.get("_guruh_nomi")
    if guruh_nomi:
        return str(guruh_nomi)
    talabalar = int(qator.get("_talabalar_soni", 0))
    maruza_bor = int(qator.get("maruza", 0)) > 0
    if maruza_bor and talabalar > 0:
        return f"Oqim ({talabalar} talaba)"
    if talabalar > 0:
        return f"{talabalar} talaba"
    return "Oqim"


def _yangi_shakl1_qator(y: Yuklama) -> dict[str, object]:
    fs = y.fan_semestr
    reja = fs.variant.fan.reja
    return {
        "fan": fs.variant.nomi,
        "kodi": fs.variant.kodi,
        "yonalish": f"{reja.yonalish_kodi} {reja.yonalish_nomi}",
        "kurs": (fs.semestr + 1) // 2,
        "semestr": fs.semestr,
        "guruh": "Oqim",
        "_guruh_nomi": y.guruh.nomi if y.guruh else "",
        "_talabalar_soni": 0,
        "maruza": 0,
        "amaliyot": 0,
        "laboratoriya": 0,
        "seminar": 0,
        "kurs_ishi": 0,
        "jami": 0,
    }


def shakl1_satrlarini_yigish(
    yuklamalar: list[Yuklama],
) -> tuple[list[dict[str, object]], dict[str, int]]:
    """Group workload rows by course-semester and group for 1-shakl display."""
    tur_jami: dict[str, int] = defaultdict(int)
    shakl1_qatorlar: dict[tuple[int, int | None], dict[str, object]] = {}
    for y in yuklamalar:
        tur_jami[y.tur] += y.soat
        kalit = (y.fan_semestr_id, y.guruh_id)
        if kalit not in shakl1_qatorlar:
            shakl1_qatorlar[kalit] = _yangi_shakl1_qator(y)
        qator = shakl1_qatorlar[kalit]
        if y.talabalar_soni:
            qator["_talabalar_soni"] = int(qator["_talabalar_soni"]) + y.talabalar_soni
        tur_kalit = y.tur.lower()
        if tur_kalit in qator:
            qator[tur_kalit] = int(qator[tur_kalit]) + y.soat
        qator["jami"] = int(qator["jami"]) + y.soat
        qator["guruh"] = shakl1_guruh_matni(qator)
    return list(shakl1_qatorlar.values()), tur_jami


def oqituvchi_yuklamalari(profil: OqituvchiProfil, akademik_yil: int) -> list[Yuklama]:
    """Fetch pre-joined Yuklama rows for one teacher in an academic year."""
    return list(
        Yuklama.objects.filter(oqituvchi=profil)
        .akademik_yilda(akademik_yil)
        .select_related("fan_semestr__variant__fan__reja", "guruh")
        .order_by("fan_semestr__semestr", "fan_semestr__variant__nomi", "tur")
    )


def oqituvchi_shakl1_malumoti(
    profil: OqituvchiProfil, akademik_yil: int
) -> tuple[list[Yuklama], list[dict[str, object]], dict[str, int]]:
    """Return raw workloads, 1-shakl rows, and per-type totals for one teacher."""
    yuklamalar = oqituvchi_yuklamalari(profil, akademik_yil)
    satrlar, tur_jami = shakl1_satrlarini_yigish(yuklamalar)
    return yuklamalar, satrlar, tur_jami


__all__ = [
    "SoatTuri",
    "oqituvchi_shakl1_malumoti",
    "oqituvchi_yuklamalari",
    "shakl1_guruh_matni",
    "shakl1_satrlarini_yigish",
]
