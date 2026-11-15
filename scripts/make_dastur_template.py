r"""
Asl namunaviy hujjatdan plans/dastur/oquv_dastur.docx shablonini yasaydi.

Bir marta ishga tushiriladi, faqat universitet shaklning o'zini yangilasa qayta:

    venv\Scripts\python.exe scripts\make_dastur_template.py

sources/Kiberxavfsizlik_asoslari_fan_dasturi_ATDT.docx faylini faqat o'qish
uchun ochib, aniq qiymatlarni Jinja teglariga almashtiradi va takroriy
qatorlarni {%tr for %} sikllariga yig'adi. Chiziq, birlashtirish va shriftlar
o'zgarishsiz qoladi — faqat matn yangilanadi.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.table import Table, _Cell
from docx.text.paragraph import Paragraph

ILDIZ = Path(__file__).resolve().parent.parent
MANBA = ILDIZ / "sources" / "Kiberxavfsizlik_asoslari_fan_dasturi_ATDT.docx"
SHABLON = ILDIZ / "plans" / "dastur" / "oquv_dastur.docx"


# --------------------------------------------------------------------------
# quyi darajadagi yordamchilar
# --------------------------------------------------------------------------


def abzas_matnini_yoz(p: Paragraph, text: str) -> None:
    """Birinchi run formatini saqlagan holda abzas matnini almashtiradi.

    Word matnni bir nechta run bo'laklariga bo'lib yuboradi, shu bois oddiy
    qidirib-almashtirish chegaradagi teglarni o'tkazib yuboradi. Bitta run ga
    yig'ish bu muammoni butunlay bartaraf etadi.
    """
    runs = p.runs
    if not runs:
        p.add_run(text)
        return
    runs[0].text = text
    for r in runs[1:]:
        r._element.getparent().remove(r._element)


def abzasni_almashtir(p: Paragraph, replacements: list[tuple[str, str]]) -> None:
    """Aralash abzasni bitta run ga yig'ib, to'liq matnida almashtirish bajaradi.

    Abzasning faqat bir qismi tegga aylanadigan joylar (masalan, kafedra
    haqidagi gap) uchun ishlatiladi.
    """
    text = p.text
    for old, new in replacements:
        if old not in text:
            raise LookupError(f"{old!r} matni abzasda topilmadi: {p.text!r}")
        text = text.replace(old, new)
    abzas_matnini_yoz(p, text)


def matn_abzasini_top(doc: Document, needle: str) -> Paragraph:
    matches = [p for p in doc.paragraphs if needle in p.text]
    if not matches:
        raise LookupError(f"asosiy matn abzasi topilmadi: {needle!r}")
    if len(matches) > 1:
        raise LookupError(
            f"{needle!r} abzasi noaniq ({len(matches)} ta moslik topildi)"
        )
    return matches[0]


def katak_abzasi(table: Table, row: int, col: int, idx: int = 0) -> Paragraph:
    """python-docx jadvalidagi 1-asosli qator/ustun; idx 0-asosli abzas."""
    return table.rows[row - 1].cells[col - 1].paragraphs[idx]


def katakka_yoz(table: Table, row: int, col: int, text: str, idx: int = 0) -> None:
    abzas_matnini_yoz(katak_abzasi(table, row, col, idx), text)


def korinadigan_kataklar(row) -> list[_Cell]:
    """Birlashtirilgan qatorda `.cells` bitta katakni takrorlaydi; har biri 1 marta."""
    seen: set[int] = set()
    cells = []
    for cell in row.cells:
        if id(cell._tc) in seen:
            continue
        seen.add(id(cell._tc))
        cells.append(cell)
    return cells


def qatorni_top(table: Table, needle: str, *, bosh_qator: int = 1) -> int:
    """`bosh_qator` dan boshlab `needle` bor birinchi qatorning 1-asosli indeksi.

    Qator raqamiga emas, matniga tayanish oldingi qadamlar qatorlarni
    o'chirganda ham keyingi qidiruvlarni buzmaydi.
    """
    for i in range(bosh_qator, len(table.rows) + 1):
        if any(needle in c.text for c in korinadigan_kataklar(table.rows[i - 1])):
            return i
    raise LookupError(f"{bosh_qator}-qatordan keyin {needle!r} topilmadi")


def abzasni_ochir(p: Paragraph) -> None:
    p._p.getparent().remove(p._p)


def qatorlarni_ochir(table: Table, first: int, last: int) -> None:
    """1-asosli first..last qatorlarni pastdan tepaga o'chiradi (indeks buzilmaydi)."""
    for i in range(last, first - 1, -1):
        tr = table.rows[i - 1]._tr
        tr.getparent().remove(tr)


def _teg_qatori_qil(row, tag: str) -> None:
    """Boshqaruv qatorining barcha kataklarini tozalab, birinchisiga tegni yozadi."""
    for i, cell in enumerate(korinadigan_kataklar(row)):
        for j, p in enumerate(cell.paragraphs):
            if j == 0:
                abzas_matnini_yoz(p, tag if i == 0 else "")
            else:
                abzasni_ochir(p)


def siklga_ora(table: Table, first: int, last: int, opener: str, closer: str) -> None:
    """`first` dan oldin `opener`, `last` dan keyin `closer` qatorini qo'shadi.

    docxtpl {%tr %} tegi yozilgan qatorlarni yakuniy hujjatda o'chiradi.
    """
    tail = copy.deepcopy(table.rows[last - 1]._tr)
    if last == len(table.rows):
        table._tbl.append(tail)
        closer_row = table.rows[-1]
    else:
        table.rows[last]._tr.addprevious(tail)
        closer_row = table.rows[last]
    _teg_qatori_qil(closer_row, closer)

    head = copy.deepcopy(table.rows[first - 1]._tr)
    table.rows[first - 1]._tr.addprevious(head)
    _teg_qatori_qil(table.rows[first - 1], opener)


def _katak_oraligi(tc) -> int:
    pr = tc.find(qn("w:tcPr"))
    gridspan = pr.find(qn("w:gridSpan")) if pr is not None else None
    return int(gridspan.get(qn("w:val"))) if gridspan is not None else 1


def _jadval_tizimi(table: Table):
    grid = table._tbl.find(qn("w:tblGrid"))
    if grid is None:
        raise ValueError("w:tblGrid topilmadi")
    return grid


def _tc_span_oshir(tc, span: int) -> None:
    pr = tc.find(qn("w:tcPr"))
    gridspan = pr.find(qn("w:gridSpan")) if pr is not None else None
    if gridspan is None:
        raise ValueError("w:gridSpan topilmadi")
    gridspan.set(qn("w:val"), str(span + 1))


def ustun_qosh(
    table: Table,
    ustundan_keyin: int,
    kenglik: int,
    *,
    bolinadigan_qatorlar: list[int],
    kengayadigan_qatorlar: list[int],
    oxirgi_katak_qatorlar: list[int] = (),
) -> None:
    """0-asosli `ustundan_keyin` ustunidan `kenglik` ajratib, yangi ustun qo'shadi.

    Faqat ko'rsatilgan qatorlargina o'zgartiriladi: `bolinadigan_qatorlar` ga
    bo'sh `w:tc` qo'shiladi, `kengayadigan_qatorlar` da `gridSpan` 1 ga oshadi,
    `oxirgi_katak_qatorlar` da esa oxirgi katak kengaytiriladi.
    """
    grid = _jadval_tizimi(table)
    gridcols = grid.findall(qn("w:gridCol"))
    old_width = int(gridcols[ustundan_keyin].get(qn("w:w")))
    gridcols[ustundan_keyin].set(qn("w:w"), str(old_width - kenglik))
    new_gridcol = OxmlElement("w:gridCol")
    new_gridcol.set(qn("w:w"), str(kenglik))
    gridcols[ustundan_keyin].addnext(new_gridcol)

    targets = set(bolinadigan_qatorlar) | set(kengayadigan_qatorlar)
    for row_idx, tr in enumerate(table._tbl.findall(qn("w:tr")), start=1):
        if row_idx in oxirgi_katak_qatorlar:
            tc = tr.findall(qn("w:tc"))[-1]
            _tc_span_oshir(tc, _katak_oraligi(tc))
            continue
        if row_idx not in targets:
            continue
        col = 0
        for tc in tr.findall(qn("w:tc")):
            span = _katak_oraligi(tc)
            if col <= ustundan_keyin < col + span:
                if row_idx in kengayadigan_qatorlar:
                    _tc_span_oshir(tc, span)
                else:
                    new_tc = copy.deepcopy(tc)
                    for p in new_tc.findall(qn("w:p")):
                        for run in p.findall(qn("w:r")):
                            p.remove(run)
                    tc.addnext(new_tc)
                break
            col += span

    _kengliklarni_qayta_hisobla(table)


def _kengliklarni_qayta_hisobla(table: Table) -> None:
    """Har bir katakning w:tcW enini joriy tblGrid asosida qayta hisoblaydi.

    Ustun qo'shilgandan keyin kerak, chunki gridSpan o'zgarishi katak enini
    o'z-o'zidan yangilamaydi.
    """
    widths = [
        int(gridcol.get(qn("w:w")))
        for gridcol in _jadval_tizimi(table).findall(qn("w:gridCol"))
    ]
    for tr in table._tbl.findall(qn("w:tr")):
        col = 0
        for tc in tr.findall(qn("w:tc")):
            span = _katak_oraligi(tc)
            pr = tc.find(qn("w:tcPr"))
            tcW = pr.find(qn("w:tcW")) if pr is not None else None
            if tcW is not None:
                tcW.set(qn("w:w"), str(sum(widths[col : col + span])))
            col += span


# --------------------------------------------------------------------------
# hujjat bo'limlarini tahrirlash
# --------------------------------------------------------------------------


def muqovani_tahrirla(doc: Document) -> None:
    abzas_matnini_yoz(
        matn_abzasini_top(doc, "KIBERXAVFSIZLIK ASOSLARI"), "{{ course.name|upper }}"
    )
    abzas_matnini_yoz(
        matn_abzasini_top(doc, "kunduzgi ta’lim uchun"), "({{ education_form }} uchun)"
    )
    abzas_matnini_yoz(
        matn_abzasini_top(doc, "Bilim sohasi:"),
        "Bilim sohasi:\t{{ major.bilim_sohasi }}",
    )
    abzas_matnini_yoz(
        matn_abzasini_top(doc, "Ta’lim sohasi:"),
        "Ta’lim sohasi:\t{{ major.talim_sohasi }}",
    )
    abzas_matnini_yoz(
        matn_abzasini_top(doc, "Ta’lim yo‘nalishi:"),
        "Ta’lim yo‘nalishi:\t{{ major.talim_yonalishi }}",
    )
    abzasni_almashtir(
        matn_abzasini_top(doc, "Namangan – 2026"),
        [("Namangan – 2026", "{{ city }} – {{ year }}")],
    )

    kafedra = matn_abzasini_top(doc, "kafedrasi tomonidan taqdim etilgan")
    abzasni_almashtir(
        kafedra,
        [
            (
                "Turan International University Filologiya kafedrasi tomonidan "
                "taqdim etilgan (kafedraning 2026-yil"
                + "_" * 19
                + "-sonli yig‘ilish bayoni).",
                "{{ university }} {{ kafedra }} kafedrasi tomonidan taqdim etilgan "
                "(kafedraning {{ kafedra_council.year }}-yil "
                "{{ kafedra_council.date }}-sonli yig‘ilish bayoni).",
            )
        ],
    )

    # Tasdiqlash katagi: "TASDIQLAYMAN", universitet nomi va sana joylari.
    approval = doc.tables[0].rows[0].cells[1]
    abzas_matnini_yoz(approval.paragraphs[1], "{{ university }}")
    abzas_matnini_yoz(approval.paragraphs[4], "{{ year }}-yil “___” _________")

    # Tuzuvchi/Taqrizchilar: namunadagi ismlarni bo'sh qoldiramiz.
    abzas_matnini_yoz(matn_abzasini_top(doc, "S.Komilov"), "")
    abzas_matnini_yoz(matn_abzasini_top(doc, "S.Xashimov"), "")


def seminar_ustunini_qosh(doc: Document) -> None:
    """Namunaviy hujjatdagi 3 soat ustuni yonidan yangi "Seminar" ustuni ochadi.

    98 qatorli jadval o'zgarmagan paytda eng birinchi ishlashi shart: 4-qator
    kengayadi, 5-6-qatorlarga bo'sh katak qo'shiladi, 7-98-qatorlar esa jadval
    bo'ylab to'liq enini saqlash uchun 1 ustunga kengaytiriladi.
    """
    t = doc.tables[1]
    ustun_qosh(
        t,
        ustundan_keyin=6,
        kenglik=360,
        bolinadigan_qatorlar=[5, 6],
        kengayadigan_qatorlar=[1, 4, *range(7, len(t.rows) + 1)],
        oxirgi_katak_qatorlar=[2, 3],
    )
    katakka_yoz(t, 5, 8, "Seminar")
    katakka_yoz(t, 6, 8, "{{ hours.seminar }}")


def fan_malumotlarini_tahrirla(doc: Document) -> None:
    """1-bo'lim, table[1] ning 1-6-qatorlari.

    9+ ustunlar bittaga surilgan, chunki seminar ustuni oldin qo'shilgan.
    """
    t = doc.tables[1]
    katakka_yoz(t, 2, 1, "{{ course.code }}", idx=1)
    katakka_yoz(t, 2, 4, "{{ academic_years_str }}", idx=1)
    katakka_yoz(t, 2, 5, "{{ semesters_str }}", idx=1)
    katakka_yoz(t, 2, 9, "{{ credits_str }}", idx=1)
    katakka_yoz(t, 3, 1, "{{ course.module_type }}", idx=1)
    katakka_yoz(t, 3, 4, "{{ language }}", idx=1)
    katakka_yoz(t, 3, 5, "{{ plan_number }}", idx=1)
    katakka_yoz(t, 3, 9, "{{ weekly_hours_str }}", idx=1)
    katakka_yoz(t, 4, 1, "{{ course.name }}", idx=1)

    abzasni_almashtir(
        katak_abzasi(t, 4, 5),
        [("jami – 72 soat, shundan:", "jami – {{ classroom_total }} soat, shundan:")],
    )

    katakka_yoz(t, 6, 4, "{{ total_hours }}")
    katakka_yoz(t, 6, 5, "{{ hours.lecture }}")
    katakka_yoz(t, 6, 6, "{{ hours.practice }}")
    katakka_yoz(t, 6, 7, "{{ hours.lab }}")
    katakka_yoz(t, 6, 9, "{{ hours.self_study }}")
    katakka_yoz(t, 6, 10, "{{ hours.coursework }}")


def mazmunni_tahrirla(doc: Document) -> None:
    """2-bo'lim: maqsad va vazifalar bitta katakdagi ikkita abzasda joylashgan."""
    t = doc.tables[1]
    row = qatorni_top(t, "Fanning maqsadi")
    katakka_yoz(t, row, 1, "{{ purpose }}", idx=0)
    katakka_yoz(t, row, 1, "{{ tasks }}", idx=1)


def _bitta_qatorga_qisqartir(
    t: Table, header_needle: str, first_item_needle: str, group_size: int
) -> int:
    """Takroriy blokning 2..group_size qatorlarini o'chirib, birinchisini qaytaradi."""
    header = qatorni_top(t, header_needle)
    item1 = qatorni_top(t, first_item_needle, bosh_qator=header)
    qatorlarni_ochir(t, item1 + 1, item1 + group_size - 1)
    return item1


def zarur_bilimlarni_tahrirla(doc: Document) -> None:
    """3-bo'lim: 3 ta zaruriy fan qatorini siklga aylantiradi."""
    t = doc.tables[1]
    item1 = _bitta_qatorga_qisqartir(
        t, "Fanni o‘zlashtirish uchun zarur", "(ATD1308)", 3
    )
    katakka_yoz(t, item1, 1, "{{ loop.index }}.")
    katakka_yoz(t, item1, 2, "{{ item }}")
    siklga_ora(t, item1, item1, "{%tr for item in prerequisites %}", "{%tr endfor %}")


def natijalarni_tahrirla(doc: Document) -> None:
    """4-bo'lim: TN1-5 kasbiy va TN6-10 ko'nikma qatorlarini alohida siklga yig'adi."""
    t = doc.tables[1]
    _bitta_qatorga_qisqartir(t, "Ko‘nikmalar:", "TN6", 5)
    _bitta_qatorga_qisqartir(t, "Kasbiy kompetensiyalar:", "TN1", 5)

    tn1 = qatorni_top(t, "TN1")
    tn6 = qatorni_top(t, "TN6", bosh_qator=tn1)
    for row in (tn6, tn1):
        katakka_yoz(t, row, 1, "{{ o.code }}")
        katakka_yoz(t, row, 2, "{{ o.text }}")
    siklga_ora(t, tn6, tn6, "{%tr for o in outcomes.skills %}", "{%tr endfor %}")
    siklga_ora(t, tn1, tn1, "{%tr for o in outcomes.professional %}", "{%tr endfor %}")


def mavzularni_tahrirla(doc: Document) -> None:
    """5-bo'lim: M/A/L mashg'ulot turlarini siklga yig'ib, Seminar (S) qo'shadi."""
    t = doc.tables[1]
    _bitta_qatorga_qisqartir(t, "Laboratoriya mashg‘ulot (L)", "L1", 12)
    _bitta_qatorga_qisqartir(t, "Amaliy mashg‘ulot (A)", "A1", 12)
    _bitta_qatorga_qisqartir(t, "Ma’ruza (M)", "M1", 12)

    m1 = qatorni_top(t, "M1")
    a1 = qatorni_top(t, "A1", bosh_qator=m1)
    l1 = qatorni_top(t, "L1", bosh_qator=a1)
    a_hdr, l_hdr = a1 - 1, l1 - 1

    for row in (l1, a1, m1):
        katakka_yoz(t, row, 1, "{{ t.code }}")
        katakka_yoz(t, row, 2, "{{ t.title }}")
        katakka_yoz(t, row, 11, "{{ t.hours }}")
    katakka_yoz(t, m1 - 1, 11, "{{ hours.lecture }}")
    katakka_yoz(t, a_hdr, 11, "{{ hours.practice }}")
    katakka_yoz(t, l_hdr, 11, "{{ hours.lab }}")
    siklga_ora(t, l1, l1, "{%tr for t in labs %}", "{%tr endfor %}")
    siklga_ora(t, a1, a1, "{%tr for t in practicals %}", "{%tr endfor %}")
    siklga_ora(t, m1, m1, "{%tr for t in lectures %}", "{%tr endfor %}")

    _seminar_bolimini_qosh(t)


def _seminar_bolimini_qosh(t: Table) -> None:
    """Laboratoriya blokidan keyin M/A/L shaklida Seminar (S) bo'limini qo'shadi."""
    l_hdr = qatorni_top(t, "Laboratoriya mashg‘ulot (L)")
    l_endfor = qatorni_top(t, "{%tr endfor %}", bosh_qator=l_hdr)
    anchor = t.rows[l_endfor - 1]._tr

    for _ in range(4):
        clone = copy.deepcopy(anchor)
        anchor.addnext(clone)
        anchor = clone

    s_hdr, s_for, s_data, s_endfor = range(l_endfor + 1, l_endfor + 5)
    _teg_qatori_qil(t.rows[s_hdr - 1], "")
    katakka_yoz(t, s_hdr, 2, "Seminar (S)")
    katakka_yoz(t, s_hdr, 11, "{{ hours.seminar }}")
    _teg_qatori_qil(t.rows[s_for - 1], "{%tr for t in seminars %}")
    katakka_yoz(t, s_data, 1, "{{ t.code }}")
    katakka_yoz(t, s_data, 2, "{{ t.title }}")
    katakka_yoz(t, s_data, 11, "{{ t.hours }}")
    _teg_qatori_qil(t.rows[s_endfor - 1], "{%tr endfor %}")


def mustaqil_ishni_tahrirla(doc: Document) -> None:
    """6-bo'lim: 27 ta mustaqil ish topshirig'ini bitta siklga yig'adi."""
    t = doc.tables[1]
    hdr = qatorni_top(t, "Mustaqil ta’lim topshiriqlari")
    task1 = hdr + 1
    katakka_yoz(t, hdr, 11, "{{ hours.self_study }}")
    qatorlarni_ochir(t, task1 + 1, len(t.rows))  # 2-27-topshiriqlar
    katakka_yoz(t, task1, 1, "{{ loop.index }}")
    katakka_yoz(t, task1, 2, "{{ t.title }}")
    katakka_yoz(t, task1, 11, "{{ t.hours }}")
    siklga_ora(t, task1, task1, "{%tr for t in self_study_tasks %}", "{%tr endfor %}")


# --------------------------------------------------------------------------


def asosiy() -> int:
    if not MANBA.exists():
        print(f"xato: {MANBA} fayli topilmadi", file=sys.stderr)
        return 1

    doc = Document(MANBA)
    for step in (
        seminar_ustunini_qosh,
        muqovani_tahrirla,
        fan_malumotlarini_tahrirla,
        mazmunni_tahrirla,
        zarur_bilimlarni_tahrirla,
        natijalarni_tahrirla,
        mavzularni_tahrirla,
        mustaqil_ishni_tahrirla,
    ):
        step(doc)
        print(f"  {step.__name__}")

    SHABLON.parent.mkdir(parents=True, exist_ok=True)
    doc.save(SHABLON)
    print(f"\nyozildi: {SHABLON.relative_to(ILDIZ)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asosiy())
