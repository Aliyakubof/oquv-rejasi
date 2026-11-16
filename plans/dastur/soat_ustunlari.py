"""Fan bo'yicha 0 soatli turlar uchun 1-jadvaldagi ustunlar va 5-bo'lim
sarlavha qatorlarini olib tashlaydi.

docxtpl teglarni almashtiradi, lekin {%tr %} siklidan tashqaridagi jadval
ustuni yoki qatorini o'chira olmaydi — shuning uchun ular OOXML darajasida kesiladi.
"""

from docx.document import Document
from docx.oxml.ns import qn
from docx.oxml.table import CT_Tc
from docx.table import Table

from plans.models import FanVariant

JADVAL_INDEKSI = 2
JADVAL_SONI = 4
GRID_USTUNLARI = 11

# 1-jadvaldagi grid ustun indeksi -> FanVariant ning tegishli soat maydoni.
SOAT_USTUNLARI: tuple[tuple[int, str], ...] = (
    (4, "maruza_soat"),
    (5, "amaliyot_soat"),
    (6, "laboratoriya_soat"),
    (7, "seminar_soat"),
)

# 5-bo'limdagi ichki sarlavha matnlari (jadval tartibida maydonlar bilan juft).
SOAT_SARLAVHALARI: tuple[tuple[str, str], ...] = (
    ("Ma’ruza (M)", "maruza_soat"),
    ("Amaliy mashg‘ulot (A)", "amaliyot_soat"),
    ("Laboratoriya mashg‘ulot (L)", "laboratoriya_soat"),
    ("Seminar (S)", "seminar_soat"),
)


def soat_ustunlarini_tozala(hujjat: Document, variant: FanVariant) -> None:
    """Soati yo'q mashg'ulot turlarini 1-bo'lim ustunidan hamda 5-bo'limdagi
    ortiqcha kichik sarlavhalardan olib tashlaydi.
    """
    table = _jadval1(hujjat)
    bosh_turlar = [
        maydon for _, maydon in SOAT_USTUNLARI if not getattr(variant, maydon)
    ]
    if len(bosh_turlar) < len(SOAT_USTUNLARI):
        _ustunlarni_ochir(table, bosh_turlar)
    _bosh_sarlavhalarni_ochir(table, variant)


def _ustunlarni_ochir(table: Table, bosh_turlar: list[str]) -> None:
    """`bosh_turlar` ustunlarini 1-bo'limdan o'chiradi va bo'shagan kenglikni
    qolgan soat ustunlariga teng bo'lib beradi.
    """
    ochiriladigan = [ustun for ustun, maydon in SOAT_USTUNLARI if maydon in bosh_turlar]
    if sorted(ochiriladigan) == [4, 5, 6]:
        _semestr_kataklarini_surish(table)

    bosh_kenglik = 0
    for ustun in sorted(ochiriladigan, reverse=True):
        bosh_kenglik += _ustunni_ochir(table, ustun)

    omon_qolganlar = [
        ustun - sum(1 for o in ochiriladigan if o < ustun)
        for ustun, maydon in SOAT_USTUNLARI
        if maydon not in bosh_turlar
    ]
    _ustunlarni_kengaytir(table, omon_qolganlar, bosh_kenglik)
    _kengliklarni_qayta_hisobla(table)


def _semestr_kataklarini_surish(table: Table) -> None:
    """Faqat Seminar (7-ustun) qolsa, Semestr/Tartib 6-ustunda tugab ECTS/Haftadagi
    7-dan boshlanadi; ustun chegarasi buzilmasligi uchun span chapga suriladi.
    """
    for tr in table._tbl.findall(qn("w:tr")):
        tclar = tr.findall(qn("w:tc"))
        joriy = 0
        for idx, tc in enumerate(tclar[:-1]):
            span = _span(tc)
            keyingi = tclar[idx + 1]
            keyingi_span = _span(keyingi)
            if joriy == 4 and span == 3 and keyingi_span >= 2:
                _span_ornat(tc, span + 1)
                _span_ornat(keyingi, keyingi_span - 1)
                break
            joriy += span


def _span_ornat(tc: CT_Tc, yangi_span: int) -> None:
    if tc.tcPr is None:
        return
    gridspan = tc.tcPr.find(qn("w:gridSpan"))
    if gridspan is not None:
        gridspan.set(qn("w:val"), str(yangi_span))


def _bosh_sarlavhalarni_ochir(table: Table, variant: FanVariant) -> None:
    """5-bo'limda soati nol bo'lgan mashg'ulot sarlavha qatorini o'chiradi."""
    for label, maydon in SOAT_SARLAVHALARI:
        if getattr(variant, maydon):
            continue
        tr = _sarlavha_qatorini_top(table, label)
        if tr is not None:
            tr.getparent().remove(tr)


def _sarlavha_qatorini_top(table: Table, label: str):
    """Word matnni bir nechta `w:t` bo'laklarga bo'lib yuboradi — shuning uchun
    qidiruvdan oldin qatordagi barcha matnni birlashtirib solishtiramiz.
    """
    for tr in table._tbl.findall(qn("w:tr")):
        matn = "".join(t.text or "" for t in tr.iter(qn("w:t")))
        if label in matn:
            return tr
    return None


def _tbl_grid(table: Table):
    grid = table._tbl.find(qn("w:tblGrid"))
    if grid is None:
        raise ValueError("1-jadvalda w:tblGrid topilmadi.")
    return grid


def _jadval1(hujjat: Document) -> Table:
    if len(hujjat.tables) != JADVAL_SONI:
        raise ValueError(
            f"Kutilgan {JADVAL_SONI} ta jadval, topildi: {len(hujjat.tables)}. "
            "Shablon tuzilishi o‘zgargan bo‘lsa, SOAT_USTUNLARI ham yangilanishi kerak."
        )
    table = hujjat.tables[JADVAL_INDEKSI]
    ustunlar = len(_tbl_grid(table).findall(qn("w:gridCol")))
    if ustunlar != GRID_USTUNLARI:
        raise ValueError(
            f"1-jadvalda {GRID_USTUNLARI} ta grid ustuni kutilgan, topildi: {ustunlar}."
        )
    return table


def _ustunni_ochir(table: Table, ustun: int) -> int:
    """Bitta grid ustunni o'chiradi va bo'shagan kenglikni qaytaradi."""
    grid = _tbl_grid(table)
    gridcol = grid.findall(qn("w:gridCol"))[ustun]
    bosh_kenglik = int(gridcol.get(qn("w:w")))
    grid.remove(gridcol)

    for tr in table._tbl.findall(qn("w:tr")):
        joriy = 0
        for tc in tr.findall(qn("w:tc")):
            span = _span(tc)
            if joriy <= ustun < joriy + span:
                if span == 1:
                    tr.remove(tc)
                else:
                    gridspan = (
                        tc.tcPr.find(qn("w:gridSpan")) if tc.tcPr is not None else None
                    )
                    if gridspan is None:
                        raise ValueError(
                            "Birlashtirilgan katakda w:gridSpan topilmadi."
                        )
                    gridspan.set(qn("w:val"), str(span - 1))
                break
            joriy += span
    return bosh_kenglik


def _ustunlarni_kengaytir(
    table: Table, omon_qolganlar: list[int], bosh_kenglik: int
) -> None:
    """Bo'shagan kenglikni qolgan ustunlarga teng bo'lib beradi, qoldig'i chapga."""
    if not omon_qolganlar:
        return
    gridcols = _tbl_grid(table).findall(qn("w:gridCol"))
    ulush, qoldiq = divmod(bosh_kenglik, len(omon_qolganlar))
    for tartib, ustun in enumerate(omon_qolganlar):
        gridcol = gridcols[ustun]
        qoshimcha = ulush + (1 if tartib < qoldiq else 0)
        gridcol.set(qn("w:w"), str(int(gridcol.get(qn("w:w"))) + qoshimcha))


def _kengliklarni_qayta_hisobla(table: Table) -> None:
    """Har bir katak kengligini yangilangan grid asosida qaytadan yozib chiqadi."""
    kengliklar = [
        int(gridcol.get(qn("w:w")))
        for gridcol in _tbl_grid(table).findall(qn("w:gridCol"))
    ]
    for tr in table._tbl.findall(qn("w:tr")):
        joriy = 0
        for tc in tr.findall(qn("w:tc")):
            span = _span(tc)
            tcW = tc.tcPr.find(qn("w:tcW")) if tc.tcPr is not None else None
            if tcW is not None:
                tcW.set(qn("w:w"), str(sum(kengliklar[joriy : joriy + span])))
            joriy += span


def _span(tc: CT_Tc) -> int:
    gridspan = tc.tcPr.find(qn("w:gridSpan")) if tc.tcPr is not None else None
    return int(gridspan.get(qn("w:val"))) if gridspan is not None else 1
