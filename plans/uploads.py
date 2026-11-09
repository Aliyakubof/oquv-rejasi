"""Orchestrate a browser-uploaded reja file into the importer."""

import uuid
from dataclasses import dataclass
from pathlib import Path
from zipfile import BadZipFile

from django.conf import settings
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction

from plans.importer import ImportNatija, ImportXato, import_reja, parse_xlsx
from plans.services import guruhlarni_sinxronlash

YUKLASH_KATALOGI = "rejalar"


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
    """Save the upload, parse it and persist reja + counts atomically.

    If parsing or importing fails, the invalid file is removed from disk so
    orphaned uploads do not accumulate.
    """
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
    except BadZipFile as xato:
        yol.unlink(missing_ok=True)
        raise ImportXato("fayl .xlsx formatida emas yoki buzilgan") from xato
    except Exception:
        yol.unlink(missing_ok=True)
        raise
    return natija


def _faylni_saqlash(fayl: UploadedFile) -> Path:
    katalog = Path(settings.MEDIA_ROOT) / YUKLASH_KATALOGI
    katalog.mkdir(parents=True, exist_ok=True)
    yol = katalog / f"{uuid.uuid4().hex[:8]}_{Path(fayl.name).name}"
    with open(yol, "wb") as nishon:
        for parcha in fayl.chunks():
            nishon.write(parcha)
    return yol
