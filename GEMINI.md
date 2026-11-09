# GEMINI.md - Senior Engineering Guidelines

Ushbu loyiha ("O'quv-reja") uchun Antigravity agentining asosiy muhandislik qoidalari. Har qanday kod yozish, o'zgartirish yoki tekshirishda quyidagi senior darajasidagi talablarga amal qilinadi.

---

## 1. Javob berish uslubi (Communication & Response Style)
- **Qisqa va aniq:** Ortiqcha kirish, maqtov yoki takrorlarsiz to'g'ridan-to'g'ri yechim va tushuntirish beriladi.
- **Tahliliy yondashuv:** Faqat kod bermasdan, uning ishlash sababi, cheklovlari va potentsial muammolari (edge-case) ko'rsatiladi.
- **O'zbek tilida texnik aniqlik:** Dasturlash atamalarini tushunarli, aniq va savodli bayon qilish.

---

## 2. Senior Kod Sifati va Arxitektura (Python / Django)
- **Modullilik:** Yangi vazifa — yangi fayl yoki modul. `parser/` moduli Django-dan to'liq mustaqil bo'lishi shart.
- **Tipizatsiya:** Barcha ochiq funksiyalarda to'liq type hintlar (`X | None`, `list[...]`, `tuple[...]`). `Any` taqiqlanadi.
- **Ixchamlik:** Funksiyalar ~40 qatordan oshmasligi kerak.
- **Xatoliklar:** Parsing yoki ma'lumotlar bilan ishlashda xatoliklarni yutib ketmaslik (`try-except: pass` yo'q), aniq xatolik xabarlari bilan exception ko'tarish.
- **Linting:** Har qanday o'zgarishdan so'ng `ruff check .` va `ruff format .` qoidalariga bo'ysunish.

---

## 3. UI/UX Standartlari (HTML / HTMX / Alpine.js / CSS)
- **Vizual tartib:** Inter shrifti, mantiqiy spacing (4, 8, 12, 16, 24px) va aniq vizual ierarxiya.
- **Interaktivlik va holatlar:** Har bir tugma/elementda `hover`, `active`, `focus` va `disabled` holatlari bo'lishi shart.
- **HTMX yuklanish holatlari:** Serverga so'rov yuborilganda foydalanuvchiga `hx-indicator` orqali spinner yoki indikator ko'rsatish.
- **Bo'sh holatlar (Empty state):** Ma'lumot yo'q bo'lsa, xunuk bo'sh sahifa emas, chiroyli tushuntirish va qo'shish yo'li berilishi kerak.
- **Alpine.js:** Modal, popover va dinamik qidiruvlar silliq (`x-transition`) va qulay (`Esc` bilan yopiladigan) bo'lishi lozim.

---

## 4. Ma'lumotlar Bazasi va ORM Unumdorligi
- **N+1 Query man etiladi:** `select_related` (FK) va `prefetch_related` (M2M) dan foydalanish majburiy.
- **Indekslar:** Filtr yoki tartiblashda ko'p qatnashadigan maydonlarga indeks berish.
- **Tranzaksiyalar:** Bog'liq jadvallarga yozish yoki ommaviy importlarda `with transaction.atomic():` ishlatish.
- **Katta hajmdagi ma'lumotlar:** `.bulk_create()` va `.bulk_update()` ishlatish, Python siklida `.save()` chaqirmaslik.

---

## 5. Git Boshqaruvi
- **Format:** Conventional Commits (`feat:`, `fix:`, `refactor:`, `perf:`, `style:`, `chore:`).
- **Tozalik:** Commit qilishdan oldin faqat kerakli fayllar stajlanganini tekshirish. Hech qachon maxfiy kalitlar (`.env`), keshlar yoki virtual muhit fayllari tushmasligi kerak.

Batafsil yo'riqnoma: `.agents/skills/senior-engineer/SKILL.md`

