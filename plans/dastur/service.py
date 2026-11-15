"""Bitta fan uchun bazadagi ma'lumotlardan rasmiy o'quv dastur (.docx) yasaydi.

Tizimda yo'q maydonlar (Tuzuvchi, Taqrizchilar, kengash bayonnomasi va h.k.)
bo'sh qoldiriladi — o'qituvchi ularni keyin Word'da o'zi to'ldiradi.
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
    """O'qituvchida shu fanning ma'ruza (MARUZA) yuklamasi bo'lsa True qaytaradi.

    FanVariant semestrlari o'z OquvReja yiliga bog'liq, shuning uchun joriy
    kalendar o'quv yili bilan filtrlash noto'g'ri bo'lardi — aks holda hali
    joriy yilga import qilinmagan fan egasi rad etilib qolardi.
    """
    return Yuklama.objects.filter(
        fan_semestr__variant=variant, tur=SoatTuri.MARUZA, oqituvchi=oqituvchi
    ).exists()


def dastur_render(variant: FanVariant) -> BytesIO:
    hujjat = DocxTemplate(SABLON_YOLI)
    hujjat.render(dastur_kontekst(variant), autoescape=True)
    # `.get_docx()` emas, aynan `.docx`: aks holda shablon diskdan qayta
    # yuklanib, hozirgina render qilingan hamma matn yo'qolib ketadi.
    soat_ustunlarini_tozala(hujjat.docx, variant)
    buffer = BytesIO()
    hujjat.save(buffer)
    buffer.seek(0)
    return buffer
