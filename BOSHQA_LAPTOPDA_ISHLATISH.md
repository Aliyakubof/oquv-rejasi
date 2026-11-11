# O'quv Reja — Boshqa laptopda / kompyuterda ishga tushirish qo'llanmasi

Ushbu arxivda **O'quv rejalari va yuklamalari** tizimining to'liq kodi, shablonlari, statik resurslari, media fayllari, tayyor SQLite ma'lumotlar bazasi (`db.sqlite3`) hamda yangilangan boshlang'ich ma'lumotlar to'plami (`initial_data.json`) jamlangan.

---

## 1. Talablar
* **Python**: 3.10, 3.11, 3.12 yoki 3.13
* **OS**: Windows, macOS yoki Linux

---

## 2. Tezkor ishga tushirish (Yangi o'rnatish — SQLite bilan)

Arxiv ichida barcha migratsiyalar qo'llanilgan va tayyor ma'lumotlarga ega **`db.sqlite3`** bazasi mavjud. Shu sababli boshqa dasturchi hech qanday tashqi baza o'rnatmasdan darhol ishga tushira oladi:

### 1-qadam: Arxivni oching va loyiha papkasiga kiring
```bash
cd "Oquv rejasi"
```

### 2-qadam: Virtual muhit (venv) yarating va faollashtiring
**Windows (PowerShell / CMD):**
```powershell
python -m venv venv
venv\Scripts\activate
```

**Linux / macOS:**
```bash
python3 -m venv venv
source venv/bin/activate
```

### 3-qadam: Kutubxonalarni o'rnating
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4-qadam: Serverni ishga tushiring
```bash
python manage.py runserver
```

Brauzerda oching:
👉 **http://127.0.0.1:8000**

---

## 2.1. Mavjud loyihani yangilash (Agar loyiha kompyuterda oldindan bo'lsa)

Agar loyiha kompyuterda oldindan mavjud bo'lsa, eng so'nggi himoya qoidalari, CI fayllari, UI/UX modallari va barcha yangilanishlarni qabul qilish uchun o'z terminalida quyidagilarni bajaradi:

```bash
# 1. Asosiy tarmoqqa o'tish va so'nggi commitlarni tortib olish
git checkout main
git pull origin main

# 2. Bog'liqliklar va migratsiyalarni yangilash (tavsiya etiladi)
pip install -r requirements.txt
python manage.py migrate

# 3. Serverni ishga tushirish
python manage.py runserver
```

> [!TIP]
> Agar kompyuterda saqlanmagan lokal o'zgarishlar bo'lsa, `git pull` oldidan `git stash` qilib, pull qilingandan so'ng `git stash pop` qilish mumkin.

---

## 3. Foydalanuvchilar va Kirish

* Loyihada rollar tizimi mavjud (O'quv bo'limi / Office, Kafedra mudiri, O'qituvchi).
* Agar mavjud akkaunt parollarini bilmasangiz, yangi superuser yarating:
  ```bash
  python manage.py createsuperuser
  ```
* Yoki mavjud foydalanuvchining parolini yangilang:
  ```bash
  python manage.py changepassword <username>
  ```

---

## 4. PostgreSQL bilan ishlash (Ixtiyoriy / Production)

Agar PostgreSQL bazasida ishlamoqchi bo'lsangiz:

1. PostgreSQL da yangi baza yarating (masalan, `oquv_reja`).
2. `.env` faylini ochib, `DATABASE_URL` parametrini sozlang:
   ```env
   SECRET_KEY=thisissecretkeyfornow
   DEBUG=True
   ALLOWED_HOSTS=127.0.0.1,localhost
   CSRF_TRUSTED_ORIGINS=http://127.0.0.1:8000
   DATABASE_URL=postgres://POSTGRES_USER:POSTGRES_PAROL@localhost:5432/oquv_reja
   ```
3. Baza jadvallarini yarating:
   ```bash
   python manage.py migrate
   ```
4. Tayyor ma'lumotlarni bazaga yuklang:
   ```bash
   python manage.py loaddata initial_data.json
   ```

---

## 5. Loyiha tuzilishi va Asosiy modullar

* **`accounts/`** — Foydalanuvchilar, fakultetlar, kafedralar, o'qituvchilar va rollar boshqaruvi.
* **`plans/`** — O'quv rejalari, fanlar, soatlar, semestrovka, o'quv dasturlari va topshirish tarixi, audit tizimi (`audit.py`), eksport (`eksport.py`).
* **`parser/`** — O'quv reja Excel (`.xlsx`) fayllarini o'qish va tahlil qilish uchun mustaqil parser moduli.
* **`web/`** — Barcha UI shablonlari, HTMX/Alpine.js interfeyslari, office, kafedra, o'qituvchi kabinetlari, API va jonli qidiruv (`jonli.py`, `api.py`).
* **`docs/`** — PRD, o'quv reja xaritasi (`oquv_reja_map.md`), o'quv dasturi xaritasi (`oquv_dastur_map.md`) va texnik hujjatlar.
* **`scripts/`** — Shablon yaratish va yordamchi skriptlar.

---

## 6. Testlar va Kod sifati

Barcha testlarni ishga tushirish (270+ test mavjud, barchasi yashil):
```bash
python manage.py test
```

Kodni tekshirish va formatlash (Ruff):
```bash
ruff check .
ruff format .
```
