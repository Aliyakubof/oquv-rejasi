---
name: database-optimizer
description: Ma'lumotlar bazasi va Django ORM ni optimallashtirish, N+1 muammolarini bartaraf etish, indekslash, tranzaksiyalar (atomic) va katta hajmdagi ma'lumotlarni qayta ishlash uchun ishlatiladi.
---

# Senior Database Architect & ORM Optimizer Skill

Ushbu skill ma'lumotlar bazasi (SQLite, PostgreSQL, MySQL) va ORM qatlamini yuqori unumdorlik, xavfsizlik va barqarorlik bilan ishlashini ta'minlaydi.

## Qachon ishlatiladi?
Foydalanuvchi ma'lumotlar bazasi modellarini yaratish, o'zgartirish, sekin ishlayotgan query-larni tahlil qilish, N+1 muammolarini yo'qotish yoki ommaviy ma'lumotlarni import qilishda foydalanadi.

---

## 1. ORM va Baza Unumdorligi Qoidalari

### 1. N+1 Query Muammosini To'liq Bartaraf Etish
- **ForeignKey va OneToOneField:** Har doim `.select_related('fk_field')` orqali bir so'rovda JOIN qilinadi.
- **ManyToManyField va Teskari bog'lanishlar:** `.prefetch_related('m2m_field')` orqali olinadi.
- **Qat'iy taqiq:** Template ichida sikl aylanayotganda `{{ object.related_model.name }}` chaqirib, har safar yangi DB so'rovi yuborish taqiqlanadi. View yoki QuerySet darajasida prefetch qilib o'tkazilsin.

### 2. Aqlli Indekslash (Indexing)
- Filtrlash (`filter()`), qidirish yoki saralashda (`order_by()`) ko'p ishlatiladigan ustunlarga `db_index=True` berilsin:
  ```python
  class Course(models.Model):
      code = models.CharField(max_length=50, db_index=True)
      status = models.CharField(max_length=20, db_index=True)
  ```
- Bir nechta ustun birga tekshirilsa, kompozit indeks qo'shilsin:
  ```python
  class Meta:
      indexes = [
          models.Index(fields=['department', 'status']),
      ]
  ```

### 3. Kerakli Ma'lumotnigina Yuklash (Projection)
- Agar butun model obyekti kerak bo'lmasa, barcha ustunlarni tortib olmaslik:
  - Faqat bir nechta maydon kerak bo'lsa: `.only('id', 'name')`
  - Katta matnli yoki faylli ustunlarni chetlab o'tish: `.defer('description')`
  - ID yoki ma'lum ro'yxat kerak bo'lsa: `.values_list('id', flat=True)`
- Baza ichida obyekt mavjudligini tekshirish uchun `.count() > 0` emas, `.exists()` ishlatish.

### 4. Tranzaksiya Xavfsizligi (Atomicity)
- Bir nechta jadvalga yozish, yangilash yoki import amallari mutlaqo `with transaction.atomic():` ichida bajarilishi shart:
  ```python
  from django.db import transaction

  with transaction.atomic():
      curriculum = Curriculum.objects.create(...)
      Course.objects.bulk_create(...)
  ```
  Agar biron xatolik yuz bersa, baza avtomatik *rollback* bo'ladi va chala ma'lumot qolmaydi.

### 5. Ommaviy Amallar (Bulk Operations)
- Katta hajmdagi ma'lumotlarni import qilishda Python siklida `.save()` chaqirmaslik:
  - Yangi yozuvlar uchun: `Model.objects.bulk_create(batch_list, batch_size=500)`
  - Yangilash uchun: `Model.objects.bulk_update(batch_list, fields=['field1', 'field2'], batch_size=500)`

### 6. Agregatsiya va Hisob-kitoblar Bazada Bo'lishi Shart
- Ma'lumotlarni xotirada emas, DB darajasida hisoblash:
  - `annotate(total=Sum('hours'), count=Count('courses'))`
  - `F()` ifodalari yordamida poyga holati (race condition) xavfisiz qiymatni oshirish:
    `Item.objects.filter(id=x).update(views=F('views') + 1)`

