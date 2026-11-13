"""Orchestrate a browser-uploaded reja file into the importer."""

import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from xml.etree import ElementTree as ET
from zipfile import BadZipFile

from django.conf import settings
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from openpyxl.utils.exceptions import InvalidFileException

from plans.importer import ImportNatija, ImportXato, import_reja, parse_xlsx
from plans.services import guruhlarni_sinxronlash

YUKLASH_KATALOGI = "rejalar"
MAX_FAYL_STEM = 80


def xavfsiz_fayl_nomi(xom_nom: str | None) -> str:
    """Return a clean cross-OS basename or empty string if invalid."""
    if not xom_nom or "\x00" in xom_nom:
        return ""
    return PureWindowsPath(PurePosixPath(xom_nom).name).name


@dataclass(frozen=True)
class YuklashParametrlari:
    talabalar_soni: int
    guruhlar_soni: int
    guruh_prefiksi: str
    boshlanish_yili: int | None
    replace: bool


def fayldan_import_qilish(
    fayl: UploadedFile, parametrlar: YuklashParametrlari
) -> ImportNatija:
    """Save the upload temporarily, parse and persist reja + counts atomically."""
    yol = _faylni_saqlash(fayl)
    try:
        parsed = parse_xlsx(yol, parametrlar.boshlanish_yili)
        with transaction.atomic():
            natija = import_reja(parsed, replace=parametrlar.replace)
            reja = natija.reja
            reja.talabalar_soni = parametrlar.talabalar_soni
            reja.guruhlar_soni = parametrlar.guruhlar_soni
            reja.guruh_prefiksi = parametrlar.guruh_prefiksi
            reja.save(
                update_fields=["talabalar_soni", "guruhlar_soni", "guruh_prefiksi"]
            )
            guruhlarni_sinxronlash(reja)
    except (
        BadZipFile,
        InvalidFileException,
        ET.ParseError,
        KeyError,
        ValueError,
        EOFError,
    ) as xato:
        raise ImportXato("fayl .xlsx formatida emas yoki buzilgan") from xato
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
