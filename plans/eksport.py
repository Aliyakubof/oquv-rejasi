"""Excel (.xlsx) export of teacher coverage and detailed workload rows."""

import re
from io import BytesIO

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from accounts.models import Department
from plans.dashboard import KafedraQamrov, kafedra_qamrovi
from plans.models import OquvReja, Yuklama
from plans.services import YuklamaHolati, ofis_taqsimoti, yuklama_kamomadi

_XML_TAQIQ = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_SARLAVHA_SHRIFT = Font(bold=True, size=12)
_USTUN_SHRIFT = Font(bold=True, size=10, color="1E293B")
_USTUN_FON = PatternFill("solid", fgColor="F1F5F9")
_CHEGARA_CHIZIQ = Side(style="thin", color="CBD5E1")
_CHEGARA = Border(
    left=_CHEGARA_CHIZIQ,
    right=_CHEGARA_CHIZIQ,
    top=_CHEGARA_CHIZIQ,
    bottom=_CHEGARA_CHIZIQ,
)

_UMUMIY_USTUNLAR = [
    "№",
    "F.I.Sh",
    "Telefon",
    "Kafedra",
    "Lavozim",
    "Minimal soat",
    "Yuklama soat",
    "Kamomad",
    "Qoplanish (%)",
    "Holat",
]

_TAFSILOT_USTUNLAR = [
    "№",
    "O'qituvchi",
    "Kafedra",
    "Fan kodi",
    "Fan nomi",
    "Yo'nalish",
    "Semestr",
    "Mashg'ulot turi",
    "Guruh / Talabalar",
    "Soat",
]


def _xavfsiz_matn(qiymat: object) -> str:
    """Strip XML-illegal control characters and neutralize Excel formulas."""
    matn = _XML_TAQIQ.sub("", "" if qiymat is None else str(qiymat))
    if matn[:1] in ("\t", "\r") or matn.lstrip()[:1] in ("=", "+", "-", "@"):
        return "'" + matn
    return matn


def oqituvchilar_excel(
    akademik_yil: int, *, kafedra: Department | None = None
) -> BytesIO:
    """Build a two-sheet .xlsx workbook: teacher summary + detailed Yuklama rows."""
    holatlar = yuklama_kamomadi(akademik_yil, kafedra=kafedra)
    kitob = openpyxl.Workbook()

    umumiy_varaq = kitob.active
    umumiy_varaq.title = "O'qituvchilar"
    _umumiy_varaqni_toldir(umumiy_varaq, holatlar, akademik_yil, kafedra)

    tafsilot_varaq = kitob.create_sheet("Yuklama tafsiloti")
    _tafsilot_varaqni_toldir(tafsilot_varaq, akademik_yil, kafedra)

    buffer = BytesIO()
    kitob.save(buffer)
    buffer.seek(0)
    return buffer


def _umumiy_qator(idx: int, h: YuklamaHolati) -> list[str | int]:
    foiz = round(h.jami_soat * 100 / h.min_soat) if h.min_soat else 0
    holat_matni = f"Kamomad {h.kamomad} soat" if h.kamomad else "To'ldi"
    return [
        idx,
        _xavfsiz_matn(h.oqituvchi),
        _xavfsiz_matn(h.oqituvchi.foydalanuvchi.telefon),
        _xavfsiz_matn(h.oqituvchi.kafedra.nomi),
        _xavfsiz_matn(h.oqituvchi.turi.nomi),
        h.min_soat,
        h.jami_soat,
        h.kamomad,
        foiz,
        holat_matni,
    ]


def _umumiy_varaqni_toldir(
    ws: Worksheet,
    holatlar: list[YuklamaHolati],
    akademik_yil: int,
    kafedra: Department | None,
) -> None:
    nom = f"{kafedra.nomi} kafedrasi" if kafedra else "Barcha kafedralar"
    sarlavha = f"{nom} — {akademik_yil}/{akademik_yil + 1} o'quv yili yuklama hisoboti"
    ws.append([_xavfsiz_matn(sarlavha)])
    ws["A1"].font = _SARLAVHA_SHRIFT
    ws.append([])

    ws.append(_UMUMIY_USTUNLAR)
    _ustun_qatorini_bezash(ws, 3, len(_UMUMIY_USTUNLAR))
    for idx, h in enumerate(holatlar, start=1):
        ws.append(_umumiy_qator(idx, h))
    _kataklarni_chegaralash(ws, 4, 3 + len(holatlar), len(_UMUMIY_USTUNLAR))
    _kengliklarni_moslash(ws, bosh_qator=3)


def _tafsilot_yuklamalari(
    akademik_yil: int, kafedra: Department | None
) -> list[Yuklama]:
    qs = (
        Yuklama.objects.akademik_yilda(akademik_yil)
        .select_related(
            "oqituvchi__foydalanuvchi",
            "oqituvchi__kafedra",
            "fan_semestr__variant__fan__reja",
            "guruh",
        )
        .order_by(
            "oqituvchi__kafedra__nomi",
            "oqituvchi__foydalanuvchi__last_name",
            "fan_semestr__semestr",
            "tur",
        )
    )
    if kafedra is not None:
        qs = qs.filter(oqituvchi__kafedra=kafedra)
    return list(qs)


def _tafsilot_qator(idx: int, y: Yuklama) -> list[str | int]:
    guruh_matni = (
        y.guruh.nomi
        if y.guruh
        else (f"{y.talabalar_soni} talaba" if y.talabalar_soni else "Butun oqim")
    )
    return [
        idx,
        _xavfsiz_matn(y.oqituvchi),
        _xavfsiz_matn(y.oqituvchi.kafedra.nomi),
        _xavfsiz_matn(y.fan_semestr.variant.kodi or ""),
        _xavfsiz_matn(y.fan_semestr.variant.nomi),
        _xavfsiz_matn(y.fan_semestr.variant.fan.reja.yonalish_kodi),
        f"{y.fan_semestr.semestr}-semestr",
        _xavfsiz_matn(y.get_tur_display()),
        _xavfsiz_matn(guruh_matni),
        y.soat,
    ]


def _tafsilot_varaqni_toldir(
    ws: Worksheet, akademik_yil: int, kafedra: Department | None
) -> None:
    ws.append(_TAFSILOT_USTUNLAR)
    _ustun_qatorini_bezash(ws, 1, len(_TAFSILOT_USTUNLAR))
    yuklamalar = _tafsilot_yuklamalari(akademik_yil, kafedra)
    for idx, y in enumerate(yuklamalar, start=1):
        ws.append(_tafsilot_qator(idx, y))
    _kataklarni_chegaralash(ws, 2, 1 + len(yuklamalar), len(_TAFSILOT_USTUNLAR))
    _kengliklarni_moslash(ws, bosh_qator=1)


def _ustun_qatorini_bezash(ws: Worksheet, qator: int, ustun_soni: int) -> None:
    for col in range(1, ustun_soni + 1):
        katak = ws.cell(row=qator, column=col)
        katak.font = _USTUN_SHRIFT
        katak.fill = _USTUN_FON
        katak.border = _CHEGARA
        katak.alignment = Alignment(vertical="center")


def _kataklarni_chegaralash(
    ws: Worksheet, bosh_qator: int, oxirgi_qator: int, ustun_soni: int
) -> None:
    for row in range(bosh_qator, oxirgi_qator + 1):
        for col in range(1, ustun_soni + 1):
            ws.cell(row=row, column=col).border = _CHEGARA


def _kengliklarni_moslash(ws: Worksheet, *, bosh_qator: int = 1) -> None:
    for col_cells in ws.columns:
        harf = get_column_letter(col_cells[0].column)
        uzunlik = max(
            (len(str(c.value or "")) for c in col_cells if c.row >= bosh_qator),
            default=10,
        )
        ws.column_dimensions[harf].width = min(max(uzunlik + 4, 10), 42)


_SVOD_KAFEDRA_USTUNLAR = [
    "№",
    "Kafedra",
    "Fakultet",
    "O'qituvchilar",
    "Biriktirilgan soat",
    "Taqsimlangan soat",
    "Qoldiq soat",
    "Qoplanish (%)",
    "Tasdiq holati",
]
_SVOD_REJA_USTUNLAR = [
    "№",
    "Yo'nalish kodi",
    "Yo'nalish nomi",
    "Qabul yili",
    "Ta'lim shakli",
    "Guruhlar",
    "Talabalar",
    "Jami soat",
    "Taqsimlangan",
    "Qoldiq",
    "Qoplanish (%)",
]


def _svod_kafedra_varaqi(
    ws: Worksheet, qamrovlar: list[KafedraQamrov], akademik_yil: int
) -> None:
    sarlavha = f"Kafedralar kesimida svod yuklama ({akademik_yil}/{akademik_yil + 1})"
    ws.append([_xavfsiz_matn(sarlavha)])
    ws["A1"].font = _SARLAVHA_SHRIFT
    ws.append([])
    ws.append(_SVOD_KAFEDRA_USTUNLAR)
    _ustun_qatorini_bezash(ws, 3, len(_SVOD_KAFEDRA_USTUNLAR))
    for idx, q in enumerate(qamrovlar, start=1):
        qoldiq = max(0, q.biriktirilgan_soat - q.taqsimlangan_soat)
        foiz = (
            round(q.taqsimlangan_soat * 100 / q.biriktirilgan_soat)
            if q.biriktirilgan_soat
            else 0
        )
        holat = q.tasdiq.get_holat_display() if q.tasdiq else "Yuborilmagan"
        ws.append(
            [
                idx,
                _xavfsiz_matn(q.kafedra.nomi),
                _xavfsiz_matn(q.kafedra.fakultet or "—"),
                q.oqituvchilar_soni,
                q.biriktirilgan_soat,
                q.taqsimlangan_soat,
                qoldiq,
                foiz,
                holat,
            ]
        )
    jami_talab = sum(q.biriktirilgan_soat for q in qamrovlar)
    jami_taqsim = sum(q.taqsimlangan_soat for q in qamrovlar)
    jami_foiz = round(jami_taqsim * 100 / jami_talab) if jami_talab else 0
    ws.append(
        [
            "",
            "JAMI",
            "",
            sum(q.oqituvchilar_soni for q in qamrovlar),
            jami_talab,
            jami_taqsim,
            max(0, jami_talab - jami_taqsim),
            jami_foiz,
            "",
        ]
    )
    _kataklarni_chegaralash(ws, 4, 4 + len(qamrovlar), len(_SVOD_KAFEDRA_USTUNLAR))
    _kengliklarni_moslash(ws, bosh_qator=3)


def _svod_yonalish_varaqi(ws: Worksheet, akademik_yil: int) -> None:
    sarlavha = (
        "O'quv rejalar va yo'nalishlar kesimida svod "
        f"({akademik_yil}/{akademik_yil + 1})"
    )
    ws.append([_xavfsiz_matn(sarlavha)])
    ws["A1"].font = _SARLAVHA_SHRIFT
    ws.append([])
    ws.append(_SVOD_REJA_USTUNLAR)
    _ustun_qatorini_bezash(ws, 3, len(_SVOD_REJA_USTUNLAR))
    talab_yig: dict[int, int] = {}
    taqsim_yig: dict[int, int] = {}
    rejalar_map: dict[int, OquvReja] = {}
    for satr in ofis_taqsimoti(akademik_yil):
        reja = satr.fan_semestr.variant.fan.reja
        rejalar_map[reja.pk] = reja
        talab_yig[reja.pk] = talab_yig.get(reja.pk, 0) + (satr.talab_soat or 0)
        taqsim_yig[reja.pk] = taqsim_yig.get(reja.pk, 0) + satr.taqsimlangan_soat
    rejalar = sorted(
        rejalar_map.values(),
        key=lambda r: (r.yonalish_kodi, r.boshlanish_yili, r.talim_shakli),
    )
    for idx, r in enumerate(rejalar, start=1):
        talab = talab_yig.get(r.pk, 0)
        taqsim = taqsim_yig.get(r.pk, 0)
        foiz = round(taqsim * 100 / talab) if talab else 0
        ws.append(
            [
                idx,
                _xavfsiz_matn(r.yonalish_kodi),
                _xavfsiz_matn(r.yonalish_nomi or "—"),
                r.boshlanish_yili,
                _xavfsiz_matn(r.talim_shakli or "—"),
                r.guruhlar_soni or 0,
                r.talabalar_soni or 0,
                talab,
                taqsim,
                max(0, talab - taqsim),
                foiz,
            ]
        )
    _kataklarni_chegaralash(ws, 4, 3 + len(rejalar), len(_SVOD_REJA_USTUNLAR))
    _kengliklarni_moslash(ws, bosh_qator=3)


def svod_excel(akademik_yil: int) -> BytesIO:
    """Build university-wide 3-sheet consolidated workload .xlsx report."""
    kitob = openpyxl.Workbook()
    taqsimot = ofis_taqsimoti(akademik_yil)
    qamrovlar = kafedra_qamrovi(akademik_yil, taqsimot=taqsimot)
    holatlar = yuklama_kamomadi(akademik_yil)

    ws_kaf = kitob.active
    ws_kaf.title = "Kafedralar kesimi"
    _svod_kafedra_varaqi(ws_kaf, qamrovlar, akademik_yil)

    ws_oqit = kitob.create_sheet("O'qituvchilar kesimi")
    _umumiy_varaqni_toldir(ws_oqit, holatlar, akademik_yil, None)

    ws_yon = kitob.create_sheet("Yo'nalishlar kesimi")
    _svod_yonalish_varaqi(ws_yon, akademik_yil)

    buffer = BytesIO()
    kitob.save(buffer)
    buffer.seek(0)
    return buffer
