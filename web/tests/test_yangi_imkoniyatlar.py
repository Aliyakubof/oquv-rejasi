import json
from io import BytesIO

import openpyxl
from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from accounts.models import Department, OqituvchiTuri
from plans import dashboard, services
from plans.audit import audit_yoz
from plans.models import (
    AuditAmali,
    AuditYozuvi,
    KafedraTasdiqHolati,
    KafedraYuklamaTasdiq,
    OquvReja,
    SoatTuri,
    TalimYonalishi,
    Yuklama,
)
from plans.tests.factories import (
    make_fan,
    make_fan_semestr,
    make_oqituvchi,
    make_reja,
)
from web.tests.helpers import (
    PAROL,
    login,
    mudir_yarat,
    office_admin_yarat,
    oqituvchi_yarat,
)


class ParolOzgartirishTests(TestCase):
    def test_foydalanuvchi_oz_parolini_almashtiradi(self) -> None:
        user = oqituvchi_yarat()
        login(self.client, user)
        javob = self.client.post(
            reverse("parol_ozgartirish"),
            {
                "old_password": PAROL,
                "new_password1": "YangiMaxfiy-987!",
                "new_password2": "YangiMaxfiy-987!",
            },
        )
        self.assertRedirects(
            javob, reverse("bosh_sahifa"), fetch_redirect_response=False
        )
        user.refresh_from_db()
        self.assertTrue(user.check_password("YangiMaxfiy-987!"))


class OqituvchiYuklamaVaExcelTests(TestCase):
    def setUp(self) -> None:
        self.yil = dashboard.joriy_akademik_yil()
        self.kafedra = Department.objects.create(nomi="Dasturiy injiniring")
        self.reja = make_reja(boshlanish_yili=self.yil)
        fan = make_fan(self.reja, kafedra=self.kafedra)
        fs = make_fan_semestr(fan.tanlangan_variant, semestr=1)
        self.oqituvchi = make_oqituvchi(kafedra=self.kafedra)
        Yuklama.objects.create(
            fan_semestr=fs, tur=SoatTuri.MARUZA, oqituvchi=self.oqituvchi
        )

    def test_ofis_oqituvchi_yuklama_varaqasi(self) -> None:
        login(self.client, office_admin_yarat())
        javob = self.client.get(
            reverse("office:oqituvchi_yuklama", args=[self.oqituvchi.pk]),
            {"yil": self.yil},
        )
        self.assertEqual(javob.status_code, 200)
        self.assertContains(javob, str(self.oqituvchi))
        self.assertContains(javob, "24")

    def test_kafedra_oqituvchi_yuklama_varaqasi(self) -> None:
        login(self.client, mudir_yarat(kafedra=self.kafedra))
        javob = self.client.get(
            reverse("kafedra:oqituvchi_yuklama", args=[self.oqituvchi.pk]),
            {"yil": self.yil},
        )
        self.assertEqual(javob.status_code, 200)
        self.assertContains(javob, str(self.oqituvchi))

    def test_ofis_excel_eksport(self) -> None:
        login(self.client, office_admin_yarat())
        javob = self.client.get(reverse("office:oqituvchi_excel"), {"yil": self.yil})
        self.assertEqual(javob.status_code, 200)
        kitob = openpyxl.load_workbook(BytesIO(b"".join(javob.streaming_content)))
        self.assertEqual(kitob.sheetnames, ["O'qituvchilar", "Yuklama tafsiloti"])

    def test_kafedra_hisobot_excel_eksport(self) -> None:
        login(self.client, mudir_yarat(kafedra=self.kafedra))
        javob = self.client.get(reverse("kafedra:hisobot_excel"), {"yil": self.yil})
        self.assertEqual(javob.status_code, 200)


class TopshirilmaganDasturlarMonitoringTests(TestCase):
    def test_topshirilmagan_fan_monitoringda_chiqadi(self) -> None:
        yil = dashboard.joriy_akademik_yil()
        kafedra = Department.objects.create(nomi="Fizika")
        reja = make_reja(boshlanish_yili=yil)
        fan = make_fan(reja, kafedra=kafedra)
        fs = make_fan_semestr(fan.tanlangan_variant, semestr=1)
        oqituvchi = make_oqituvchi(kafedra=kafedra)
        Yuklama.objects.create(fan_semestr=fs, tur=SoatTuri.MARUZA, oqituvchi=oqituvchi)

        login(self.client, office_admin_yarat())
        javob = self.client.get(
            reverse("office:dastur_topshirishlar"), {"holat": "TOPSHIRILMAGAN"}
        )
        self.assertEqual(javob.status_code, 200)
        self.assertContains(javob, "TOPSHIRILMAGAN")
        self.assertContains(javob, fan.tanlangan_variant.nomi)


class SozlamalarVaRejaOchirishTests(TestCase):
    def setUp(self) -> None:
        login(self.client, office_admin_yarat())

    def test_lavozim_va_yonalish_yaratish(self) -> None:
        self.client.post(
            reverse("office:lavozim_yangi"),
            {"nomi": "Stajyor-o'qituvchi", "min_soat": 450},
        )
        self.assertTrue(
            OqituvchiTuri.objects.filter(nomi="Stajyor-o'qituvchi").exists()
        )
        self.client.post(
            reverse("office:yonalish_yangi"),
            {
                "kodi": "60610999",
                "nomi": "Sun'iy intellekt",
                "bilim_sohasi_kodi": "600000",
                "bilim_sohasi_nomi": "AKT",
                "talim_sohasi_kodi": "606100",
                "talim_sohasi_nomi": "Kompyuter texnologiyalari",
            },
        )
        self.assertTrue(TalimYonalishi.objects.filter(kodi="60610999").exists())

    def test_yuklamasiz_reja_ochiriladi_yuklamali_rad_etiladi(self) -> None:
        reja = make_reja()
        fan = make_fan(reja)
        fs = make_fan_semestr(fan.tanlangan_variant, semestr=1)
        yuklama = Yuklama.objects.create(
            fan_semestr=fs, tur=SoatTuri.MARUZA, oqituvchi=make_oqituvchi()
        )
        self.client.post(reverse("office:reja_ochirish", args=[reja.pk]))
        self.assertTrue(OquvReja.objects.filter(pk=reja.pk).exists())

        yuklama.delete()
        self.client.post(reverse("office:reja_ochirish", args=[reja.pk]))
        self.assertFalse(OquvReja.objects.filter(pk=reja.pk).exists())


class JonliYangilanishTests(TestCase):
    def test_jonli_holat_versiyasi_malumot_ozgarganda_yangilanadi(self) -> None:
        login(self.client, office_admin_yarat())
        javob1 = self.client.get(reverse("jonli_holat"))
        self.assertEqual(javob1.status_code, 200)
        v1 = javob1.json()["versiya"]

        kafedra = Department.objects.create(nomi="Matematika")
        javob2 = self.client.get(reverse("jonli_holat"))
        v2 = javob2.json()["versiya"]
        self.assertNotEqual(v1, v2)

        reja = make_reja()
        fan = make_fan(reja)
        fan.tanlangan_variant.kafedra = kafedra
        fan.tanlangan_variant.save()
        javob3 = self.client.get(reverse("jonli_holat"))
        v3 = javob3.json()["versiya"]
        self.assertNotEqual(v2, v3)

    def test_sahifalarda_jonli_atributlari_va_skript_mavjud(self) -> None:
        reja = make_reja(boshlanish_yili=dashboard.joriy_akademik_yil())
        fan = make_fan(reja)
        make_fan_semestr(fan.tanlangan_variant, semestr=1)
        login(self.client, office_admin_yarat())
        javob = self.client.get(reverse("office:dashboard"))
        self.assertContains(javob, "jonli.js")
        self.assertContains(javob, 'data-jonli="office-statlar"')
        self.assertContains(javob, 'data-jonli="office-fan-tbody"')


class KafedraTasdiqWorkflowTests(TestCase):
    def setUp(self) -> None:
        self.yil = dashboard.joriy_akademik_yil()
        self.kafedra = Department.objects.create(nomi="Kiberxavfsizlik")
        self.mudir = mudir_yarat(kafedra=self.kafedra)
        self.reja = make_reja(boshlanish_yili=self.yil)
        fan = make_fan(self.reja, kafedra=self.kafedra)
        self.fs = make_fan_semestr(fan.tanlangan_variant, semestr=1)
        self.oqituvchi = make_oqituvchi(kafedra=self.kafedra)

    def test_kafedra_tasdiqqa_yuborish_va_qulflash(self) -> None:
        login(self.client, self.mudir)
        javob = self.client.post(
            reverse("kafedra:tasdiqqa_yuborish"),
            {"yil": self.yil, "izoh": "Taqsimot yakunlandi"},
        )
        self.assertEqual(javob.status_code, 302)

        tasdiq = KafedraYuklamaTasdiq.objects.get(
            kafedra=self.kafedra, akademik_yil=self.yil
        )
        self.assertEqual(tasdiq.holat, KafedraTasdiqHolati.TASDIQDA)
        self.assertTrue(services.kafedra_yuklama_qulflanganmi(self.kafedra, self.yil))

        # Qulflangan holatda yangi yuklama qo'shish rad etiladi
        post_javob = self.client.post(
            reverse("kafedra:maruza_yaratish", args=[self.fs.pk]),
            {"oqituvchi": self.oqituvchi.pk},
        )
        self.assertContains(post_javob, "qulflangan")

    def test_ofis_tasdiqlash_va_qaytarish(self) -> None:
        services.yuklamani_tasdiqqa_yuborish(self.kafedra, self.yil, "Tekshiring")
        admin = office_admin_yarat()
        login(self.client, admin)

        # Tasdiqlash
        self.client.post(
            reverse("office:kafedra_tasdiqlash", args=[self.kafedra.pk]),
            {"yil": self.yil},
        )
        tasdiq = KafedraYuklamaTasdiq.objects.get(
            kafedra=self.kafedra, akademik_yil=self.yil
        )
        self.assertEqual(tasdiq.holat, KafedraTasdiqHolati.TASDIQLANGAN)
        self.assertTrue(services.kafedra_yuklama_qulflanganmi(self.kafedra, self.yil))

        # Qaytarish
        self.client.post(
            reverse("office:kafedra_qaytarish", args=[self.kafedra.pk]),
            {"yil": self.yil, "izoh": "Soatlar noto'g'ri"},
        )
        tasdiq.refresh_from_db()
        self.assertEqual(tasdiq.holat, KafedraTasdiqHolati.QAYTARILGAN)
        self.assertEqual(tasdiq.izoh, "Soatlar noto'g'ri")
        self.assertFalse(services.kafedra_yuklama_qulflanganmi(self.kafedra, self.yil))


class AuditJurnaliTests(TestCase):
    def test_audit_yozuvlari_ofisda_korinadi_va_filtrlanadi(self) -> None:
        admin = office_admin_yarat()
        kafedra = Department.objects.create(nomi="Axborot xavfsizligi")
        audit_yoz(
            AuditAmali.TASDIQLANDI,
            f"{kafedra.nomi}: 2026/2027 yuklamasi tasdiqlandi.",
            foydalanuvchi=admin,
            model_nomi="Department",
        )

        self.assertTrue(
            AuditYozuvi.objects.filter(amal=AuditAmali.TASDIQLANDI).exists()
        )

        login(self.client, admin)
        javob = self.client.get(reverse("office:audit_list"))
        self.assertEqual(javob.status_code, 200)
        self.assertContains(javob, "Axborot xavfsizligi")
        self.assertContains(javob, "Tasdiqlandi")

        # Amal bo'yicha filtrlash
        javob_filter = self.client.get(
            reverse("office:audit_list"), {"amal": AuditAmali.TASDIQLANDI}
        )
        self.assertEqual(javob_filter.status_code, 200)
        self.assertContains(javob_filter, "Tasdiqlandi")

    def test_audit_yoz_obyekt_va_ip_manzil_bilan_ishlaydi(self) -> None:
        kafedra = Department.objects.create(nomi="Kiberxavfsizlik")
        yozuv = audit_yoz(
            AuditAmali.YARATILDI,
            "Kafedra yaratildi",
            obyekt=kafedra,
            ip_manzil="192.168.1.100",
        )
        self.assertEqual(yozuv.model_nomi, "Department")
        self.assertEqual(yozuv.obyekt_id, str(kafedra.pk))
        self.assertEqual(yozuv.ip_manzil, "192.168.1.100")

    def test_audit_yoz_notogri_ip_manzilni_filtrlaydi(self) -> None:
        yozuv = audit_yoz(
            AuditAmali.YARATILDI,
            "Soxta IP sinovi",
            ip_manzil="not-an-ip-address",
        )
        self.assertIsNone(yozuv.ip_manzil)

    def test_audit_sahifalash_ishlaydi(self) -> None:
        admin = office_admin_yarat()
        AuditYozuvi.objects.bulk_create(
            [
                AuditYozuvi(amal=AuditAmali.YARATILDI, tavsif=f"Yozuv-{i}")
                for i in range(55)
            ]
        )
        login(self.client, admin)
        javob = self.client.get(reverse("office:audit_list"), {"page": 2})
        self.assertEqual(javob.status_code, 200)
        self.assertContains(javob, "Sahifa 2 / 2")
        self.assertContains(javob, "Oldingi")


class Shakl1IndividualRejaTests(TestCase):
    def test_oqituvchi_shakl1_jadvali_korsatiladi(self) -> None:
        yil = dashboard.joriy_akademik_yil()
        kafedra = Department.objects.create(nomi="Dasturiy vositalar")
        mudir = mudir_yarat(kafedra=kafedra)
        oqituvchi = make_oqituvchi(kafedra=kafedra)
        reja = make_reja(boshlanish_yili=yil)
        fan = make_fan(reja, kafedra=kafedra)
        fs = make_fan_semestr(fan.tanlangan_variant, semestr=1)
        Yuklama.objects.create(fan_semestr=fs, tur=SoatTuri.MARUZA, oqituvchi=oqituvchi)

        login(self.client, mudir)
        javob = self.client.get(
            reverse("kafedra:oqituvchi_yuklama", args=[oqituvchi.pk]), {"yil": yil}
        )
        self.assertEqual(javob.status_code, 200)
        self.assertContains(javob, "1-shakl (Individual reja)")
        self.assertContains(javob, "Ma'ruza")
        self.assertContains(javob, "Jami")


class AnalitikaDashboardTests(TestCase):
    def test_ofis_dashboard_analitika_kartochkasi_chiqadi(self) -> None:
        login(self.client, office_admin_yarat())
        yil = dashboard.joriy_akademik_yil()
        reja = make_reja(boshlanish_yili=yil)
        fan = make_fan(reja)
        make_fan_semestr(fan.tanlangan_variant, semestr=1)

        javob = self.client.get(reverse("office:dashboard"))
        self.assertEqual(javob.status_code, 200)
        self.assertContains(javob, "Yuklama taqsimoti va analitika")
        self.assertContains(javob, "Mashg'ulot turlari bo'yicha soatlar nisbati")
        self.assertContains(javob, "Kafedralar bo'yicha yuklama qamrovi")


class RestApiTests(TestCase):
    def setUp(self) -> None:
        self.api_key = settings.HEMIS_API_KEY
        self.kafedra = Department.objects.create(
            nomi="Algoritmlar va sun'iy intellekt", fakultet="AKT"
        )
        self.oqituvchi = make_oqituvchi(kafedra=self.kafedra)
        self.reja = make_reja(boshlanish_yili=2024, yonalish_kodi="60610500")
        fan = make_fan(self.reja, kafedra=self.kafedra)
        self.fs = make_fan_semestr(fan.tanlangan_variant, semestr=1)
        self.yuklama = Yuklama.objects.create(
            fan_semestr=self.fs, tur=SoatTuri.MARUZA, oqituvchi=self.oqituvchi
        )

    def test_api_avtorizatsiyasiz_401(self) -> None:
        javob = self.client.get(reverse("api:rejalar"))
        self.assertEqual(javob.status_code, 401)
        self.assertIn("xato", javob.json())

    def test_api_bearer_token_bilan_ishlaydi(self) -> None:
        auth = f"Bearer {self.api_key}"
        javob = self.client.get(reverse("api:rejalar"), HTTP_AUTHORIZATION=auth)
        self.assertEqual(javob.status_code, 200)
        data = javob.json()
        self.assertGreaterEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["yonalish_kodi"], "60610500")

    def test_api_kafedralar_va_oqituvchilar_va_yuklamalar(self) -> None:
        auth = f"Bearer {self.api_key}"
        # Kafedralar
        j_kaf = self.client.get(reverse("api:kafedralar"), HTTP_AUTHORIZATION=auth)
        self.assertEqual(j_kaf.status_code, 200)
        self.assertIn("Algoritmlar", j_kaf.json()["results"][0]["nomi"])

        # O'qituvchilar
        j_oqi = self.client.get(reverse("api:oqituvchilar"), HTTP_AUTHORIZATION=auth)
        self.assertEqual(j_oqi.status_code, 200)
        self.assertGreaterEqual(j_oqi.json()["count"], 1)

        # Yuklamalar
        j_yuk = self.client.get(
            reverse("api:yuklamalar"), {"yil": 2024}, HTTP_AUTHORIZATION=auth
        )
        self.assertEqual(j_yuk.status_code, 200)
        self.assertGreaterEqual(j_yuk.json()["count"], 1)
        self.assertEqual(j_yuk.json()["results"][0]["tur"], "MARUZA")
        self.assertEqual(j_yuk.json()["results"][0]["akademik_yil"], 2024)

    def test_api_sessiya_orqali_post_csrf_himoyalangan(self) -> None:
        from django.test import Client

        admin = office_admin_yarat()
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(admin)
        javob = csrf_client.post(
            reverse("api:sync"),
            data=json.dumps({"rejalar": []}),
            content_type="application/json",
        )
        self.assertEqual(javob.status_code, 401)

    def test_api_hemis_sync_talabalar_va_guruhlarni_yangilaydi(self) -> None:
        auth = f"Bearer {self.api_key}"
        sync_data = {
            "rejalar": [
                {
                    "yonalish_kodi": "60610500",
                    "boshlanish_yili": 2024,
                    "talabalar_soni": 75,
                    "guruhlar_soni": 3,
                    "guruh_prefiksi": "AI",
                }
            ]
        }
        javob = self.client.post(
            reverse("api:sync"),
            data=json.dumps(sync_data),
            content_type="application/json",
            HTTP_AUTHORIZATION=auth,
        )
        self.assertEqual(javob.status_code, 200)
        self.assertEqual(javob.json()["yangilandi_soni"], 1)

        self.reja.refresh_from_db()
        self.assertEqual(self.reja.talabalar_soni, 75)
        self.assertEqual(self.reja.guruhlar_soni, 3)
        self.assertEqual(self.reja.guruhlar.count(), 3)
        self.assertTrue(
            AuditYozuvi.objects.filter(amal=AuditAmali.TAHRIRLANDI).exists()
        )
