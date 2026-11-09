---
name: senior-engineer
description: Senior darajadagi kod review, zamonaviy UI/UX tajribasi, ma'lumotlar bazasi (ORM, query optimization, indekslash) va professional Git amaliyotlarini ta'minlovchi ekspert skill.
---

# Senior Full-Stack Engineer & Architect Skill

Ushbu skill Antigravity agentiga 4 ta asosiy ustun bo'yicha Senior darajasida ishlash qoidalarini yuklaydi:
1. **Senior Code Review & Clean Architecture**
2. **Modern UI/UX Engineering**
3. **Database Mastery & ORM Performance**
4. **Git Mastery & Version Control**

---

## 1. SENIOR CODE REVIEW & CLEAN CODE

Kodni ko'rib chiqish yoki yozishda faqat ishlaydigan kod emas, uzoq muddat xizmat qiladigan toza arxitektura talab qilinadi:

- **Arxitektura mustaqilligi:**
  - Bir modul — bitta javobgarlik (Single Responsibility).
  - Parser (`parser/`) mustaqil paket bo'lishi, Django app-lariga bog'lanmasligi kerak.
  - Hujjat generatsiyasi (Word/DOCX) alohida izolyatsiyalangan modulda bo'lsin.
- **Qat'iy Tipizatsiya (Strict Typing):**
  - Python 3.10+ zamonaviy sintaksisi: `tuple[...]`, `list[...]`, `dict[...]`.
  - `Optional[X]` o'rniga `X | None`.
  - Ochiq funksiyalarda `Any` ishlatilmaydi, parametr va qaytish qiymati qat'iy ko'rsatiladi.
  - Ma'lumotlar o'tkazishda xom (raw) tuple yoki dict o'rniga `dataclass` yoki TypedDict ishlatiladi.
- **Kichik va aniq funksiyalar:**
  - Har bir funksiya ~40 qatordan oshmasligi kerak. Oshsa — mantiqiy kichik funksiyalarga bo'linadi.
- **Xatolarni yutib yubormaslik (Fail-Fast):**
  - Parse yoki hisob-kitobda xatolik yuz bersa, uni `try-except: pass` bilan yashirma.
  - Aniq va tushunarli xabar beruvchi maxsus exceptionlarni chaqir (`raise ParsingError(...)`).
- **Format va Linting:**
  - Kod o'zgartirilgach doimo `ruff check --fix .` va `ruff format .` qoidalariga bo'ysunishi shart.

---

## 2. MODERN UI/UX ENGINEERING

Oddiy HTML emas, foydalanuvchiga zavq beradigan, qulay va tushunarli interfeys yaratish:

- **Visual Ierarxiya va Tipografika:**
  - Matn o'lchamlari va shrift vaznlari (Inter: 400, 500, 600, 700) orqali muhimlik darajasini ajratish.
  - Ranglar balansi: Kontrast yetarli, ko'zni charchatmaydigan fon va matn ranglari.
  - Standart spacing (padding/margin): 4px, 8px, 12px, 16px, 24px, 32px qoidasi.
- **Holatlar (Component States):**
  - Har bir interaktiv tugma/havola uchun: `default`, `hover`, `active`, `focus` (accessibility uchun outline) va `disabled`.
  - **Yuklanish holati (Loading state):** HTMX orqali serverga so'rov yuborilganda foydalanuvchi qotib qolmasligi uchun `hx-indicator` yordamida spinner yoki skeleton ko'rsatilsin.
- **Bo'sh holatlar (Empty States):**
  - Jadval yoki ro'yxatda ma'lumot bo'lmaganda shunchaki bo'sh qolmasdan, chiroyli ikonka va tushunarli yo'l-yo'riq ("Hozircha hech narsa yo'q, yangi qo'shish uchun...") chiqarilsin.
- **HTMX & Alpine.js uyg'unligi:**
  - Sahifani to'liq qayta yuklamasdan faqat o'zgargan blokni almashtirish (`hx-swap="outerHTML"` yoki `innerHTML`).
  - Dinamik qidiruv va filtrlashda serverga keraksiz so'rov yubormaslik (`hx-trigger="keyup changed delay:300ms"`).
  - Modal oynalar, popoverlar va dropdownlar Alpine.js (`x-data`, `x-show`, `x-transition`) orqali silliq ochilib-yopilishi kerak.
- **Responsive & Accessibility:**
  - Mobil, planshet va desktop ekranlarda buzilmaydigan tartib (Flexbox/Grid).
  - Modal ochilganda `Esc` tugmasi bilan yopilishi va fokus boshqaruvi.

---

## 3. DATABASE MASTERY & ORM PERFORMANCE

Ma'lumotlar bazasi tez, xavfsiz va to'g'ri ishlashi shart:

- **N+1 Query muammosini yo'qotish:**
  - ForeignKey va OneToOne bog'lanishlarida: `.select_related(...)`.
  - ManyToMany va teskari bog'lanishlarda: `.prefetch_related(...)`.
  - Hech qachon template ichida yoki for siklida alohida DB so'rovlarini chaqirmaslik.
- **Tezkor indekslash (Indexing):**
  - Qidiruv, `WHERE` filtrlarida yoki `ORDER BY` da ko'p ishlatiladigan maydonlarga `db_index=True` yoki `models.Index` qo'shish.
- **Optimal ma'lumot olish:**
  - Agar faqat 2-3 ta ustun kerak bo'lsa, butun modelni tortib olmasdan `.values()`, `.values_list(flat=True)` yoki `.only(...)` ishlatish.
  - Mavjudligini tekshirish uchun `.count() > 0` emas, `.exists()` ishlatish.
- **Tranzaksiyalar xavfsizligi (Atomicity):**
  - Bir nechta bog'liq modellarga yozish yoki ommaviy import amallarida `with transaction.atomic():` blokidan foydalanish (xatolik bo'lsa, baza yarim holatda qolib ketmasligi uchun).
- **Ommaviy amallar (Bulk operations):**
  - Sikl ichida bittalab `.save()` qilmaslik, buning o'rniga `bulk_create(..., batch_size=500)` va `bulk_update(...)` ishlatish.
- **Hisob-kitoblar DB darajasida:**
  - Yig'indi yoki sonlarni Python xotirasida sanamasdan, `Count()`, `Sum()`, `F()` ifodalari bilan bazaning o'zida hisoblash.

---

## 4. GIT MASTERY & VERSION CONTROL

Git bilan tartibli va xavfsiz ishlash madaniyati:

- **Conventional Commits qoidasi:**
  - `feat: yangi imkoniyat tavsifi`
  - `fix: xatolik tuzatildi`
  - `refactor: kod strukturasi yaxshilandi (mantiq o'zgarmadi)`
  - `perf: unumdorlik oshirildi`
  - `style: formatlash yoki dizayn o'zgarishi`
  - `docs: hujjatlashtirish`
  - `chore: yordamchi sozlamalar, kutubxonalar`
- **Atomik commitlar:**
  - Bir commitda bitta mantiqiy ish bajarilsin. Masalan, "baza migratsiyasi + UI tugmasi rangi + parser refaktori" bir commitga aralashtirilmaydi.
- **Commitdan oldingi tekshiruv (Pre-commit hygiene):**
  - Har doim `git status` va `git diff` qilib ortiqcha fayllar, print() yoki debug qoldiqlar yo'qligiga ishonch hosil qilish.
  - Fayllarni `ruff format .` dan o'tkazish.
- **Maxfiylik va tozalik:**
  - Hech qachon `.env`, maxfiy parollar, tokenlar, virtual muhit (`venv/`, `env/`) yoki vaqtinchalik SQLite fayllar Gitga qo'shilmasligi kerak.

