"""Bulk Excel import and template generation for teachers and major classifiers."""

import re
from dataclasses import dataclass
from io import BytesIO

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.utils.exceptions import InvalidFileException
from openpyxl.worksheet.worksheet import Worksheet

from accounts.models import (
    Department,
    Foydalanuvchi,
    OqituvchiProfil,
    OqituvchiTuri,
    Rol,
)
from accounts.phone import normalize_phone, validate_uzbek_phone
from accounts.services import vaqtinchalik_parol_tasodifiy
from plans.models import TalimYonalishi
from plans.services import keshni_tozala

MAX_EXCEL_HAJM = 10 * 1024 * 1024
MAX_IMPORT_QATOR = 1000
_FORMULA_BOSH = ("=", "+", "-", "@", "\t", "\r")

_USTUN_SHRIFT = Font(bold=True, size=10, color="1E293B")
_USTUN_FON = PatternFill("solid", fgColor="E2E8F0")
_CHEGA = Side(border_style="thin", color="CBD5E1")
_CHEGARA = Border(left=_CHEGA, right=_CHEGA, top=_CHEGA, bottom=_CHEGA)

_OQITUVCHI_USTUNLAR = [
    "Familiya",
    "Ism",
    "Telefon (+998...)",
    "Kafedra nomi",
    "Lavozim",
]
_YONALISH_USTUNLAR = [
    "Yo'nalish kodi",
    "Yo'nalish nomi",
    "Bilim sohasi kodi",
    "Bilim sohasi nomi",
    "Ta'lim sohasi kodi",
    "Ta'lim sohasi nomi",
]


@dataclass(frozen=True)
class OqituvchiImportNatija:
    yaratilganlar: list[dict[str, str]]
    otkazildi_mavjud: list[str]


@dataclass(frozen=True)
class _TayyorOqituvchi:
    last_name: str
    first_name: str
    telefon: str
    kafedra: Department
    turi: OqituvchiTuri


def _xavfsiz(qiymat: object) -> object:
    if isinstance(qiymat, str) and qiymat.startswith(_FORMULA_BOSH):
        return f"'{qiymat}"
    return qiymat


def _matn(katak: object) -> str:
    if katak is None:
        return ""
    if isinstance(katak, float) and katak.is_integer():
        return str(int(katak))
    return " ".join(str(katak).strip().split())


def _norm(matn: str) -> str:
    return " ".join(matn.lower().replace("'", "").replace("’", "").split())


def _telefonni_normallashtir(xom: object) -> str:
    matn = _matn(xom)
    if not matn:
        return ""
    toza = re.sub(r"[^\d+]", "", normalize_phone(matn))
    if re.fullmatch(r"998\d{9}", toza):
        toza = f"+{toza}"
    elif re.fullmatch(r"\d{9}", toza):
        toza = f"+998{toza}"
    validate_uzbek_phone(toza)
    return toza


def _excel_yuklash(fayl: UploadedFile) -> list[list[object]]:
    nom = (getattr(fayl, "name", "") or "").lower()
    if not nom.endswith(".xlsx"):
        raise ValidationError("Faqat .xlsx formatidagi Excel fayllar qabul qilinadi.")
    if getattr(fayl, "size", 0) > MAX_EXCEL_HAJM:
        raise ValidationError("Fayl hajmi 10 MB dan oshmasligi kerak.")
    fayl.seek(0)
    try:
        wb = load_workbook(fayl, read_only=True, data_only=True)
    except (InvalidFileException, OSError, KeyError, ValueError) as exc:
        raise ValidationError(
            "Excel faylini o'qib bo'lmadi. Namunadagi .xlsx fayldan foydalaning."
        ) from exc
    try:
        ws = wb.active
        qatorlar = [list(r) for r in ws.iter_rows(values_only=True)]
    finally:
        wb.close()
    if len(qatorlar) - 1 > MAX_IMPORT_QATOR:
        raise ValidationError(
            f"Bir yuklashda ko'pi bilan {MAX_IMPORT_QATOR} ta qator import qilinadi."
        )
    return qatorlar


def _jadvalni_bezash(ws: Worksheet, ustun_soni: int, qator_soni: int) -> None:
    for col in range(1, ustun_soni + 1):
        c = ws.cell(row=1, column=col)
        c.font = _USTUN_SHRIFT
        c.fill = _USTUN_FON
        c.border = _CHEGARA
        c.alignment = Alignment(vertical="center")
    for row in range(2, qator_soni + 1):
        for col in range(1, ustun_soni + 1):
            ws.cell(row=row, column=col).border = _CHEGARA
    for cells in ws.columns:
        harf = get_column_letter(cells[0].column)
        max_len = max((len(str(c.value or "")) for c in cells), default=12)
        ws.column_dimensions[harf].width = min(max(max_len + 4, 14), 42)


def _varaqqa_bufferga(wb: Workbook) -> BytesIO:
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def oqituvchilar_namuna_excel() -> BytesIO:
    """Build a downloadable .xlsx template with reference departments & positions."""
    wb = Workbook()
    ws = wb.active
    ws.title = "O'qituvchilar"
    ws.append(_OQITUVCHI_USTUNLAR)
    kaf = Department.objects.order_by("nomi").first()
    tur = OqituvchiTuri.objects.order_by("nomi").first()
    ws.append(
        [
            "Aliyev",
            "Vali",
            "+998901234567",
            kaf.nomi if kaf else "Axborot texnologiyalari",
            tur.nomi if tur else "Dotsent",
        ]
    )
    _jadvalni_bezash(ws, len(_OQITUVCHI_USTUNLAR), 2)

    qollanma = wb.create_sheet("Ma'lumotnoma")
    qollanma.append(["Mavjud kafedralar", "Mavjud lavozimlar"])
    kaflar = list(Department.objects.order_by("nomi").values_list("nomi", flat=True))
    turlar = list(OqituvchiTuri.objects.order_by("nomi").values_list("nomi", flat=True))
    jami = max(len(kaflar), len(turlar), 1)
    for i in range(jami):
        qollanma.append(
            [
                kaflar[i] if i < len(kaflar) else "",
                turlar[i] if i < len(turlar) else "",
            ]
        )
    _jadvalni_bezash(qollanma, 2, jami + 1)
    return _varaqqa_bufferga(wb)


def _oqituvchi_qatorini_oqish(
    qator_raqami: int,
    qator: list[object],
    kafedra_map: dict[str, Department],
    turi_map: dict[str, OqituvchiTuri],
    korilgan_telefon: set[str],
    mavjud_telefon: set[str],
) -> tuple[_TayyorOqituvchi | None, str | None, str | None]:
    qiymatlar = [_matn(qator[i]) if i < len(qator) else "" for i in range(5)]
    if not any(qiymatlar):
        return None, None, None
    familiya, ism, xom_tel, kaf_nomi, lav_nomi = qiymatlar
    if not all(qiymatlar):
        return None, None, f"{qator_raqami}-qator: barcha 5 ustun to'ldirilishi shart."
    try:
        telefon = _telefonni_normallashtir(xom_tel)
    except ValidationError as exc:
        return None, None, f"{qator_raqami}-qator: {' '.join(exc.messages)}"
    if telefon in korilgan_telefon:
        return None, None, f"{qator_raqami}-qator: takroriy raqam ({telefon})."
    korilgan_telefon.add(telefon)
    if telefon in mavjud_telefon:
        return None, telefon, None
    kafedra = kafedra_map.get(_norm(kaf_nomi))
    if kafedra is None:
        return None, None, f"{qator_raqami}-qator: kafedra topilmadi ('{kaf_nomi}')."
    turi = turi_map.get(_norm(lav_nomi))
    if turi is None:
        return None, None, f"{qator_raqami}-qator: lavozim topilmadi ('{lav_nomi}')."
    return (
        _TayyorOqituvchi(
            last_name=familiya,
            first_name=ism,
            telefon=telefon,
            kafedra=kafedra,
            turi=turi,
        ),
        None,
        None,
    )


def _oqituvchilarni_yigish(
    qatorlar: list[list[object]],
) -> tuple[list[_TayyorOqituvchi], list[str]]:
    kaf_map = {_norm(k.nomi): k for k in Department.objects.all()}
    tur_map = {_norm(t.nomi): t for t in OqituvchiTuri.objects.all()}
    mavjud_tel = set(Foydalanuvchi.objects.values_list("telefon", flat=True))
    korilgan: set[str] = set()
    tayyor: list[_TayyorOqituvchi] = []
    otkazildi: list[str] = []
    xatolar: list[str] = []
    for idx, qator in enumerate(qatorlar[1:], start=2):
        yozuv, mavjud, xato = _oqituvchi_qatorini_oqish(
            idx, qator, kaf_map, tur_map, korilgan, mavjud_tel
        )
        if xato:
            xatolar.append(xato)
        elif mavjud:
            otkazildi.append(mavjud)
        elif yozuv is not None:
            tayyor.append(yozuv)
    if xatolar:
        raise ValidationError(xatolar[:15])
    return tayyor, otkazildi


def oqituvchilar_excel_import(fayl: UploadedFile) -> OqituvchiImportNatija:
    """Validate and atomically import teachers with one-time temporary passwords."""
    qatorlar = _excel_yuklash(fayl)
    if len(qatorlar) < 2:
        raise ValidationError("Excel faylida ma'lumot qatorlari topilmadi.")
    tayyor, otkazildi = _oqituvchilarni_yigish(qatorlar)
    if not tayyor:
        return OqituvchiImportNatija(yaratilganlar=[], otkazildi_mavjud=otkazildi)

    yaratilganlar: list[dict[str, str]] = []
    with transaction.atomic():
        for item in tayyor:
            parol = vaqtinchalik_parol_tasodifiy()
            user = Foydalanuvchi.objects.create_user(
                telefon=item.telefon,
                password=parol,
                first_name=item.first_name,
                last_name=item.last_name,
                rol=Rol.TEACHER,
                parol_ozgartirish_kerak=True,
            )
            OqituvchiProfil.objects.create(
                foydalanuvchi=user, kafedra=item.kafedra, turi=item.turi
            )
            yaratilganlar.append(
                {
                    "ism": f"{user.last_name} {user.first_name}",
                    "telefon": user.telefon,
                    "kafedra": item.kafedra.nomi,
                    "lavozim": item.turi.nomi,
                    "parol": parol,
                }
            )
        keshni_tozala()
    return OqituvchiImportNatija(
        yaratilganlar=yaratilganlar, otkazildi_mavjud=otkazildi
    )


def oqituvchi_import_natija_excel(yaratilganlar: list[dict[str, str]]) -> BytesIO:
    """Export one-time initial credentials generated during teacher import."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Vaqtinchalik parollar"
    ustunlar = ["№", "F.I.Sh.", "Telefon", "Kafedra", "Lavozim", "Vaqtinchalik parol"]
    ws.append(ustunlar)
    for idx, q in enumerate(yaratilganlar, start=1):
        ws.append(
            [
                idx,
                _xavfsiz(q.get("ism", "")),
                _xavfsiz(q.get("telefon", "")),
                _xavfsiz(q.get("kafedra", "")),
                _xavfsiz(q.get("lavozim", "")),
                _xavfsiz(q.get("parol", "")),
            ]
        )
    _jadvalni_bezash(ws, len(ustunlar), len(yaratilganlar) + 1)
    return _varaqqa_bufferga(wb)


def yonalishlar_namuna_excel() -> BytesIO:
    """Build a downloadable .xlsx template for official classifier rows."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Yo'nalishlar"
    ws.append(_YONALISH_USTUNLAR)
    ws.append(
        [
            "60610100",
            "Kompyuter ilmlari va dasturlash texnologiyalari",
            "600000",
            "Axborot-kommunikatsiya texnologiyalari",
            "606100",
            "Axborot va kommunikatsiya texnologiyalari",
        ]
    )
    _jadvalni_bezash(ws, len(_YONALISH_USTUNLAR), 2)
    return _varaqqa_bufferga(wb)


def _yonalish_qatorlarini_yigish(
    qatorlar: list[list[object]],
) -> list[dict[str, str]]:
    yozuvlar: list[dict[str, str]] = []
    xatolar: list[str] = []
    korilgan_kod: set[str] = set()
    for idx, qator in enumerate(qatorlar[1:], start=2):
        qiymatlar = [_matn(qator[i]) if i < len(qator) else "" for i in range(6)]
        if not any(qiymatlar):
            continue
        kodi, nomi, bs_kod, bs_nom, ts_kod, ts_nom = qiymatlar
        if not all(qiymatlar):
            xatolar.append(f"{idx}-qator: barcha 6 ustun to'ldirilishi shart.")
            continue
        if kodi in korilgan_kod:
            xatolar.append(f"{idx}-qator: takroriy yo'nalish kodi ({kodi}).")
            continue
        korilgan_kod.add(kodi)
        yozuvlar.append(
            {
                "kodi": kodi[:20],
                "nomi": nomi[:255],
                "bilim_sohasi_kodi": bs_kod[:10],
                "bilim_sohasi_nomi": bs_nom[:255],
                "talim_sohasi_kodi": ts_kod[:10],
                "talim_sohasi_nomi": ts_nom[:255],
            }
        )
    if xatolar:
        raise ValidationError(xatolar[:15])
    if not yozuvlar:
        raise ValidationError("Import qilinadigan yo'nalishlar topilmadi.")
    return yozuvlar


def yonalishlar_excel_import(fayl: UploadedFile) -> tuple[int, int]:
    """Validate and bulk upsert TalimYonalishi rows from an .xlsx file."""
    qatorlar = _excel_yuklash(fayl)
    if len(qatorlar) < 2:
        raise ValidationError("Excel faylida ma'lumot qatorlari topilmadi.")
    yozuvlar = _yonalish_qatorlarini_yigish(qatorlar)
    yaratildi = 0
    yangilandi = 0
    with transaction.atomic():
        for item in yozuvlar:
            _, created = TalimYonalishi.objects.update_or_create(
                kodi=item["kodi"], defaults=item
            )
            if created:
                yaratildi += 1
            else:
                yangilandi += 1
        keshni_tozala()
    return yaratildi, yangilandi
