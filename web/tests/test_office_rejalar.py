from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from accounts.models import Department
from plans.models import DasturTopshirish, FanTuri, SoatTuri, Yuklama
from plans.tests.factories import (
    fan_semestr_yasa,
    fan_yasa,
    oqituvchi_yasa,
    reja_yasa,
)
from web.forms.yuklama import KursIshiYuklamaForm
from web.tests.helpers import ofis_admin_yarat, tizimga_kir


class RejaListTests(TestCase):
    def setUp(self) -> None:
        tizimga_kir(self.client, ofis_admin_yarat())

    def test_rejalar_royxati(self) -> None:
        reja_yasa()
        javob = self.client.get(reverse("office:reja_list"))
        self.assertContains(javob, "Dasturiy injiniring")


class RejaImportTests(TestCase):
    def setUp(self) -> None:
        tizimga_kir(self.client, ofis_admin_yarat())

    def test_notogri_fayl_xato_korsatadi(self) -> None:
        javob = self.client.post(
            reverse("office:reja_yangi"),
            {
                "fayl": SimpleUploadedFile("reja.xlsx", b"bu excel emas"),
                "talabalar_soni": 50,
                "guruhlar_soni": 2,
                "guruh_prefiksi": "BH",
            },
        )
        self.assertContains(javob, "xlsx formatida emas")


class RejaDetailTests(TestCase):
    def setUp(self) -> None:
        self.reja = reja_yasa()
        tizimga_kir(self.client, ofis_admin_yarat())

    def test_semestrovka_chiplari(self) -> None:
        fan = fan_yasa(self.reja)
        fan_semestr_yasa(fan.tanlangan_variant, semestr=1, haftalik_soat=6)
        javob = self.client.get(reverse("office:reja_detail", args=[self.reja.pk]))
        self.assertContains(javob, "sem-fill")
        self.assertContains(javob, "Majburiy fanlar")
        self.assertContains(javob, "Dasturlashga kirish")

    def test_semestrovka_breakdown_har_semestrni_yoyadi(self) -> None:
        fan = fan_yasa(self.reja, maruza_soat=60, amaliyot_soat=60)
        variant = fan.tanlangan_variant
        fan_semestr_yasa(
            variant, semestr=1, maruza_soat=30, amaliyot_soat=30, laboratoriya_soat=0
        )
        fan_semestr_yasa(
            variant, semestr=2, maruza_soat=30, amaliyot_soat=30, laboratoriya_soat=0
        )
        javob = self.client.get(reverse("office:reja_detail", args=[self.reja.pk]))
        # Ochiladigan jadvalda har bir semestr alohida qator bo'lib,
        # soatlarni tahrirlash kataklari chiqadi.
        self.assertContains(javob, "<strong>S1</strong>")
        self.assertContains(javob, "<strong>S2</strong>")
        self.assertContains(javob, 'class="soat-input"')
        self.assertContains(javob, "-amaliyot")

    def test_tanlanmagan_tanlov_belgisi(self) -> None:
        fan = fan_yasa(self.reja, raqam="2.01", turi=FanTuri.TANLOV)
        fan_semestr_yasa(fan.variantlar.first(), semestr=1)
        javob = self.client.get(reverse("office:reja_detail", args=[self.reja.pk]))
        self.assertContains(javob, "TANLANMAGAN")

    def test_detaldan_kafedra_biriktirish_redirect(self) -> None:
        kafedra = Department.objects.create(nomi="Iqtisod")
        fan = fan_yasa(self.reja)
        fan_semestr_yasa(fan.tanlangan_variant, semestr=1)
        variant = fan.tanlangan_variant
        javob = self.client.post(
            reverse("office:kafedra_biriktirish", args=[variant.pk]),
            {
                "kafedra": kafedra.pk,
                "redirect": reverse("office:reja_detail", args=[self.reja.pk]),
            },
        )
        self.assertRedirects(javob, reverse("office:reja_detail", args=[self.reja.pk]))
        variant.refresh_from_db()
        self.assertEqual(variant.kafedra, kafedra)


class SemestrovkaTahrirTests(TestCase):
    def setUp(self) -> None:
        self.reja = reja_yasa()
        self.fan = fan_yasa(self.reja, maruza_soat=60, amaliyot_soat=60)
        self.fs = fan_semestr_yasa(
            self.fan.tanlangan_variant,
            semestr=1,
            maruza_soat=30,
            amaliyot_soat=30,
            laboratoriya_soat=0,
        )
        tizimga_kir(self.client, ofis_admin_yarat())

    def _saqlash(self, **ozgarishlar: object) -> object:
        maydonlar = {
            f"fs-{self.fs.pk}-maruza": 40,
            f"fs-{self.fs.pk}-amaliyot": 20,
            f"fs-{self.fs.pk}-lab": 0,
            f"fs-{self.fs.pk}-seminar": 0,
        }
        maydonlar.update(ozgarishlar)
        return self.client.post(
            reverse("office:semestrovka_saqlash", args=[self.reja.pk]), maydonlar
        )

    def test_soatlar_yangilanadi(self) -> None:
        javob = self._saqlash()
        self.assertRedirects(
            javob,
            reverse("office:reja_detail", args=[self.reja.pk]) + "?tab=semestrovka",
        )
        self.fs.refresh_from_db()
        self.assertEqual(self.fs.maruza_soat, 40)
        self.assertEqual(self.fs.amaliyot_soat, 20)

    def test_kurs_ishi_belgilanadi(self) -> None:
        self._saqlash(**{f"fs-{self.fs.pk}-kursishi": "on"})
        self.fs.refresh_from_db()
        self.assertTrue(self.fs.kurs_ishi_bor)

    def test_taqsimlangan_turni_nolga_tushirib_bolmaydi(self) -> None:
        oqituvchi = oqituvchi_yasa()
        Yuklama.objects.create(
            fan_semestr=self.fs, tur=SoatTuri.MARUZA, oqituvchi=oqituvchi
        )
        self._saqlash(**{f"fs-{self.fs.pk}-maruza": 0})
        self.fs.refresh_from_db()
        self.assertEqual(self.fs.maruza_soat, 30)

    def test_boshqa_rejaning_semestri_tegilmaydi(self) -> None:
        boshqa = reja_yasa(yonalish_kodi="30310100", boshlanish_yili=2023)
        fan2 = fan_yasa(boshqa)
        fs2 = fan_semestr_yasa(fan2.tanlangan_variant, semestr=1, maruza_soat=24)
        self.client.post(
            reverse("office:semestrovka_saqlash", args=[self.reja.pk]),
            {
                f"fs-{fs2.pk}-maruza": 0,
                f"fs-{fs2.pk}-amaliyot": 0,
                f"fs-{fs2.pk}-lab": 0,
                f"fs-{fs2.pk}-seminar": 0,
            },
        )
        fs2.refresh_from_db()
        self.assertEqual(fs2.maruza_soat, 24)


class RejaTahrirTests(TestCase):
    def setUp(self) -> None:
        self.reja = reja_yasa(guruhlar_soni=2)
        tizimga_kir(self.client, ofis_admin_yarat())

    def test_guruhlar_soni_oshirilsa_guruhlar_yaratiladi(self) -> None:
        javob = self.client.post(
            reverse("office:reja_tahrir", args=[self.reja.pk]),
            {
                "bilim_sohasi_kodi": self.reja.bilim_sohasi_kodi,
                "bilim_sohasi_nomi": self.reja.bilim_sohasi_nomi,
                "talim_sohasi_kodi": self.reja.talim_sohasi_kodi,
                "talim_sohasi_nomi": self.reja.talim_sohasi_nomi,
                "yonalish_kodi": self.reja.yonalish_kodi,
                "yonalish_nomi": self.reja.yonalish_nomi,
                "talabalar_soni": 90,
                "guruhlar_soni": 3,
                "guruh_prefiksi": "DI",
            },
        )
        self.assertRedirects(javob, reverse("office:reja_detail", args=[self.reja.pk]))
        self.reja.refresh_from_db()
        self.assertEqual(self.reja.guruhlar.count(), 3)

    def test_dastur_topshirigi_bor_reja_ochirilmaydi(self) -> None:
        kaf = Department.objects.create(nomi="Dasturiy")
        fan = fan_yasa(self.reja, kafedra=kaf)
        oqit = oqituvchi_yasa(kafedra=kaf)
        DasturTopshirish.objects.create(
            variant=fan.tanlangan_variant,
            urinish_raqami=1,
            oqituvchi=oqit,
            fayl="dasturlar/test_delete_block.docx",
        )
        javob = self.client.post(reverse("office:reja_ochirish", args=[self.reja.pk]))
        self.assertRedirects(javob, reverse("office:reja_list"))
        self.assertTrue(self.reja.__class__.objects.filter(pk=self.reja.pk).exists())

    def test_kurs_ishi_tahrir_formasi_ozini_inkor_qilmaydi(self) -> None:
        kaf = Department.objects.create(nomi="Kafedra")
        fan = fan_yasa(self.reja, kafedra=kaf)
        fs = fan_semestr_yasa(fan.tanlangan_variant, semestr=1, kurs_ishi_bor=True)
        oqit = oqituvchi_yasa(kafedra=kaf)
        y = Yuklama.objects.create(
            fan_semestr=fs, tur=SoatTuri.KURS_ISHI, oqituvchi=oqit, talabalar_soni=20
        )
        forma = KursIshiYuklamaForm(
            fs, kaf, data={"oqituvchi": oqit.pk, "talabalar_soni": 30}, instance=y
        )
        self.assertTrue(forma.is_valid(), forma.errors)
