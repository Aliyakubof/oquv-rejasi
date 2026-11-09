---
name: ui-ux-designer
description: Zamonaviy UI/UX yaratish, HTML/CSS, Tailwind, HTMX interaktivligi, Alpine.js reaktiv holatlari, animatsiyalar va foydalanuvchi qulayligini ta'minlash uchun ishlatiladi.
---

# Senior UI/UX Designer & Frontend Engineer Skill

Ushbu skill veb-interfeyslarni qulay (user-friendly), chiroyli, zamonaviy va silliq ishlaydigan qilish bo'yicha senior darajasidagi prinsiplarni o'z ichiga oladi.

## Qachon ishlatiladi?
Foydalanuvchi interfeys yaratish, template tahrirlash, sahifa dizaynini yaxshilash, HTMX yoki Alpine.js bilan ishlash, mobil moslashuvchanlik yoki animatsiyalar qo'shishni so'raganda ishlatiladi.

---

## 1. Asosiy Vizual Standartlar

### 1. Vizual Ierarxiya va Tipografika
- **Shriftlar:** Inter yoki zamonaviy sans-serif shriftlari.
- **Matn ierarxiyasi:**
  - Katta sarlavhalar: `text-2xl` / `text-3xl`, `font-bold` (700)
  - Bo'lim sarlavhalari: `text-lg` / `text-xl`, `font-semibold` (600)
  - Asosiy matn: `text-sm` / `text-base`, `font-normal` (400)
  - Yordamchi matn: `text-xs`, rang susaytirilgan (`text-muted`, kulrang)
- **Bo'shliqlar (Spacing Scale):** 4px, 8px, 12px, 16px, 24px, 32px. Elementlar bir-biriga yopishib qolmasligi lozim.

### 2. Komponent Holatlari (States)
Har bir interaktiv element (tugma, havola, input) quyidagi 5 ta holatga ega bo'lishi shart:
1. `Default`: Oddiy, toza ko'rinish.
2. `Hover`: Sichqoncha borganda yengil rang o'zgarishi yoki soya (`hover:bg-... transition`).
3. `Active`: Bosilganda kichrayish yoki chuqurlashish effekti (`active:scale-95`).
4. `Focus`: Klaviatura orqali boshqarilganda aniq ko'rinadigan kontur (`focus:ring-2 focus:outline-none`).
5. `Disabled`: Tugma o'chiqligida shaffoflik (`opacity-50 cursor-not-allowed`).

### 3. HTMX Yuklanish Holatlari (Loading States)
- Serverga so'rov yuborilganda foydalanuvchi ilova qotib qoldi deb o'ylamasligi kerak.
- Har doim `hx-indicator` yordamida yuklanish spinneri yoki skeletoni ko'rsatilsin:
  ```html
  <button hx-post="/api/save/" hx-indicator="#save-spinner" class="btn">
    Saqlash
    <span id="save-spinner" class="htmx-indicator spinner"></span>
  </button>
  ```
- Natijani almashtirishda (`hx-swap`) sakrashlar (layout shift) bo'lmasin.

### 4. Alpine.js Reaktivligi va Modal/Popoverlar
- Modal oynalar, popoverlar va dropdownlar silliq paydo bo'lishi kerak:
  ```html
  <div x-show="ochiq"
       x-transition:enter="transition ease-out duration-200"
       x-transition:enter-start="opacity-0 transform scale-95"
       x-transition:enter-end="opacity-100 transform scale-100"
       @keydown.escape.window="ochiq = false"
       @click.away="ochiq = false">
  ```
- Doimo `Esc` tugmasi bilan yopilish imkoniyatini ta'minlash.

### 5. Bo'sh Holatlar (Empty States)
Jadval yoki ro'yxat bo'sh bo'lganda hech qachon shunchaki bo'sh qora/oq joy qoldirilmasin:
- Tushunarli ikonka
- "Hozircha hech qanday ma'lumot yo'q" sarlavhasi
- Foydalanuvchini harakatga chaqiruvchi tugma ("Birinchi ma'lumotni qo'shish")

