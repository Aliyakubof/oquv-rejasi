"""Brauzerdan yuklangan o'quv reja faylini tekshirib importga uzatish moduli."""

import uuid
import zlib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from lxml.etree import XMLSyntaxError
from openpyxl.utils.exceptions import InvalidFileException

from plans.importer import ImportNatija, ImportXato, excel_reja_oqi, import_reja
from plans.services import guruhlarni_sinxronlash

YUKLASH_KATALOGI = "rejalar"
MAX_FAYL_STEM = 80
MAX_ZIP_CHIQARILGAN_HAJM = 50 * 1024 * 1024  # 50 MB dan oshiq arxivga ruxsat yo'q
MAX_ZIP_FAYL_SONI = 2000


def xavfsiz_fayl_nomi(xom_nom: str | None) -> str:
    """Har xil OS yo'llaridan faqat toza fayl nomini ajratib oladi."""
    if not xom_nom or "\x00" in xom_nom:
        return ""
    return PureWindowsPath(PurePosixPath(xom_nom).name).name


def _arxiv_tarkibini_tekshir(
    fayl: UploadedFile,
    *,
    kengaytma: str,
    max_chiqarilgan_hajm: int,
    max_fayl_soni: int,
    zarur_fayl: str | None,
) -> None:
    try:
        with ZipFile(fayl) as arxiv:
            yozuvlar = arxiv.infolist()
            if len(yozuvlar) > max_fayl_soni:
                raise ValidationError(
                    "Arxivdagi fayllar soni ruxsat etilgan chegaradan oshdi."
                )
            if sum(y.file_size for y in yozuvlar) > max_chiqarilgan_hajm:
                raise ValidationError(
                    "Faylning ochilgan hajmi xavfsiz chegaradan oshdi."
                )
            if zarur_fayl and zarur_fayl not in arxiv.namelist():
                raise ValidationError(f"Fayl yaroqli {kengaytma} hujjati emas.")
            # Zip sarlavhadagi file_size aldanishi mumkin: amalda ochib o'lchaymiz.
            jami_chiqarilgan = 0
            for yozuv in yozuvlar:
                if yozuv.is_dir():
                    continue
                with arxiv.open(yozuv) as ichki:
                    while bolak := ichki.read(65_536):
                        jami_chiqarilgan += len(bolak)
                        if jami_chiqarilgan > max_chiqarilgan_hajm:
                            raise ValidationError(
                                "Faylning ochilgan hajmi xavfsiz chegaradan oshdi."
                            )
    except (BadZipFile, EOFError, OSError, RuntimeError, zlib.error) as xato:
        raise ValidationError(
            f"Fayl {kengaytma} formatida emas yoki buzilgan."
        ) from xato


def zip_faylini_tekshir(
    fayl: UploadedFile,
    *,
    kutilgan_kengaytma: str,
    max_hajm: int,
    max_chiqarilgan_hajm: int = MAX_ZIP_CHIQARILGAN_HAJM,
    max_fayl_soni: int = MAX_ZIP_FAYL_SONI,
    zarur_fayl: str | None = None,
) -> str:
    """Yuklangan OOXML arxivni kengaytma, hajm va zip-bomba chegaralaridan o'tkazadi."""
    toza_nom = xavfsiz_fayl_nomi(getattr(fayl, "name", ""))
    kengaytma = kutilgan_kengaytma.lower()
    if not toza_nom.lower().endswith(kengaytma):
        raise ValidationError(f"Fayl {kengaytma} formatida bo'lishi kerak.")
    hajm = getattr(fayl, "size", None)
    if not hajm:
        raise ValidationError("Bo'sh fayl yuklab bo'lmaydi.")
    if hajm > max_hajm:
        limit_mb = max_hajm // (1024 * 1024)
        raise ValidationError(f"Fayl hajmi {limit_mb} MB dan oshmasligi kerak.")
    fayl.seek(0)
    try:
        _arxiv_tarkibini_tekshir(
            fayl,
            kengaytma=kengaytma,
            max_chiqarilgan_hajm=max_chiqarilgan_hajm,
            max_fayl_soni=max_fayl_soni,
            zarur_fayl=zarur_fayl,
        )
    finally:
        fayl.seek(0)
    return toza_nom


@dataclass(frozen=True)
class YuklashParametrlari:
    talabalar_soni: int
    guruhlar_soni: int
    guruh_prefiksi: str
    boshlanish_yili: int | None
    almashtirish: bool


def fayldan_import_qilish(
    fayl: UploadedFile, parametrlar: YuklashParametrlari
) -> ImportNatija:
    """Faylni vaqtincha saqlab o'qiydi va reja bilan guruhlarni bazaga yozadi."""
    try:
        zip_faylini_tekshir(
            fayl,
            kutilgan_kengaytma=".xlsx",
            max_hajm=10 * 1024 * 1024,
            zarur_fayl="xl/workbook.xml",
        )
    except ValidationError as xato:
        raise ImportXato("; ".join(xato.messages)) from xato

    yol = _faylni_saqlash(fayl)
    try:
        try:
            tahlil = excel_reja_oqi(yol, parametrlar.boshlanish_yili)
        except (
            BadZipFile,
            InvalidFileException,
            ET.ParseError,
            XMLSyntaxError,
            KeyError,
            ValueError,
            EOFError,
            zlib.error,
        ) as xato:
            raise ImportXato("fayl .xlsx formatida emas yoki buzilgan") from xato
        with transaction.atomic():
            natija = import_reja(tahlil, almashtirish=parametrlar.almashtirish)
            reja = natija.reja
            reja.talabalar_soni = parametrlar.talabalar_soni
            reja.guruhlar_soni = parametrlar.guruhlar_soni
            reja.guruh_prefiksi = parametrlar.guruh_prefiksi
            reja.full_clean()
            reja.save(
                update_fields=["talabalar_soni", "guruhlar_soni", "guruh_prefiksi"]
            )
            guruhlarni_sinxronlash(reja)
    finally:
        yol.unlink(missing_ok=True)
    return natija


def _faylni_saqlash(fayl: UploadedFile) -> Path:
    katalog = Path(settings.MEDIA_ROOT) / YUKLASH_KATALOGI
    katalog.mkdir(parents=True, exist_ok=True)
    toza_nom = xavfsiz_fayl_nomi(fayl.name) or "reja.xlsx"
    stem = Path(toza_nom).stem[:MAX_FAYL_STEM] or "reja"
    kengaytma = Path(toza_nom).suffix.lower() or ".xlsx"
    yol = katalog / f"{uuid.uuid4().hex[:8]}_{stem}{kengaytma}"
    with open(yol, "wb") as nishon:
        for parcha in fayl.chunks():
            nishon.write(parcha)
    return yol
