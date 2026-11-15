from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from accounts.models import Department
from plans import dashboard
from plans.dastur.topshirish import (
    dastur_qabul_qilish,
    dastur_rad_etish,
    dastur_topshirish,
    joriy_topshirishlar,
)
from plans.models import DasturTopshirish, SoatTuri, TopshirishHolati, Yuklama
from plans.tests.factories import (
    fan_semestr_yasa,
    fan_yasa,
    oqituvchi_yasa,
    reja_yasa,
)
from web.tests.helpers import ofis_admin_yarat


def _fayl(nomi: str = "dastur.docx") -> SimpleUploadedFile:
    return SimpleUploadedFile(nomi, b"mazmun", content_type="application/octet-stream")


class DasturTopshirishTest(TestCase):
    def setUp(self) -> None:
        yil = dashboard.joriy_akademik_yil()
        kafedra = Department.objects.create(nomi="Matematika")
        reja = reja_yasa(boshlanish_yili=yil)
        fan = fan_yasa(reja, kafedra=kafedra)
        self.variant = fan.tanlangan_variant
        fs = fan_semestr_yasa(self.variant, semestr=1)
        self.egasi = oqituvchi_yasa(kafedra=kafedra)
        self.begona = oqituvchi_yasa(kafedra=kafedra)
        Yuklama.objects.create(
            fan_semestr=fs, tur=SoatTuri.MARUZA, oqituvchi=self.egasi
        )

    def test_egasi_topshiradi(self) -> None:
        topshirish = dastur_topshirish(self.variant, self.egasi, _fayl())
        self.assertEqual(topshirish.holat, TopshirishHolati.KUTILMOQDA)
        self.assertEqual(topshirish.oqituvchi, self.egasi)
        self.assertEqual(topshirish.urinish_raqami, 1)

    def test_begona_topshira_olmaydi(self) -> None:
        with self.assertRaises(ValidationError):
            dastur_topshirish(self.variant, self.begona, _fayl())

    def test_qayta_topshirish_yangi_qator_yaratadi(self) -> None:
        birinchi = dastur_topshirish(self.variant, self.egasi, _fayl("v1.docx"))
        dastur_rad_etish(birinchi, ofis_admin_yarat(), "To'liq emas")

        ikkinchi = dastur_topshirish(self.variant, self.egasi, _fayl("v2.docx"))

        self.assertEqual(DasturTopshirish.objects.count(), 2)
        self.assertEqual(ikkinchi.urinish_raqami, 2)
        self.assertEqual(ikkinchi.holat, TopshirishHolati.KUTILMOQDA)
        self.assertEqual(ikkinchi.izoh, "")
        self.assertIsNone(ikkinchi.korib_chiqqan)

        birinchi.refresh_from_db()
        self.assertEqual(birinchi.izoh, "To'liq emas")
        self.assertEqual(birinchi.holat, TopshirishHolati.RAD_ETILDI)
        self.assertTrue(birinchi.fayl.storage.exists(birinchi.fayl.name))

    def test_kutilayotgan_urinish_ustiga_qayta_topshirib_bolmaydi(self) -> None:
        dastur_topshirish(self.variant, self.egasi, _fayl("v1.docx"))
        with self.assertRaises(ValidationError):
            dastur_topshirish(self.variant, self.egasi, _fayl("v2.docx"))
        self.assertEqual(DasturTopshirish.objects.count(), 1)


class DasturQabulRadTest(TestCase):
    def setUp(self) -> None:
        yil = dashboard.joriy_akademik_yil()
        kafedra = Department.objects.create(nomi="Fizika")
        reja = reja_yasa(yonalish_kodi="60610199", boshlanish_yili=yil)
        fan = fan_yasa(reja, kafedra=kafedra)
        variant = fan.tanlangan_variant
        fs = fan_semestr_yasa(variant, semestr=1)
        self.egasi = oqituvchi_yasa(kafedra=kafedra)
        Yuklama.objects.create(
            fan_semestr=fs, tur=SoatTuri.MARUZA, oqituvchi=self.egasi
        )
        self.topshirish = dastur_topshirish(variant, self.egasi, _fayl())
        self.admin = ofis_admin_yarat()

    def test_qabul_qilish(self) -> None:
        dastur_qabul_qilish(self.topshirish, self.admin)
        self.topshirish.refresh_from_db()
        self.assertEqual(self.topshirish.holat, TopshirishHolati.QABUL_QILINDI)
        self.assertEqual(self.topshirish.korib_chiqqan, self.admin)
        self.assertIsNotNone(self.topshirish.korib_chiqilgan_vaqt)

    def test_rad_etish_izoh_bilan(self) -> None:
        dastur_rad_etish(self.topshirish, self.admin, "Mavzular yetarli emas")
        self.topshirish.refresh_from_db()
        self.assertEqual(self.topshirish.holat, TopshirishHolati.RAD_ETILDI)
        self.assertEqual(self.topshirish.izoh, "Mavzular yetarli emas")

    def test_rad_etish_izohsiz_xato(self) -> None:
        with self.assertRaises(ValidationError):
            dastur_rad_etish(self.topshirish, self.admin, "  ")


class JoriyTopshirishlarTest(TestCase):
    def setUp(self) -> None:
        yil = dashboard.joriy_akademik_yil()
        kafedra = Department.objects.create(nomi="Kimyo")
        self.admin = ofis_admin_yarat()

        reja1 = reja_yasa(yonalish_kodi="60610111", boshlanish_yili=yil)
        fan1 = fan_yasa(reja1, kafedra=kafedra)
        self.variant1 = fan1.tanlangan_variant
        fs1 = fan_semestr_yasa(self.variant1, semestr=1)
        self.egasi1 = oqituvchi_yasa(kafedra=kafedra)
        Yuklama.objects.create(
            fan_semestr=fs1, tur=SoatTuri.MARUZA, oqituvchi=self.egasi1
        )

        reja2 = reja_yasa(yonalish_kodi="60610122", boshlanish_yili=yil)
        fan2 = fan_yasa(reja2, kafedra=kafedra)
        self.variant2 = fan2.tanlangan_variant
        fs2 = fan_semestr_yasa(self.variant2, semestr=1)
        self.egasi2 = oqituvchi_yasa(kafedra=kafedra)
        Yuklama.objects.create(
            fan_semestr=fs2, tur=SoatTuri.MARUZA, oqituvchi=self.egasi2
        )

    def test_bir_variant_uchun_bitta_qator(self) -> None:
        birinchi = dastur_topshirish(self.variant1, self.egasi1, _fayl("v1.docx"))
        dastur_rad_etish(birinchi, self.admin, "To'liq emas")
        dastur_rad_etish(
            dastur_topshirish(self.variant1, self.egasi1, _fayl("v2.docx")),
            self.admin,
            "Yana kamchilik bor",
        )
        uchinchi = dastur_topshirish(self.variant1, self.egasi1, _fayl("v3.docx"))
        dastur_topshirish(self.variant2, self.egasi2, _fayl("boshqa.docx"))

        natija = joriy_topshirishlar()

        self.assertEqual(len(natija), 2)
        variant1_qatori = next(t for t in natija if t.variant_id == self.variant1.pk)
        self.assertEqual(variant1_qatori.pk, uchinchi.pk)
        self.assertEqual(variant1_qatori.urinish_raqami, 3)
