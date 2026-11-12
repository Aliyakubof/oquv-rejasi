"""Renders the official o'quv dastur (.docx) for one course, pre-filled from
data already in the DB. Content the system has no source for (Tuzuvchi,
Taqrizchilar, council protocol numbers, ...) is left blank for the teacher
to fill in afterward in Word.
"""

from io import BytesIO
from pathlib import Path

from docxtpl import DocxTemplate

from accounts.models import OqituvchiProfil
from plans.dastur.kontekst import dastur_kontekst
from plans.dastur.soat_ustunlari import soat_ustunlarini_tozala
from plans.models import FanVariant, SoatTuri, Yuklama

SABLON_YOLI = Path(__file__).resolve().parent / "oquv_dastur.docx"


def dastur_egasimi(variant: FanVariant, oqituvchi: OqituvchiProfil) -> bool:
    """True if `oqituvchi` holds this course's lecture (MARUZA).

    A FanVariant's semesters already belong to one fixed curriculum year via
    its OquvReja, so there is nothing to compare against "today" — filtering
    by the calendar's current academic year would wrongly reject the real
    owner whenever that year has no imported data yet.
    """
    return Yuklama.objects.filter(
        fan_semestr__variant=variant, tur=SoatTuri.MARUZA, oqituvchi=oqituvchi
    ).exists()


def dastur_render(variant: FanVariant) -> BytesIO:
    hujjat = DocxTemplate(SABLON_YOLI)
    hujjat.render(dastur_kontekst(variant), autoescape=True)
    # `.docx` and not `.get_docx()`: the latter reloads the template from disk
    # after a render, silently discarding everything just rendered.
    soat_ustunlarini_tozala(hujjat.docx, variant)
    buffer = BytesIO()
    hujjat.save(buffer)
    buffer.seek(0)
    return buffer
