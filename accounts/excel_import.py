"""O'qituvchilar va yo'nalishlarni Excel orqali yuklash hamda shablon yaratish."""

import re
from dataclasses import dataclass
from io import BytesIO
from xml.etree import ElementTree as ET
from zipfile import BadZipFile

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from lxml.etree import XMLSyntaxError
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
from accounts.phone import telefonni_normallashtir, validate_uzbek_phone
from accounts.services import vaqtinchalik_parol_tasodifiy
from plans.models import TalimYonalishi
from plans.services import keshni_tozala
from plans.uploads import zip_faylini_tekshir

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
    if isinstance(qiymat, str) and (
        qiymat[:1] in ("\t", "\r") or qiymat.lstrip().startswith(_FORMULA_BOSH)
    ):
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
    toza = re.sub(r"[^\d+]", "", telefonni_normallashtir(matn))
    if re.fullmatch(r"998\d{9}", toza):
        toza = f"+{toza}"
    elif re.fullmatch(r"\d{9}", toza):
        toza = f"+998{toza}"
    validate_uzbek_phone(toza)
    return toza


_EXCEL_XATOLARI = (
    BadZipFile,
    ET.ParseError,
    XMLSyntaxError,
    EOFError,
    InvalidFileException,
    OSError,
    KeyError,
    ValueError,
)


def _excel_qatorlarini_oqi(wb) -> list[list[object]]:
    qatorlar: list[list[object]] = []
    ws = wb.active
    if ws is None:
        raise ValidationError("Excel faylida faol varaq topilmadi.")
    for indeks, qator in enumerate(ws.iter_rows(values_only=True)):
        if indeks > MAX_IMPORT_QATOR:
            raise ValidationError(
                f"Bir yuklashda ko'pi bilan {MAX_IMPORT_QATOR} "
                "ta qator import qilinadi."
            )
        qatorlar.append(list(qator))
    return qatorlar


def _excel_yuklash(fayl: UploadedFile) -> list[list[object]]:
    zip_faylini_tekshir(
        fayl,
        kutilgan_kengaytma=".xlsx",
        max_hajm=MAX_EXCEL_HAJM,
        zarur_fayl="xl/workbook.xml",
    )
    fayl.seek(0)
    try:
        wb = load_workbook(fayl, read_only=True, data_only=True)
    except _EXCEL_XATOLARI as exc:
        raise ValidationError(
            "Excel faylini o'qib bo'lmadi. Namunadagi .xlsx fayldan foydalaning."
        ) from exc
    try:
        return _excel_qatorlarini_oqi(wb)
    except _EXCEL_XATOLARI as exc:
        raise ValidationError(
            "Excel faylini o'qib bo'lmadi. Namunadagi .xlsx fayldan foydalaning."
        ) from exc
    finally:
        wb.close()


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
    """Mavjud kafedralar va lavozimlar bilan .xlsx shablon tayyorlaydi."""
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
            _xavfsiz(kaf.nomi if kaf else "Axborot texnologiyalari"),
            _xavfsiz(tur.nomi if tur else "Dotsent"),
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
                _xavfsiz(kaflar[i]) if i < len(kaflar) else "",
                _xavfsiz(turlar[i]) if i < len(turlar) else "",
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
) -> list[_TayyorOqituvchi]:
    kaf_map = {_norm(k.nomi): k for k in Department.objects.all()}
    tur_map = {_norm(t.nomi): t for t in OqituvchiTuri.objects.all()}
    korilgan: set[str] = set()
    nomzodlar: list[_TayyorOqituvchi] = []
    xatolar: list[str] = []
    for idx, qator in enumerate(qatorlar[1:], start=2):
        yozuv, _, xato = _oqituvchi_qatorini_oqish(
            idx, qator, kaf_map, tur_map, korilgan, set()
        )
        if xato:
            xatolar.append(xato)
        elif yozuv is not None:
            nomzodlar.append(yozuv)
    if xatolar:
        raise ValidationError(xatolar[:15])
    return nomzodlar


def _yangi_oqituvchi_obyektlari(
    tayyor: list[_TayyorOqituvchi], parollar: list[str]
) -> list[Foydalanuvchi]:
    yangi_userlar: list[Foydalanuvchi] = []
    for item, parol in zip(tayyor, parollar):
        user = Foydalanuvchi(
            telefon=item.telefon,
            first_name=item.first_name[:150],
            last_name=item.last_name[:150],
            rol=Rol.TEACHER,
            parol_ozgartirish_kerak=True,
        )
        user.set_password(parol)
        yangi_userlar.append(user)
    return yangi_userlar


def oqituvchilar_excel_import(fayl: UploadedFile) -> OqituvchiImportNatija:
    """O'qituvchilarni tekshirib, bir martalik parollar bilan bazaga yozadi."""
    qatorlar = _excel_yuklash(fayl)
    if len(qatorlar) < 2:
        raise ValidationError("Excel faylida ma'lumot qatorlari topilmadi.")
    nomzodlar = _oqituvchilarni_yigish(qatorlar)
    if not nomzodlar:
        return OqituvchiImportNatija(yaratilganlar=[], otkazildi_mavjud=[])

    telefonlar = [item.telefon for item in nomzodlar]
    with transaction.atomic():
        mavjud_tel = set(
            Foydalanuvchi.objects.select_for_update()
            .filter(telefon__in=telefonlar)
            .order_by("pk")
            .values_list("telefon", flat=True)
        )
        tayyor = [item for item in nomzodlar if item.telefon not in mavjud_tel]
        otkazildi = [item.telefon for item in nomzodlar if item.telefon in mavjud_tel]
        if not tayyor:
            return OqituvchiImportNatija(yaratilganlar=[], otkazildi_mavjud=otkazildi)

        parollar = [vaqtinchalik_parol_tasodifiy() for _ in tayyor]
        yangi_userlar = _yangi_oqituvchi_obyektlari(tayyor, parollar)
        saqlangan = Foydalanuvchi.objects.bulk_create(yangi_userlar, batch_size=200)
        OqituvchiProfil.objects.bulk_create(
            [
                OqituvchiProfil(
                    foydalanuvchi=user, kafedra=item.kafedra, turi=item.turi
                )
                for user, item in zip(saqlangan, tayyor)
            ],
            batch_size=200,
        )
        keshni_tozala()
    yaratilganlar = [
        {
            "ism": f"{user.last_name} {user.first_name}",
            "telefon": user.telefon,
            "kafedra": item.kafedra.nomi,
            "lavozim": item.turi.nomi,
            "parol": parol,
        }
        for user, item, parol in zip(saqlangan, tayyor, parollar)
    ]
    return OqituvchiImportNatija(
        yaratilganlar=yaratilganlar, otkazildi_mavjud=otkazildi
    )


def oqituvchi_import_natija_excel(yaratilganlar: list[dict[str, str]]) -> BytesIO:
    """Import paytida yaratilgan bir martalik parollarni Excelga eksport qiladi."""
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
    """Tasdiqlangan yo'nalishlar klassifikatori uchun .xlsx shablon yaratadi."""
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


def _yonalish_qatorini_tekshir(
    idx: int, qator: list[object], korilgan_kod: set[str]
) -> tuple[dict[str, str] | None, str | None]:
    qiymatlar = [_matn(qator[i]) if i < len(qator) else "" for i in range(6)]
    if not any(qiymatlar):
        return None, None
    if not all(qiymatlar):
        return None, f"{idx}-qator: barcha 6 ustun to'ldirilishi shart."
    kodi, nomi, bs_kod, bs_nom, ts_kod, ts_nom = qiymatlar
    chegaralar = (
        (kodi, 20, "yo'nalish kodi"),
        (nomi, 255, "yo'nalish nomi"),
        (bs_kod, 10, "bilim sohasi kodi"),
        (bs_nom, 255, "bilim sohasi nomi"),
        (ts_kod, 10, "ta'lim sohasi kodi"),
        (ts_nom, 255, "ta'lim sohasi nomi"),
    )
    for qiymat, chegara, yorliq in chegaralar:
        if len(qiymat) > chegara:
            return None, f"{idx}-qator: {yorliq} {chegara} belgidan oshmasligi kerak."
    if kodi in korilgan_kod:
        return None, f"{idx}-qator: takroriy yo'nalish kodi ({kodi})."
    korilgan_kod.add(kodi)
    return {
        "kodi": kodi,
        "nomi": nomi,
        "bilim_sohasi_kodi": bs_kod,
        "bilim_sohasi_nomi": bs_nom,
        "talim_sohasi_kodi": ts_kod,
        "talim_sohasi_nomi": ts_nom,
    }, None


def _yonalish_qatorlarini_yigish(
    qatorlar: list[list[object]],
) -> list[dict[str, str]]:
    yozuvlar: list[dict[str, str]] = []
    xatolar: list[str] = []
    korilgan_kod: set[str] = set()
    for idx, qator in enumerate(qatorlar[1:], start=2):
        yozuv, xato = _yonalish_qatorini_tekshir(idx, qator, korilgan_kod)
        if xato:
            xatolar.append(xato)
        elif yozuv is not None:
            yozuvlar.append(yozuv)
    if xatolar:
        raise ValidationError(xatolar[:15])
    if not yozuvlar:
        raise ValidationError("Import qilinadigan yo'nalishlar topilmadi.")
    return yozuvlar


def yonalishlar_excel_import(fayl: UploadedFile) -> tuple[int, int]:
    """Yo'nalishlarni .xlsx fayldan tekshirib, ommaviy yangilaydi yoki qo'shadi."""
    qatorlar = _excel_yuklash(fayl)
    if len(qatorlar) < 2:
        raise ValidationError("Excel faylida ma'lumot qatorlari topilmadi.")
    yozuvlar = _yonalish_qatorlarini_yigish(qatorlar)
    kodlar = [item["kodi"] for item in yozuvlar]
    yangilash_maydonlari = (
        "nomi",
        "bilim_sohasi_kodi",
        "bilim_sohasi_nomi",
        "talim_sohasi_kodi",
        "talim_sohasi_nomi",
    )
    with transaction.atomic():
        mavjud = {
            obj.kodi: obj
            for obj in TalimYonalishi.objects.select_for_update()
            .filter(kodi__in=kodlar)
            .order_by("pk")
        }
        yangi: list[TalimYonalishi] = []
        ozgargan: list[TalimYonalishi] = []
        for item in yozuvlar:
            obj = mavjud.get(item["kodi"])
            if obj is None:
                yangi.append(TalimYonalishi(**item))
            else:
                for maydon in yangilash_maydonlari:
                    setattr(obj, maydon, item[maydon])
                ozgargan.append(obj)
        if yangi:
            TalimYonalishi.objects.bulk_create(yangi, batch_size=200)
        if ozgargan:
            TalimYonalishi.objects.bulk_update(
                ozgargan, list(yangilash_maydonlari), batch_size=200
            )
        keshni_tozala()
    return len(yangi), len(ozgargan)
