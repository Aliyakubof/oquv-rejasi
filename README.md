# O'quv Reja va Yuklamalari Tizimi

Oliy ta'lim muassasalarida o'quv rejalari, soat taqsimoti, fanlar, kafedralar yuklamalari va o'quv dasturlarini boshqarish platformasi.

Boshqa kompyuter yoki laptopda ishga tushirish uchun to'liq yo'riqnoma: [BOSHQA_LAPTOPDA_ISHLATISH.md](BOSHQA_LAPTOPDA_ISHLATISH.md)

## Tezkor ishga tushirish:
```bash
python -m venv venv
venv\Scripts\activate   # Linux/macOS: source venv/bin/activate
pip install -r requirements.txt
python manage.py runserver
```

## Mavjud loyihani yangilash:
```bash
git checkout main
git pull origin main
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```
Brauzerda: http://127.0.0.1:8000
