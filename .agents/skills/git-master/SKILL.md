---
name: git-master
description: Professional Git amaliyotlari, Conventional Commits, toza git diff tahlili, atomik commitlar va xavfsiz versiyalash uchun ishlatiladi.
---

# Senior Git Workflow & Version Control Master Skill

Ushbu skill Git versiyalar boshqaruvida xatoliklarning oldini olish, toza commit tarixi yaratish va professional jamoaviy standartlarni ta'minlash uchun xizmat qiladi.

## Qachon ishlatiladi?
Foydalanuvchi commit qilish, git buyruqlari, diff tahlili, branch ochish, ziddiyatlarni (merge conflicts) hal qilish yoki o'zgarishlarni tekshirishni so'raganda ishlatiladi.

---

## 1. Professional Git Standartlari

### 1. Conventional Commits Standarti
Barcha commitlar quyidagi formatda bo'lishi shart:
```text
<tur>(<soha>): <qisqa va aniq sarlavha>

[ixtiyoriy mantiqiy tushuntirish: nima o'zgardi va nima uchun]
```

**Asosiy turlar:**
- `feat`: Yangi funksionallik (masalan: `feat(parser): add excel curriculum header validator`)
- `fix`: Xatolikni tuzatish (masalan: `fix(db): resolve N+1 query on curriculum list page`)
- `refactor`: Kod strukturasi yaxshilandi, ammo xatti-harakati o'zgarmadi
- `perf`: Tezlik va unumdorlik oshirildi
- `style`: Faqat formatlash, bo'sh joylar yoki CSS dizayn o'zgarishi
- `docs`: Hujjatlar (README, PRD, docs) yangilandi
- `test`: Yangi testlar qo'shildi yoki mavjudlari to'g'rilandi
- `chore`: Kutubxonalar, build yoki yordamchi konfiguratsiyalar

### 2. Atomik Commit Qoidasi (One Logical Change per Commit)
- Hech qachon bir vaqtning o'zida "baza migratsiyasi", "login sahifasi dizayni" va "parser refaktori" bitta commitga aralashtirilmaydi.
- Har bir commit mustaqil, orqaga qaytarish (revert) oson bo'ladigan holatda bo'lishi lozim.

### 3. Commit Oldi Gigiyenasi (Pre-commit Checklist)
Foydalanuvchiga commit taklif qilishdan oldin:
1. `git status` — faqat kerakli fayllar stajlanganmi?
2. `git diff --cached` — kodda ortiqcha `print()`, `console.log()` yoki vaqtinchalik debug qoldiqlari yo'qligiga ishonch hosil qilish.
3. Linting: `ruff check .` va `ruff format .` dan xatosiz o'tgan bo'lishi.

### 4. Xavfsizlik va Maxfiylik (Strict Security)
Quyidagi fayllar **hech qachon** Gitga qo'shilmasligi va `.gitignore` da bo'lishi shart:
- `.env`, `.env.local` (API kalitlar, SECRET_KEY, parollar)
- Virtual muhit papkalari (`venv/`, `env/`, `.venv/`)
- SQLite vaqtinchalik fayllari yoki real shaxsiy ma'lumotlar bazasi (`*.sqlite3` ishlab chiqishda lokal bo'lsa)
- Kesh va vaqtinchalik kataloglar (`__pycache__/`, `.ruff_cache/`)

