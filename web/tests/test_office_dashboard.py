from django.test import TestCase
from django.urls import reverse

from accounts.models import Department
from plans.dashboard import joriy_akademik_yil
from plans.models import FanTuri
from plans.tests.factories import fan_semestr_yasa, fan_yasa, reja_yasa
from web.tests.helpers import ofis_admin_yarat, oqituvchi_yarat, tizimga_kir


class DashboardKorinishTests(TestCase):
    def setUp(self) -> None:
        self.joriy = joriy_akademik_yil()
        self.reja = reja_yasa(boshlanish_yili=self.joriy)
        self.kafedra = Department.objects.create(nomi="Tarix kafedrasi")
        tizimga_kir(self.client, ofis_admin_yarat())

    def test_oqituvchi_kira_olmaydi(self) -> None:
        tizimga_kir(self.client, oqituvchi_yarat())
        javob = self.client.get(reverse("office:dashboard"))
        self.assertRedirects(javob, reverse("bosh_sahifa"), target_status_code=302)

    def test_biriktirilmagan_fan_belgilanadi(self) -> None:
        fan = fan_yasa(self.reja)
        fan_semestr_yasa(fan.tanlangan_variant, semestr=1)
        javob = self.client.get(reverse("office:dashboard"))
        self.assertContains(javob, "qator-biriktirilmagan")
        self.assertContains(javob, "Kafedra biriktirish")

    def test_notogri_yil_joriyga_qaytadi(self) -> None:
        fan = fan_yasa(self.reja)
        fan_semestr_yasa(fan.tanlangan_variant, semestr=1)
        javob = self.client.get(reverse("office:dashboard"), {"yil": "1999"})
        self.assertEqual(javob.context["yil"], self.joriy)

    def test_reja_yoq_bolsa_bosh_holat(self) -> None:
        javob = self.client.get(reverse("office:dashboard"))
        self.assertContains(javob, "empty-state")

    def test_htmx_sorovi_partial_qaytaradi(self) -> None:
        fan = fan_yasa(self.reja)
        fan_semestr_yasa(fan.tanlangan_variant, semestr=1)
        javob = self.client.get(reverse("office:dashboard"), HTTP_HX_REQUEST="true")
        self.assertNotContains(javob, "<html")
        self.assertContains(javob, 'id="statlar"')

    def test_semestrovka_har_semestrni_alohida_korsatadi(self) -> None:
        fan = fan_yasa(self.reja, maruza_soat=60, amaliyot_soat=60)
        variant = fan.tanlangan_variant
        fan_semestr_yasa(
            variant, semestr=1, maruza_soat=30, amaliyot_soat=30, laboratoriya_soat=0
        )
        fan_semestr_yasa(
            variant, semestr=2, maruza_soat=30, amaliyot_soat=30, laboratoriya_soat=0
        )
        javob = self.client.get(reverse("office:dashboard"), {"yil": self.joriy})
        self.assertContains(javob, "Semestrovka")
        self.assertContains(javob, "<strong>S1</strong>")
        self.assertContains(javob, "<strong>S2</strong>")
        # Amaliyot guruhbay: 30 soat x 3 guruh = tooltipda jami 90 soat talab.
        self.assertContains(javob, "3 guruh = 90")


class KafedraBiriktirishTests(TestCase):
    def setUp(self) -> None:
        self.joriy = joriy_akademik_yil()
        self.reja = reja_yasa(boshlanish_yili=self.joriy)
        self.kafedra = Department.objects.create(nomi="Tarix kafedrasi")
        self.fan = fan_yasa(self.reja)
        fan_semestr_yasa(self.fan.tanlangan_variant, semestr=1)
        tizimga_kir(self.client, ofis_admin_yarat())

    def test_kafedra_biriktiriladi_va_statlar_yangilanadi(self) -> None:
        variant = self.fan.tanlangan_variant
        javob = self.client.post(
            reverse("office:kafedra_biriktirish", args=[variant.pk]),
            {"kafedra": self.kafedra.pk, "yil": self.joriy},
        )
        variant.refresh_from_db()
        self.assertEqual(variant.kafedra, self.kafedra)
        self.assertContains(javob, 'hx-swap-oob="true"')
        self.assertContains(javob, "Tarix kafedrasi")

    def test_bekor_qilish(self) -> None:
        variant = self.fan.tanlangan_variant
        variant.kafedra = self.kafedra
        variant.save(update_fields=["kafedra"])
        self.client.post(
            reverse("office:kafedra_biriktirish", args=[variant.pk]),
            {"kafedra": "", "yil": self.joriy},
        )
        variant.refresh_from_db()
        self.assertIsNone(variant.kafedra)


class VariantTanlashTests(TestCase):
    def setUp(self) -> None:
        self.joriy = joriy_akademik_yil()
        self.reja = reja_yasa(boshlanish_yili=self.joriy)
        tizimga_kir(self.client, ofis_admin_yarat())

    def test_tanlov_varianti_tanlanadi(self) -> None:
        fan = fan_yasa(self.reja, raqam="2.01", turi=FanTuri.TANLOV)
        variant = fan.variantlar.first()
        fan_semestr_yasa(variant, semestr=1)
        javob = self.client.post(
            reverse("office:variant_tanlash", args=[fan.pk]),
            {"variant": variant.pk, "yil": self.joriy},
        )
        fan.refresh_from_db()
        self.assertEqual(fan.tanlangan_variant, variant)
        self.assertEqual(javob.status_code, 200)

    def test_majburiy_fanda_xato_korsatiladi(self) -> None:
        fan = fan_yasa(self.reja)
        fan_semestr_yasa(fan.tanlangan_variant, semestr=1)
        javob = self.client.post(
            reverse("office:variant_tanlash", args=[fan.pk]),
            {"variant": fan.tanlangan_variant.pk, "yil": self.joriy},
        )
        self.assertContains(javob, "Faqat tanlov fanlari uchun")
