"""End-to-end web view tests for security, alerts, copy, exports & pagination."""

from io import BytesIO
from zipfile import ZipFile

from django.conf import settings
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from docx import Document
from openpyxl import Workbook, load_workbook

from accounts.models import Department, OqituvchiTuri
from plans import dashboard
from plans.models import (
    AuditAmali,
    AuditYozuvi,
    Bildirishnoma,
    FanTuri,
    KafedraTasdiqHolati,
    KafedraYuklamaTasdiq,
    SoatTuri,
    TalimYonalishi,
    Yuklama,
)
from plans.tests.factories import (
    make_fan,
    make_fan_semestr,
    make_oqituvchi,
    make_reja,
    make_yonalish,
)
from web.tests.helpers import (
    PAROL,
    foydalanuvchi_yarat,
    login,
    mudir_yarat,
    office_admin_yarat,
    oqituvchi_yarat,
)


def _xlsx_upload(nomi: str, qatorlar: list[list[object]]) -> SimpleUploadedFile:
    wb = Workbook()
    ws = wb.active
    for q in qatorlar:
        ws.append(q)
    buf = BytesIO()
    wb.save(buf)
    return SimpleUploadedFile(
        nomi,
        buf.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


class HealthVaXavfsizlikWebTests(TestCase):
    def setUp(self) -> None:
        cache.clear()

    def tearDown(self) -> None:
        cache.clear()

    def test_health_endpoint_ok_qaytaradi(self) -> None:
        javob = self.client.get("/health/")
        self.assertEqual(javob.status_code, 200)
        self.assertEqual(javob.json()["status"], "ok")

    @override_settings(LOGIN_MAX_URINISH=3, LOGIN_BLOK_SONIYA=300)
    def test_kirish_brute_force_429_bilan_bloklanadi(self) -> None:
        user = oqituvchi_yarat()
        for _ in range(3):
            r = self.client.post(
                reverse("kirish"),
                {"username": user.telefon, "password": "xato"},
            )
            self.assertEqual(r.status_code, 200)
        blok = self.client.post(
            reverse("kirish"),
            {"username": user.telefon, "password": "xato"},
        )
        self.assertEqual(blok.status_code, 429)
        self.assertContains(
            blok, "Juda ko&#x27;p noto&#x27;g&#x27;ri urinish", status_code=429
        )

    def test_vaqtinchalik_parol_va_majburiy_ozgartirish_middleware(self) -> None:
        admin = office_admin_yarat()
        oqit = make_oqituvchi()
        super_user = foydalanuvchi_yarat("SUPERADMIN")
        prof_super = make_oqituvchi(kafedra=oqit.kafedra)
        prof_super.foydalanuvchi.rol = "SUPERADMIN"
        prof_super.foydalanuvchi.save(update_fields=["rol"])

        login(self.client, admin)
        forbid = self.client.post(
            reverse("office:oqituvchi_vaqtinchalik_parol", args=[prof_super.pk]),
            follow=True,
        )
        self.assertContains(forbid, "ruxsat yo&#x27;q")

        ok = self.client.post(
            reverse("office:oqituvchi_vaqtinchalik_parol", args=[oqit.pk]),
            follow=True,
        )
        self.assertEqual(ok.status_code, 200)
        self.assertContains(ok, "Bir martalik vaqtinchalik parol yaratildi")
        oqit.foydalanuvchi.refresh_from_db()
        self.assertTrue(oqit.foydalanuvchi.parol_ozgartirish_kerak)

        # Majburiy parol almashtirish middleware GET va HTMX ni /parol/ ga yo'naltiradi
        client2 = self.client_class()
        login(client2, oqit.foydalanuvchi)
        r_get = client2.get(reverse("men:yuklamalar"))
        self.assertRedirects(r_get, reverse("parol_ozgartirish"))

        r_htmx = client2.get(reverse("men:yuklamalar"), HTTP_HX_REQUEST="true")
        self.assertEqual(r_htmx.status_code, 401)
        self.assertEqual(r_htmx["HX-Redirect"], reverse("parol_ozgartirish"))

        r_health = client2.get("/health/")
        self.assertEqual(r_health.status_code, 200)

        # Superadmin parolini tiklab bo'lmaydi; almashtirilgach sahifa ochiladi
        self.assertTrue(bool(super_user.pk))
        oqit.foydalanuvchi.parol_ozgartirish_kerak = False
        oqit.foydalanuvchi.save(update_fields=["parol_ozgartirish_kerak"])
        self.assertEqual(client2.get(reverse("men:yuklamalar")).status_code, 200)

    def test_yonalish_ochirish_reja_bogliq_bolsa_rad_etiladi(self) -> None:
        login(self.client, office_admin_yarat())
        y_band = make_yonalish(kodi="60611111")
        make_reja(yonalish_kodi="60611111")
        r_rad = self.client.post(
            reverse("office:yonalish_ochirish", args=[y_band.pk]),
            follow=True,
        )
        self.assertContains(r_rad, "o&#x27;quv rejalar mavjud")
        self.assertTrue(TalimYonalishi.objects.filter(pk=y_band.pk).exists())

        y_bosh = make_yonalish(kodi="60612222")
        self.client.post(reverse("office:yonalish_ochirish", args=[y_bosh.pk]))
        self.assertFalse(TalimYonalishi.objects.filter(pk=y_bosh.pk).exists())
        self.assertTrue(AuditYozuvi.objects.filter(amal=AuditAmali.OCHIRILDI).exists())


class BildirishnomaWebTests(TestCase):
    def test_kafedra_va_ofis_jarayonlarida_bildirishnoma_yaratiladi(self) -> None:
        yil = dashboard.joriy_akademik_yil()
        kaf = Department.objects.create(nomi="Kompyuter injiniringi")
        admin = office_admin_yarat()
        mudir = mudir_yarat(kafedra=kaf)
        reja = make_reja(boshlanish_yili=yil)
        fan = make_fan(reja, kafedra=kaf)
        make_fan_semestr(fan.tanlangan_variant, semestr=1)

        with self.captureOnCommitCallbacks(execute=True):
            login(self.client, mudir)
            self.client.post(
                reverse("kafedra:tasdiqqa_yuborish"),
                {"yil": yil, "izoh": "Tayyor"},
            )
        self.assertTrue(
            Bildirishnoma.objects.filter(qabul_qiluvchi=admin, oqilgan=False).exists()
        )

        with self.captureOnCommitCallbacks(execute=True):
            login(self.client, admin)
            self.client.post(
                reverse("office:kafedra_tasdiqlash", args=[kaf.pk]),
                {"yil": yil},
            )
        xabar = Bildirishnoma.objects.filter(qabul_qiluvchi=mudir).first()
        self.assertIsNotNone(xabar)

        # IDOR himoyasi: boshqa foydalanuvchi o'qiy olmaydi
        r_idor = self.client.post(reverse("bildirishnoma_oqish", args=[xabar.pk]))
        self.assertEqual(r_idor.status_code, 404)

        login(self.client, mudir)
        r_list = self.client.get(reverse("bildirishnoma_list"))
        self.assertContains(r_list, xabar.sarlavha)
        self.client.post(reverse("bildirishnoma_barchasi_oqildi"))
        xabar.refresh_from_db()
        self.assertTrue(xabar.oqilgan)

    def test_telegram_chat_id_saqlash_parol_sahifasida(self) -> None:
        user = oqituvchi_yarat()
        login(self.client, user)
        r = self.client.post(
            reverse("profil_telegram_saqlash"),
            {"telegram_chat_id": " 987654321 "},
            follow=True,
        )
        self.assertEqual(r.status_code, 200)
        user.refresh_from_db()
        self.assertEqual(user.telegram_chat_id, "987654321")
        self.assertEqual(PAROL, "test-parol-123")


class NusxalashVaEksportWebTests(TestCase):
    def test_nusxalash_va_svod_va_docx_zip_ishlaydi(self) -> None:
        joriy = dashboard.joriy_akademik_yil()
        otgan = joriy - 1
        kaf1 = Department.objects.create(nomi="AX")
        kaf2 = Department.objects.create(nomi="DI")
        admin = office_admin_yarat()
        mudir1 = mudir_yarat(kafedra=kaf1)
        oqit1 = make_oqituvchi(kafedra=kaf1)
        oqit2 = make_oqituvchi(kafedra=kaf2)

        r_otgan = make_reja(
            boshlanish_yili=otgan, yonalish_kodi="60610100", guruhlar_soni=1
        )
        r_otgan.guruhlar.create(raqam=1, nomi="DI-25-1")
        f_otgan = make_fan(
            r_otgan, raqam="1.01", turi=FanTuri.TANLOV, kafedra=kaf1, nomi="Algoritmlar"
        )
        v_o = f_otgan.variantlar.first()
        f_otgan.tanlangan_variant = v_o
        f_otgan.save(update_fields=["tanlangan_variant"])
        fs_o = make_fan_semestr(v_o, semestr=1)
        Yuklama.objects.create(fan_semestr=fs_o, tur=SoatTuri.MARUZA, oqituvchi=oqit1)

        r_joriy = make_reja(
            boshlanish_yili=joriy, yonalish_kodi="60610100", guruhlar_soni=1
        )
        r_joriy.guruhlar.create(raqam=1, nomi="DI-26-1")
        f_joriy = make_fan(
            r_joriy, raqam="1.01", turi=FanTuri.TANLOV, nomi="Algoritmlar"
        )
        make_fan_semestr(f_joriy.variantlar.first(), semestr=1)

        login(self.client, admin)
        dash = self.client.get(reverse("office:dashboard"), {"yil": joriy})
        self.assertContains(dash, f"{otgan}/{otgan + 1} dan ko'chirish")
        self.assertNotIn(otgan, dash.context["yillar"])

        self.client.post(
            reverse("office:taqsimot_nusxalash"),
            {"yil": joriy, "manba_yil": otgan},
        )
        f_joriy.refresh_from_db()
        self.assertEqual(f_joriy.tanlangan_variant.kafedra_id, kaf1.pk)

        login(self.client, mudir1)
        self.client.post(
            reverse("kafedra:taqsimot_nusxalash"),
            {"yil": joriy, "manba_yil": otgan},
        )
        self.assertEqual(Yuklama.objects.akademik_yilda(joriy).count(), 1)

        # Kafedra boshqa kafedraning docx varaqasiga kira olmaydi
        r_idor = self.client.get(
            reverse("kafedra:oqituvchi_shakl1_docx", args=[oqit2.pk]), {"yil": joriy}
        )
        self.assertEqual(r_idor.status_code, 404)

        r_kaf_docx = self.client.get(
            reverse("kafedra:oqituvchi_shakl1_docx", args=[oqit1.pk]), {"yil": joriy}
        )
        self.assertEqual(r_kaf_docx.status_code, 200)
        doc = Document(BytesIO(b"".join(r_kaf_docx.streaming_content)))
        self.assertIn("1-SHAKL", "\n".join(p.text for p in doc.paragraphs))

        r_kaf_zip = self.client.get(reverse("kafedra:hisobot_zip"), {"yil": joriy})
        with ZipFile(BytesIO(b"".join(r_kaf_zip.streaming_content))) as zf:
            self.assertEqual(len(zf.namelist()), 2)

        login(self.client, oqit1.foydalanuvchi)
        r_men_docx = self.client.get(reverse("men:shakl1_docx"), {"yil": joriy})
        self.assertEqual(r_men_docx.status_code, 200)

        login(self.client, admin)
        r_svod = self.client.get(reverse("office:svod_excel"), {"yil": joriy})
        wb = load_workbook(BytesIO(b"".join(r_svod.streaming_content)))
        self.assertEqual(len(wb.sheetnames), 3)

        r_ofis_zip = self.client.get(
            reverse("office:oqituvchi_shakl1_zip"), {"yil": joriy}
        )
        self.assertEqual(r_ofis_zip.status_code, 200)


class ExcelImportVaSahifalashWebTests(TestCase):
    def test_oqituvchi_va_yonalish_import_viewlari(self) -> None:
        Department.objects.create(nomi="Ekologiya")
        OqituvchiTuri.objects.create(nomi="Assistent", min_soat=600)
        login(self.client, office_admin_yarat())

        self.assertEqual(
            self.client.get(reverse("office:oqituvchi_namuna_excel")).status_code, 200
        )
        fayl = _xlsx_upload(
            "oqit.xlsx",
            [
                ["Familiya", "Ism", "Telefon", "Kafedra", "Lavozim"],
                ["Toshmatov", "Bekzod", "+998917776655", "Ekologiya", "Assistent"],
            ],
        )
        r = self.client.post(reverse("office:oqituvchi_import"), {"fayl": fayl})
        self.assertContains(r, "+998917776655")

        r_parol = self.client.get(reverse("office:oqituvchi_import_parollar"))
        self.assertEqual(r_parol.status_code, 200)
        # Session dan o'chirilgandan so'ng qayta yuklab bo'lmaydi
        self.assertEqual(
            self.client.get(reverse("office:oqituvchi_import_parollar")).status_code,
            404,
        )

        fayl_yon = _xlsx_upload(
            "yon.xlsx",
            [
                ["Kod", "Nom", "BS kod", "BS nom", "TS kod", "TS nom"],
                ["60710100", "Kimyo muhandisligi", "7", "Muhandislik", "607", "Kimyo"],
            ],
        )
        self.client.post(reverse("office:yonalish_import"), {"fayl": fayl_yon})
        self.assertTrue(TalimYonalishi.objects.filter(kodi="60710100").exists())

    def test_sozlamalar_va_oqituvchilar_server_qidiruv_va_sahifalash(self) -> None:
        kaf = Department.objects.create(nomi="Informatika")
        mudir = mudir_yarat(kafedra=kaf)
        admin = office_admin_yarat()

        TalimYonalishi.objects.bulk_create(
            [
                TalimYonalishi(
                    kodi=f"6061{i:04d}",
                    nomi=f"Yo'nalish {i}",
                    bilim_sohasi_kodi="6",
                    bilim_sohasi_nomi="AKT",
                    talim_sohasi_kodi="606",
                    talim_sohasi_nomi="IT",
                )
                for i in range(30)
            ]
        )
        for _ in range(35):
            make_oqituvchi(kafedra=kaf, min_soat=400)

        login(self.client, admin)
        r_soz_p2 = self.client.get(reverse("office:sozlamalar"), {"page": 2})
        self.assertContains(r_soz_p2, "Sahifa 2 / 2")

        r_soz_q = self.client.get(reverse("office:sozlamalar"), {"q": "60610019"})
        self.assertContains(r_soz_q, "Yo&#x27;nalish 19")
        self.assertNotContains(r_soz_q, "Yo&#x27;nalish 18")

        r_oqit_p2 = self.client.get(reverse("office:oqituvchi_list"), {"page": 2})
        self.assertContains(r_oqit_p2, "Sahifa 2 / 2")
        self.assertContains(r_oqit_p2, 'hx-select-oob="#oqituvchi-excel-btn"')

        login(self.client, mudir)
        r_kaf_p2 = self.client.get(reverse("kafedra:oqituvchi_list"), {"page": 2})
        self.assertContains(r_kaf_p2, "Sahifa 2 / 2")
        self.assertEqual(r_kaf_p2.context["oqituvchilar_soni"], 36)

    def test_bildirishnoma_context_processor_o1_sorgov(self) -> None:
        user = oqituvchi_yarat()
        Bildirishnoma.objects.bulk_create(
            [
                Bildirishnoma(qabul_qiluvchi=user, sarlavha=f"Xabar {i}")
                for i in range(15)
            ]
        )
        login(self.client, user)
        with self.assertNumQueries(4):
            r = self.client.get(reverse("parol_ozgartirish"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["oqilmagan_xabarlar_soni"], 15)
        self.assertEqual(len(r.context["songgi_xabarlar"]), 6)

    def test_health_va_middleware_konstanta(self) -> None:
        self.assertIn(
            "ParolAlmashtirishMajburiyMiddleware", " ".join(settings.MIDDLEWARE)
        )
        self.assertFalse(
            KafedraYuklamaTasdiq.objects.filter(
                holat=KafedraTasdiqHolati.TASDIQLANGAN
            ).exists()
        )
