---
name: code-reviewer
description: Senior darajadagi kod tahlili, Clean Code, Python/Django arxitekturasi, modullilik, type hintlar, xavfsizlik va refaktoring uchun ishlatiladi.
---

# Senior Code Reviewer Skill

Ushbu skill kod sifatini senior muhandis ko'zi bilan tahlil qilish, arxitekturani tekshirish va toza kod (Clean Code) standartlarini joriy qilish uchun mo'ljallangan.

## Qachon ishlatiladi?
Foydalanuvchi kodni tekshirish, review qilish, refaktor qilish, xatoliklarni topish yoki sifatini yaxshilashni so'raganda ushbu ko'rsatmalarga amal qilinadi.

---

## 1. Kod Sifati Standartlari (Checklist)

Kodni ko'rib chiqishda quyidagi 6 ta mezonga qat'iy e'tibor qaratiladi:

### 1. Arxitektura va Modullilik (Single Responsibility)
- Har bir modul faqat bitta aniq vazifani bajarsin.
- Bog'liqliklar (coupling) past bo'lishi shart: masalan, `parser` moduli Django applariga mutlaqo bog'lanmasligi, o'zi mustaqil ishlashi lozim.
- Biznes mantiq (business logic) `views.py` ichiga tiqilmasdan, alohida servislar (services) yoki modullarga ajratilishi kerak.

### 2. Qat'iy Tipizatsiya (Strict Type Hints)
- Python 3.10+ zamonaviy sintaksisidan foydalanilsin:
  - `list[str]`, `dict[str, int]`, `tuple[int, ...]`
  - `Optional[X]` o'rniga `X | None`
- Ochiq funksiyalarda `Any` ishlatish taqiqlanadi. Har bir parametr va qaytish qiymati (`-> bool`, `-> CourseData`) aniq ko'rsatiladi.
- Murakkab tuzilmalar uchun oddiy `dict` o'rniga `@dataclass(frozen=True)` yoki `TypedDict` ishlatilsin.

### 3. Funksiya Hajmi va O'qilishi
- Funksiya hajmi ~40 qatordan oshmasligi kerak. Oshsa, mantiqiy kichik yordamchi funksiyalarga bo'linadi.
- Nomlanish: O'zgaruvchi va funksiyalar nomlari qisqartmalarsiz, maqsadini yaqqol ifodalashi lozim (`fn_x` emas, `extract_curriculum_metadata`).
- Izohlar: "Kod nima qilyapti" degan izoh emas, "Nega bunday qilindi" degan sababni (edge-case, format injiqliklari) tushuntiruvchi qisqa izohlar yoziladi.

### 4. Xatolarni Qayta Ishlash (Fail-Fast & Error Handling)
- Hech qachon xatolarni yutib ketmaslik (`try: ... except Exception: pass` qat'iy man etiladi).
- Foydalanuvchiga va loglarga tushunarli bo'lgan maxsus exception sinflari yaratilsin (`CurriculumParseError`, `ValidationError`).
- Xato yuz berganda uning aniq qatori, sababi va noo'rin qiymati logda aks etishi kerak.

### 5. Formatlash va Linting
- Har qanday o'zgarish `ruff check --fix .` va `ruff format .` qoidalariga 100% mos kelishi shart.

---

## 2. Review Natijalarini Taqdim Etish Formati

Review berishda quyidagi aniq strukturadan foydalaning:
1. **Umumiy baho (Summary):** Kodning hozirgi holati va asosiy yutuqlari (1-2 gap).
2. **Kritik muammolar (Critical Issues):** Xavfsizlik, xotira yoki mantiqiy xatoliklar (agar bo'lsa).
3. **Yaxshilash tavsiyalari (Refactoring & Clean Code):** Tipizatsiya, o'qilishi va modullilik bo'yicha aniq takliflar.
4. **Tayyor yechim (Diff / Refactored Code):** To'liq to'g'rilangan, senior talablariga mos kod namunasi.

