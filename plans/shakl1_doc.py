"""1-shakl personal teacher workload Word (.docx) and .zip batch exporter."""

import re
from collections import defaultdict
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm, Pt
from docx.table import Table, _Cell

from accounts.models import Department, OqituvchiProfil
from accounts.services import universitet_nomi
from plans.models import Yuklama
from plans.shakl1 import shakl1_satrlarini_yigish

_SHAKL1_USTUNLAR = [
    "№",
    "Fan nomi",
    "Yo'nalish",
    "Kurs / Sem",
    "Guruh / Oqim",
    "Ma'ruza",
    "Amaliyot",
    "Lab.",
    "Seminar",
    "Kurs ishi",
    "Jami",
]


def _xavfsiz_nom(matn: str) -> str:
    toza = re.sub(r"[^A-Za-z0-9_-]+", "_", matn.strip()).strip("_")
    return toza[:60] or "oqituvchi"


def _sahifa_sozlash(doc: Document) -> None:
    section = doc.sections[0]
    section.orientation = WD_ORIENT.LANDSCAPE
    section.page_width, section.page_height = section.page_height, section.page_width
    for chet in ("top_margin", "bottom_margin", "left_margin", "right_margin"):
        setattr(section, chet, Cm(1.4))


def _sarlavha_yozish(
    doc: Document,
    profil: OqituvchiProfil,
    akademik_yil: int,
    jami_soat: int,
) -> None:
    uni = universitet_nomi("Oliy ta'lim muassasasi")
    p_uni = doc.add_paragraph()
    p_uni.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r_uni = p_uni.add_run(uni.upper())
    r_uni.bold = True
    r_uni.font.size = Pt(11)

    p_tit = doc.add_paragraph()
    p_tit.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r_tit = p_tit.add_run(
        "1-SHAKL: O'QITUVCHINING SHAXSIY O'QUV YUKLAMASI "
        f"({akademik_yil}/{akademik_yil + 1})"
    )
    r_tit.bold = True
    r_tit.font.size = Pt(12)

    kamomad = max(0, profil.turi.min_soat - jami_soat)
    malumot = doc.add_paragraph()
    r_info = malumot.add_run(
        f"Kafedra: {profil.kafedra.nomi}   |   "
        f"O'qituvchi: {profil}   |   "
        f"Lavozim: {profil.turi.nomi} (norma: {profil.turi.min_soat} soat)   |   "
        f"Jami yuklama: {jami_soat} soat"
        + (f" (kamomad: {kamomad} soat)" if kamomad else "")
    )
    r_info.font.size = Pt(9.5)


def _katakka_matn(katak: _Cell, matn: str, *, qalin: bool = False) -> None:
    p = katak.paragraphs[0]
    r = p.add_run(matn)
    r.font.size = Pt(8.5)
    r.bold = qalin


def _jadval_toldirish(
    jadval: Table, satrlar: list[dict[str, object]], jami_soat: int
) -> None:
    for col_idx, nomi in enumerate(_SHAKL1_USTUNLAR):
        _katakka_matn(jadval.rows[0].cells[col_idx], nomi, qalin=True)

    if not satrlar:
        bosh = jadval.add_row()
        _katakka_matn(bosh.cells[1], "Ushbu o'quv yili uchun yuklama biriktirilmagan.")
        return

    yigindi = {
        "maruza": 0,
        "amaliyot": 0,
        "laboratoriya": 0,
        "seminar": 0,
        "kurs_ishi": 0,
    }
    for idx, q in enumerate(satrlar, start=1):
        row = jadval.add_row().cells
        for k in yigindi:
            yigindi[k] += int(q.get(k, 0))
        qiymatlar = [
            str(idx),
            str(q["fan"]),
            str(q["yonalish"]),
            f"{q['kurs']}-kurs / {q['semestr']}-sem",
            str(q["guruh"]),
            str(q["maruza"] or "—"),
            str(q["amaliyot"] or "—"),
            str(q["laboratoriya"] or "—"),
            str(q["seminar"] or "—"),
            str(q["kurs_ishi"] or "—"),
            str(q["jami"]),
        ]
        for col_idx, qiymat in enumerate(qiymatlar):
            _katakka_matn(row[col_idx], qiymat, qalin=(col_idx == len(qiymatlar) - 1))

    yakun = jadval.add_row().cells
    _katakka_matn(yakun[1], "JAMI:", qalin=True)
    for offset, k in enumerate(
        ("maruza", "amaliyot", "laboratoriya", "seminar", "kurs_ishi"), start=5
    ):
        _katakka_matn(yakun[offset], str(yigindi[k]), qalin=True)
    _katakka_matn(yakun[10], str(jami_soat), qalin=True)


def _shakl1_hujjat_yarat(
    profil: OqituvchiProfil, akademik_yil: int, yuklamalar: list[Yuklama]
) -> BytesIO:
    satrlar, _ = shakl1_satrlarini_yigish(yuklamalar)
    jami_soat = sum(y.soat for y in yuklamalar)
    doc = Document()
    _sahifa_sozlash(doc)
    _sarlavha_yozish(doc, profil, akademik_yil, jami_soat)

    jadval = doc.add_table(rows=1, cols=len(_SHAKL1_USTUNLAR))
    jadval.style = "Table Grid"
    jadval.alignment = WD_TABLE_ALIGNMENT.CENTER
    _jadval_toldirish(jadval, satrlar, jami_soat)

    imzo = doc.add_paragraph()
    imzo.paragraph_format.space_before = Pt(12)
    r_imzo = imzo.add_run(
        "O'qituvchi: _____________________        "
        "Kafedra mudiri: _____________________        "
        "O'quv bo'limi: _____________________"
    )
    r_imzo.font.size = Pt(9.5)

    buf = BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf


def shakl1_docx_render(profil: OqituvchiProfil, akademik_yil: int) -> BytesIO:
    """Render one teacher's 1-shakl individual workload plan as .docx."""
    yuklamalar = list(
        Yuklama.objects.filter(oqituvchi=profil)
        .akademik_yilda(akademik_yil)
        .select_related("fan_semestr__variant__fan__reja", "guruh")
        .order_by("fan_semestr__semestr", "fan_semestr__variant__nomi", "tur")
    )
    return _shakl1_hujjat_yarat(profil, akademik_yil, yuklamalar)


def shakl1_zip_yarat(
    akademik_yil: int, *, kafedra: Department | None = None
) -> BytesIO:
    """Bundle active teachers' 1-shakl .docx files into a .zip archive."""
    qs_prof = (
        OqituvchiProfil.objects.filter(foydalanuvchi__is_active=True)
        .toliq()
        .order_by(
            "kafedra__nomi", "foydalanuvchi__last_name", "foydalanuvchi__first_name"
        )
    )
    qs_yuk = (
        Yuklama.objects.akademik_yilda(akademik_yil)
        .select_related("fan_semestr__variant__fan__reja", "guruh")
        .order_by("fan_semestr__semestr", "fan_semestr__variant__nomi", "tur")
    )
    if kafedra is not None:
        qs_prof = qs_prof.filter(kafedra=kafedra)
        qs_yuk = qs_yuk.filter(oqituvchi__kafedra=kafedra)

    yuk_xaritasi: dict[int, list[Yuklama]] = defaultdict(list)
    for y in qs_yuk:
        yuk_xaritasi[y.oqituvchi_id].append(y)

    buf = BytesIO()
    profillar = list(qs_prof)
    with ZipFile(buf, "w", compression=ZIP_DEFLATED) as zf:
        if not profillar:
            zf.writestr(
                "README.txt",
                (
                    f"{akademik_yil}/{akademik_yil + 1} o'quv yili uchun "
                    "faol o'qituvchilar topilmadi."
                ),
            )
        else:
            for p in profillar:
                doc_buf = _shakl1_hujjat_yarat(
                    p, akademik_yil, yuk_xaritasi.get(p.pk, [])
                )
                kaf_qism = _xavfsiz_nom(p.kafedra.nomi)
                ism_qism = _xavfsiz_nom(
                    f"{p.foydalanuvchi.last_name}_{p.foydalanuvchi.first_name}"
                )
                fayl_nomi = f"{kaf_qism}/{ism_qism}_{p.pk}_1shakl.docx"
                zf.writestr(fayl_nomi, doc_buf.getvalue())
    buf.seek(0)
    return buf
