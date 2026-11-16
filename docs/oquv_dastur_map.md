# O'quv Dastur (Course Syllabus) DOCX Map

Structural reference for generating and pre-filling the O'quv Dastur `.docx` document. Based on analysis of a real document (`Kiberxavfsizlik_asoslari_fan_dasturi_ATDT.docx`).

The platform **generates** this document with course metadata pre-filled. Teachers fill in the content sections (topics, descriptions, references). This map defines what to pre-fill and what to leave empty.

`plans/dastur/oquv_dastur.docx` is a hand-editable Word file, not code-generated. It was produced once by `scripts/make_dastur_template.py`, which opens
`sources/Kiberxavfsizlik_asoslari_fan_dasturi_ATDT.docx` (a real, fully populated dastur) read-only, swaps concrete values for docxtpl Jinja tags, and
collapses repeating rows into `{%tr for %}` loops — keeping every border, merge, and font byte-for-byte. The one structural addition over the reference
document itself is a fourth hour column, **Seminar** (`seminar_ustunini_qosh()`, run before any other edit) — the reference document only has
Ma'ruza/Amaliy/Lab-ya, but `FanVariant.seminar_soat` is a real, independent hours field, so the template needs its own column and section-5 loop for it
(see §3, §5, §9). Re-run the script only if the university reissues the reference form; otherwise edit `plans/dastur/oquv_dastur.docx` directly in Word
(reword a heading, adjust a border) the same way any other document is edited. At runtime, `plans/dastur/service.py::dastur_render()` renders that
template via `docxtpl.DocxTemplate`, using the context built by `plans/dastur/kontekst.py::dastur_kontekst()`, then
`plans/dastur/soat_ustunlari.py::soat_ustunlarini_tozala()` cuts out the hour columns and section-5 sub-headers a course has no hours for (docxtpl can't
remove a table column, so this is post-render OOXML surgery).

---

## 1. Document Structure Overview

The document has three top-level regions:

```
┌──────────────────────────────────────────────┐
│  COVER PAGE                                  │  Paragraphs + 1 small table
│  Title, approval block, field codes          │
├──────────────────────────────────────────────┤
│  MAIN TABLE                                  │  1 large table (~98 rows)
│  Sections 1–6: course info, lessons, tasks   │
├──────────────────────────────────────────────┤
│  FOOTER TABLE                                │  1 table (~24 rows)
│  Sections 7–10: methods, grading, references │
└──────────────────────────────────────────────┘
```

In the DOCX XML, the body contains:
- ~24 paragraphs (cover page text)
- Table 1: approval stamp (1 row, skip)
- Table 2: main content (sections 1–6, ~98 rows)
- Table 3: footer content (sections 7–10, ~24 rows)

---

## 2. Cover Page (Paragraphs)

The whole document — cover page included — is the reference file itself,
edited in place by `scripts/make_dastur_template.py`. Nothing is trimmed or
reloaded from a separate source at build time, so the page setup, fonts, and
borders are exactly the reference document's: **US Letter** (12240×15840
twips), not A4.

These are standalone paragraphs before the main table. The platform pre-fills all of them.

| Order | Content | Pre-fill source | Example |
|---|---|---|---|
| 1 | University name | Hardcoded | `TURAN INTERNATIONAL UNIVERSITY` |
| 2 | *(approval table — skip)* | | |
| 3 | **Course title** (bold, centered) | O'quv Reja → course title | `KIBERXAVFSIZLIK ASOSLARI` |
| 4 | "FANINING O'QUV DASTURI" | Hardcoded | |
| 5 | Study format label | O'quv Reja → ta'lim shakli | `(kunduzgi ta'lim uchun)` |
| 6 | **Bilim sohasi** with code | DB lookup from major code | `600000 – Axborot-kommunikatsiya texnologiyalari` |
| 7 | **Ta'lim sohasi** with code | DB lookup from major code | `610000 – Axborot-kommunikatsiya texnologiyalari` |
| 8 | **Ta'lim yo'nalishi** with code | O'quv Reja → major code + title | `60610800 – Axborot texnologiyalarining dasturiy ta'minoti` |
| 9 | City and year | Hardcoded / config | `Namangan – 2026` |
| 10 | Department attribution | Platform → department name | `Mazkur o'quv dasturi ... kafedrasi tomonidan taqdim etilgan` |
| 11 | Author (Tuzuvchi) | **Teacher fills** | |
| 12 | Reviewers (Taqrizchilar) | **Teacher fills** | |

---

## 3. Main Table — Section 1: Fan ma'lumotlari (Course Info)

This is the core metadata table the platform pre-fills entirely. It occupies rows 0–6 of the main table.

### Row layout:

```
Row 0:  "1."  |  "Fan ma'lumotlari"
        ──────┼─────────────────────────────────────────────────────────
Row 1:  Fan/modul kodi     │ O'quv yili      │ Semestr    │ ECTS-Kreditlar
        {course_code}      │ {academic_year}  │ {semester} │ {credits}
        ──────┼─────────────────────────────────────────────────────────
Row 2:  Fan/modul turi     │ Ta'lim tili      │ Tartib raqami    │ Haftadagi soatlari
        {Majburiy/Tanlov}  │ {O'zbek}         │ {code – order}   │ {weekly_hours}
        ──────┼─────────────────────────────────────────────────────────
Row 3:  Fanning nomi       │ Jami yuklama     │ Auditoriya jami – {N} soat   │ Mustaqil  │ Kurs ishi
        {course_title}     │ (soat)           │ shundan:                     │ ta'lim    │
        ──────┼             ┼──────────────────┼──────────────────────────────┼           │
Row 4:  (merged↑)          │ (merged↑)        │ Ma'ruza │ Amaliy │ Lab-ya │ Seminar │ (merged↑) │ (merged↑)
        ──────┼─────────────┼──────────────────┼─────────┼────────┼────────┼─────────┼───────────┼──────────
Row 5:  (empty, span=3)    │ {total_hrs}      │{lec_hrs}│{pra_hr}│{lab_hrs}│{sem_hrs}│{indep_hrs}│ {- or KI}
```

### Pre-fill field mapping:

| Cell | Label | Source | Notes |
|---|---|---|---|
| R1.C0 | Fan/modul kodi | O'quv Reja → course code | e.g., `KIBAS1906` |
| R1.C1 | O'quv yili | O'quv Reja → academic year | e.g., `2026-2027`. If multi-year, comma-separated. |
| R1.C2 | Semestr | O'quv Reja → semester number(s) | e.g., `7`. If multi-semester, comma-separated. |
| R1.C3 | ECTS - Kreditlar | O'quv Reja → credits for this semester | Per-semester credits, not total. |
| R2.C0 | Fan/modul turi | Derived from section | `Majburiy` or `Tanlov` |
| R2.C1 | Ta'lim tili | Hardcoded | `O'zbek`, from `TALIM_TILI` in `plans/dastur/kontekst.py` — no model field records the language of instruction |
| R2.C2 | O'quv rejadagi tartib raqami | O'quv Reja → major code + order number | e.g., `60610100 – 1.19`, joined by `_kod_bilan()` (spaced en-dash), same helper as the soha/yonalish cover-page lines |
| R2.C3 | Haftadagi dars soatlari | O'quv Reja → weekly hours for this semester | e.g., `6` |
| R3.C0 | Fanning nomi | O'quv Reja → course title | Spans 3 grid columns, merged vertically with R4–R5 |
| R3.C1 | Jami yuklama (soat) | Label only | Value goes in R5 |
| R3.C2 | Auditoriya mashg'ulotlari jami | Computed | `Auditoriya mashg'ulotlari jami – {N} soat, shundan:` |
| R4.C2–C5 | Ma'ruza / Amaliy / Lab-ya / Seminar | Labels | Only include columns for hour types that exist (>0) |
| R5.C1 | Total hours value | O'quv Reja → total hours | e.g., `180` |
| R5.C2 | Lecture hours | O'quv Reja → ma'ruza hours | e.g., `24` |
| R5.C3 | Practice hours | O'quv Reja → amaliy hours | e.g., `24` |
| R5.C4 | Lab hours | O'quv Reja → lab hours | e.g., `24`. Omit column if 0. |
| R5.C5 | Seminar hours | O'quv Reja → seminar hours | e.g., `8`. Omit column if 0. |
| R5.C6 | Independent study hours | O'quv Reja → mustaqil ta'lim | e.g., `108` |
| R5.C7 | Course project | O'quv Reja → kurs ishi | `-` if none, `Kurs ishi` if present |

> **Note on the hour columns:** the template has **four** hour-type columns — `Ma'ruza`, `Amaliy`, `Lab-ya`, `Seminar` — even though the reference document itself only has the first three; `Seminar` was added at build time by `scripts/make_dastur_template.py::seminar_ustunini_qosh()`, since `FanVariant.seminar_soat` is a real, independent hours field distinct from `laboratoriya_soat` and a course can have both non-zero at once (both must then render side by side). A column is dropped entirely (not just shown as `-`) when that hour type is zero, implemented as post-render OOXML surgery in `plans/dastur/soat_ustunlari.py::soat_ustunlarini_tozala()`, since docxtpl can only substitute tags, not remove table columns. The freed width is spread evenly across the surviving hour columns so the table stays full width. If all four are zero, nothing is deleted — removing all four would leave the "Auditoriya" header cell spanning zero grid columns, which is invalid OOXML.

---

## 4. Main Table — Sections 2–4 (Teacher-Filled)

These sections are **not pre-filled** by the platform. The teacher writes the content.

| Section | Row | Title | Content |
|---|---|---|---|
| **2** | R7 | Fanning mazmuni | Course purpose and objectives (free text) |
| **3** | R10 | Boshlang'ich bilimlar | Prerequisite courses (teacher lists them) |
| **4** | R15 | Ta'lim natijalari (TN) | Learning outcomes: TN1, TN2, ... (teacher writes) |

The platform generates these section headers with empty content rows.

---

## 5. Main Table — Section 5: Fan mazmuni va mashg'ulotlar (Lesson Tables)

This is the largest section. The platform **pre-generates the row structure** — the correct number of empty rows per hour type. The teacher fills in the topic descriptions.

### Structure:

```
Row N+0:  "5."  |  "Fan mazmuni va mashg'ulotlar shakli:"  |  "Soat"

Row N+1:  ""    |  "Ma'ruza (M)"                           |  {total_lecture_hours}
Row N+2:  "M1"  |  {empty — teacher fills}                 |  2
Row N+3:  "M2"  |  {empty}                                 |  2
  ...           (one row per lesson: total = lecture_hours / 2)

Row M+0:  ""    |  "Amaliy mashg'ulot (A)"                 |  {total_practice_hours}
Row M+1:  "A1"  |  {empty}                                 |  2
Row M+2:  "A2"  |  {empty}                                 |  2
  ...           (one row per lesson: total = practice_hours / 2)

Row L+0:  ""    |  "Laboratoriya mashg'ulot (L)"           |  {total_lab_hours}
Row L+1:  "L1"  |  {empty}                                 |  2
  ...           (one row per lesson: total = lab_hours / 2)

Row S+0:  ""    |  "Seminar (S)"                           |  {total_seminar_hours}
Row S+1:  "S1"  |  {empty}                                 |  2
  ...           (one row per lesson: total = seminar_hours / 2)
```

Sub-sections always appear in this order — Ma'ruza, Amaliy, Laboratoriya, Seminar — regardless of which hour types a given course actually has.

### Pre-fill rules:

| What | Value | Source |
|---|---|---|
| Sub-section headers | `Ma'ruza (M)`, `Amaliy mashg'ulot (A)`, `Laboratoriya mashg'ulot (L)`, `Seminar (S)` | Static text, already in the template |
| Total hours per sub-section | The number in the last column of the header row | O'quv Reja |
| Number of lesson rows | `hours / 2` per type | Computed by `bosh_mavzular()` |
| Row labels | `M1`, `M2`, ..., `A1`, `A2`, ..., `L1`, `L2`, ..., `S1`, `S2`, ... | Sequential |
| Hours per lesson | Always `2` | Hardcoded |
| Topic/description cell | **Empty** | Teacher fills |

**Only include sub-sections for hour types that have non-zero hours.** If a course has no lab hours, `soat_ustunlarini_tozala()` removes the
Laboratoriya sub-header row entirely at render time — it sits outside its `{%tr for%}` loop, so an empty `labs` list alone would leave the header
behind with a bare `-`. Same rule applies independently to each of the four types, so a course with lab hours but no seminar hours (or vice versa)
keeps one sub-section and drops the other.

---

## 6. Main Table — Section 6: Mustaqil ta'lim (Independent Study)

Same pattern as Section 5 but for independent study tasks.

```
Row:  "6."  |  "Mustaqil ta'lim topshiriqlari*"  |  {total_independent_hours}
Row:  "1"   |  {empty — teacher fills}            |  {hours_per_task}
Row:  "2"   |  {empty}                            |  {hours_per_task}
  ...
```

### Pre-fill rules:

| What | Value |
|---|---|
| Total hours | From O'quv Reja → mustaqil ta'lim |
| Number of rows | `independent_hours / hours_per_task` |
| Hours per task | Typically `4` (observed), but may need to be configurable |
| Row labels | `1`, `2`, `3`, ... (plain numbers, not prefixed) |
| Description cells | **Empty** — teacher fills |

---

## 7. Footer Table — Sections 7–10 (Teacher-Filled)

A separate table after the main table. The platform generates the section headers only. All content is teacher-filled.

| Section | Title | Content |
|---|---|---|
| **7** | Ta'lim texnologiyalari va metodlari | Teaching methods (free text) |
| **8** | Talabalar tomonidan kreditlarni olish uchun talablar | Credit requirements (free text) |
| **9** | Talabalar bilimini baholash mezoni | Grading criteria (free text) |
| **10** | Foydalanilgan adabiyotlar | References — sub-sections: Asosiy adabiyotlar, Qo'shimcha adabiyotlar, Axborot manbalari |

---

## 8. Generation Summary

What the platform generates vs. what the teacher fills:

```
PLATFORM PRE-FILLS:                      TEACHER FILLS:
─────────────────                        ─────────────
Cover page:                              Cover page:
  ✓ University name                        ✗ Author (Tuzuvchi)
  ✓ Course title                           ✗ Reviewers (Taqrizchilar)
  ✓ Study format label
  ✓ Bilim sohasi + code                  Section 2: Course description
  ✓ Ta'lim sohasi + code                 Section 3: Prerequisites
  ✓ Ta'lim yo'nalishi + code             Section 4: Learning outcomes (TN1–TNx)
  ✓ City + year
  ✓ Department attribution               Section 5: Lesson topics
                                            (rows are pre-created, content empty)
Section 1: Full course info table
  ✓ Course code                           Section 6: Independent study tasks
  ✓ Academic year                           (rows are pre-created, content empty)
  ✓ Semester
  ✓ Credits                               Section 7: Teaching methods
  ✓ Course type (Majburiy/Tanlov)         Section 8: Credit requirements
  ✓ Order number                          Section 9: Grading criteria
  ✓ Weekly hours                          Section 10: References
  ✓ Course title
  ✓ Hours breakdown
  ✓ Kurs ishi indicator

Section 5: Lesson table structure
  ✓ Sub-section headers + totals
  ✓ Row labels (M1, A1, L1...)
  ✓ "2" in hours column

Section 6: Independent study structure
  ✓ Row count + labels
  ✓ Hours per task
```

---

## 9. Conditional Sections

The document structure adapts to the course:

| Condition | Effect |
|---|---|
| No lecture hours | Section 1's Ma'ruza column and Section 5's `Ma'ruza (M)` sub-header row are both removed |
| No practice hours | Section 1's Amaliy column and Section 5's `Amaliy mashg'ulot (A)` sub-header row are both removed |
| No lab hours | Section 1's Lab-ya column and Section 5's `Laboratoriya mashg'ulot (L)` sub-header row are both removed |
| No seminar hours | Section 1's Seminar column and Section 5's `Seminar (S)` sub-header row are both removed |
| Lab and Seminar both non-zero | Both columns render side by side — they're independent fields (`laboratoriya_soat` / `seminar_soat`), not alternatives |
| All four hour types zero | Nothing is removed — deleting all four would leave the "Auditoriya" header cell spanning zero grid columns |
| No course project | Row 5 last cell = `-` instead of `Kurs ishi` |
| Multi-semester course | Comma-separated semesters and years in Section 1 |