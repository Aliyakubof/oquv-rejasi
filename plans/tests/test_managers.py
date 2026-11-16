from django.test import TestCase

from plans.models import Fan, FanSemestr, FanTuri, SoatTuri, Yuklama
from plans.tests.factories import (
    fan_semestr_yasa,
    fan_yasa,
    oqituvchi_yasa,
    reja_yasa,
    variant_yasa,
)


class FanQuerySetTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.reja = reja_yasa()
        cls.birinchi_kurs_fani = fan_yasa(cls.reja, raqam="1.01")
        fan_semestr_yasa(cls.birinchi_kurs_fani.tanlangan_variant, semestr=1)
        cls.ikkinchi_kurs_fani = fan_yasa(cls.reja, raqam="1.02")
        fan_semestr_yasa(cls.ikkinchi_kurs_fani.tanlangan_variant, semestr=3)
        fan_semestr_yasa(cls.ikkinchi_kurs_fani.tanlangan_variant, semestr=4)
        cls.tanlov_fan = fan_yasa(cls.reja, raqam="2.01", turi=FanTuri.TANLOV)
        variant_yasa(cls.tanlov_fan, nomi="Muqobil fan")

    def test_oquv_yilida_semestr_juftligini_oladi(self) -> None:
        fanlar = Fan.objects.filter(reja=self.reja).oquv_yilida(2)
        self.assertQuerySetEqual(fanlar, [self.ikkinchi_kurs_fani])

    def test_oquv_yilida_takrorlamaydi(self) -> None:
        # 2-kursning ikkala semestri ham mos keladi; fan baribir bir marta chiqadi.
        fanlar = Fan.objects.oquv_yilida(2)
        self.assertEqual(fanlar.count(), 1)

    def test_effektiv_tanlanmaganlarni_chiqarmaydi(self) -> None:
        effektiv = Fan.objects.filter(reja=self.reja).effektiv()
        self.assertNotIn(self.tanlov_fan, effektiv)
        self.assertIn(self.birinchi_kurs_fani, effektiv)

    def test_tanlov_kutilmoqda(self) -> None:
        kutilmoqda = Fan.objects.tanlov_kutilmoqda()
        self.assertQuerySetEqual(kutilmoqda, [self.tanlov_fan])

    def test_tanlangandan_keyin_effektiv_boladi(self) -> None:
        self.tanlov_fan.tanlangan_variant = self.tanlov_fan.variantlar.first()
        self.tanlov_fan.save(update_fields=["tanlangan_variant"])
        self.assertIn(self.tanlov_fan, Fan.objects.effektiv())
        self.assertEqual(Fan.objects.tanlov_kutilmoqda().count(), 0)


class FanSemestrQuerySetTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.reja_2024 = reja_yasa(boshlanish_yili=2024)
        cls.reja_2023 = reja_yasa(
            yonalish_kodi="60610200", yonalish_nomi="AT", boshlanish_yili=2023
        )
        fan_2024 = fan_yasa(cls.reja_2024)
        cls.fs_2024_s3 = fan_semestr_yasa(fan_2024.tanlangan_variant, semestr=3)
        fan_2023 = fan_yasa(cls.reja_2023)
        cls.fs_2023_s3 = fan_semestr_yasa(fan_2023.tanlangan_variant, semestr=3)
        cls.fs_2023_s5 = fan_semestr_yasa(fan_2023.tanlangan_variant, semestr=5)
        cls.tanlov = fan_yasa(cls.reja_2024, raqam="2.01", turi=FanTuri.TANLOV)
        cls.tanlov_fs = fan_semestr_yasa(cls.tanlov.variantlar.first(), semestr=3)

    def test_akademik_yilda_rejalarni_farqlaydi(self) -> None:
        # 2025/2026: DI2024 3-4-semestrda, AT2023 esa 5-6-semestrda bo'ladi.
        natija = set(FanSemestr.objects.akademik_yilda(2025))
        self.assertEqual(natija, {self.fs_2024_s3, self.fs_2023_s5, self.tanlov_fs})

    def test_effektiv_tanlanmagan_variantni_chiqarmaydi(self) -> None:
        effektiv = FanSemestr.objects.effektiv()
        self.assertNotIn(self.tanlov_fs, effektiv)
        self.assertIn(self.fs_2024_s3, effektiv)

    def test_reja_uchun_va_oquv_yilida(self) -> None:
        natija = FanSemestr.objects.reja_uchun(self.reja_2023).oquv_yilida(3)
        self.assertQuerySetEqual(natija, [self.fs_2023_s5])


class YuklamaQuerySetTest(TestCase):
    def test_akademik_yilda_yuklamalarni_filtrlash(self) -> None:
        reja = reja_yasa(boshlanish_yili=2024)
        fan = fan_yasa(reja)
        fs_s1 = fan_semestr_yasa(fan.tanlangan_variant, semestr=1)
        fs_s3 = fan_semestr_yasa(fan.tanlangan_variant, semestr=3)
        oqituvchi = oqituvchi_yasa()
        Yuklama.objects.create(
            fan_semestr=fs_s1, tur=SoatTuri.MARUZA, oqituvchi=oqituvchi
        )
        keyingi_yil = Yuklama.objects.create(
            fan_semestr=fs_s3, tur=SoatTuri.MARUZA, oqituvchi=oqituvchi
        )
        self.assertQuerySetEqual(Yuklama.objects.akademik_yilda(2025), [keyingi_yil])
