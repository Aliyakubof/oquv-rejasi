from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from plans.models import Fan, FanTuri, SoatTuri, Yuklama
from plans.tests.factories import (
    fan_semestr_yasa,
    fan_yasa,
    guruh_yasa,
    oqituvchi_yasa,
    reja_yasa,
)


class YuklamaSoatTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.reja = reja_yasa()
        cls.fan = fan_yasa(cls.reja)
        cls.fs = fan_semestr_yasa(cls.fan.tanlangan_variant, kurs_ishi_bor=True)
        cls.guruh = guruh_yasa(cls.reja)
        cls.oqituvchi = oqituvchi_yasa()

    def test_maruza_soat_butun_oqimga_bir_marta(self) -> None:
        yuklama = Yuklama.objects.create(
            fan_semestr=self.fs, tur=SoatTuri.MARUZA, oqituvchi=self.oqituvchi
        )
        self.assertEqual(yuklama.soat, 24)

    def test_guruh_yuklamasi_bir_guruh_soati(self) -> None:
        yuklama = Yuklama.objects.create(
            fan_semestr=self.fs,
            tur=SoatTuri.LABORATORIYA,
            oqituvchi=self.oqituvchi,
            guruh=self.guruh,
        )
        self.assertEqual(yuklama.soat, 24)

    def test_kurs_ishi_soati_talabaga_ikki_soat(self) -> None:
        yuklama = Yuklama.objects.create(
            fan_semestr=self.fs,
            tur=SoatTuri.KURS_ISHI,
            oqituvchi=self.oqituvchi,
            talabalar_soni=25,
        )
        self.assertEqual(yuklama.soat, 50)


class YuklamaConstraintTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.reja = reja_yasa()
        cls.fan = fan_yasa(cls.reja)
        cls.fs = fan_semestr_yasa(cls.fan.tanlangan_variant, kurs_ishi_bor=True)
        cls.guruh = guruh_yasa(cls.reja)
        cls.oqituvchi = oqituvchi_yasa()
        cls.boshqa_oqituvchi = oqituvchi_yasa()

    def test_ikkinchi_maruza_yuklamasi_taqiqlanadi(self) -> None:
        Yuklama.objects.create(
            fan_semestr=self.fs, tur=SoatTuri.MARUZA, oqituvchi=self.oqituvchi
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            Yuklama.objects.create(
                fan_semestr=self.fs,
                tur=SoatTuri.MARUZA,
                oqituvchi=self.boshqa_oqituvchi,
            )

    def test_guruh_ikki_marta_taqsimlanmaydi(self) -> None:
        Yuklama.objects.create(
            fan_semestr=self.fs,
            tur=SoatTuri.AMALIYOT,
            oqituvchi=self.oqituvchi,
            guruh=self.guruh,
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            Yuklama.objects.create(
                fan_semestr=self.fs,
                tur=SoatTuri.AMALIYOT,
                oqituvchi=self.boshqa_oqituvchi,
                guruh=self.guruh,
            )

    def test_guruh_boshqa_turda_taqsimlanishi_mumkin(self) -> None:
        Yuklama.objects.create(
            fan_semestr=self.fs,
            tur=SoatTuri.AMALIYOT,
            oqituvchi=self.oqituvchi,
            guruh=self.guruh,
        )
        Yuklama.objects.create(
            fan_semestr=self.fs,
            tur=SoatTuri.LABORATORIYA,
            oqituvchi=self.boshqa_oqituvchi,
            guruh=self.guruh,
        )

    def test_guruhsiz_amaliyot_taqiqlanadi(self) -> None:
        with self.assertRaises(IntegrityError), transaction.atomic():
            Yuklama.objects.create(
                fan_semestr=self.fs, tur=SoatTuri.AMALIYOT, oqituvchi=self.oqituvchi
            )

    def test_guruhli_maruza_taqiqlanadi(self) -> None:
        with self.assertRaises(IntegrityError), transaction.atomic():
            Yuklama.objects.create(
                fan_semestr=self.fs,
                tur=SoatTuri.MARUZA,
                oqituvchi=self.oqituvchi,
                guruh=self.guruh,
            )

    def test_talabasiz_kurs_ishi_taqiqlanadi(self) -> None:
        with self.assertRaises(IntegrityError), transaction.atomic():
            Yuklama.objects.create(
                fan_semestr=self.fs, tur=SoatTuri.KURS_ISHI, oqituvchi=self.oqituvchi
            )


class YuklamaCleanTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.reja = reja_yasa()
        cls.fan = fan_yasa(cls.reja, seminar_soat=0)
        cls.fs = fan_semestr_yasa(
            cls.fan.tanlangan_variant, seminar_soat=0, kurs_ishi_bor=True
        )
        cls.guruh = guruh_yasa(cls.reja)
        cls.oqituvchi = oqituvchi_yasa()

    def test_boshqa_reja_guruhi_rad_etiladi(self) -> None:
        boshqa_reja = reja_yasa(yonalish_kodi="60610200", yonalish_nomi="AT")
        begona_guruh = guruh_yasa(boshqa_reja)
        yuklama = Yuklama(
            fan_semestr=self.fs,
            tur=SoatTuri.AMALIYOT,
            oqituvchi=self.oqituvchi,
            guruh=begona_guruh,
        )
        with self.assertRaises(ValidationError) as ctx:
            yuklama.full_clean()
        self.assertIn("guruh", ctx.exception.message_dict)

    def test_tanlanmagan_variant_rad_etiladi(self) -> None:
        tanlov_fan = fan_yasa(self.reja, raqam="2.01", turi=FanTuri.TANLOV)
        fs = fan_semestr_yasa(tanlov_fan.variantlar.first())
        yuklama = Yuklama(fan_semestr=fs, tur=SoatTuri.MARUZA, oqituvchi=self.oqituvchi)
        with self.assertRaises(ValidationError) as ctx:
            yuklama.full_clean()
        self.assertIn("fan_semestr", ctx.exception.message_dict)

    def test_soati_yoq_tur_rad_etiladi(self) -> None:
        yuklama = Yuklama(
            fan_semestr=self.fs,
            tur=SoatTuri.SEMINAR,
            oqituvchi=self.oqituvchi,
            guruh=self.guruh,
        )
        with self.assertRaises(ValidationError) as ctx:
            yuklama.full_clean()
        self.assertIn("tur", ctx.exception.message_dict)

    def test_kurs_ishi_ortiqcha_taqsimlanmaydi(self) -> None:
        Yuklama.objects.create(
            fan_semestr=self.fs,
            tur=SoatTuri.KURS_ISHI,
            oqituvchi=self.oqituvchi,
            talabalar_soni=50,
        )
        yuklama = Yuklama(
            fan_semestr=self.fs,
            tur=SoatTuri.KURS_ISHI,
            oqituvchi=oqituvchi_yasa(),
            talabalar_soni=26,  # 50 + 26 > 75
        )
        with self.assertRaises(ValidationError) as ctx:
            yuklama.full_clean()
        self.assertIn("talabalar_soni", ctx.exception.message_dict)

    def test_kurs_ishi_sigimga_teng_taqsimlanadi(self) -> None:
        Yuklama.objects.create(
            fan_semestr=self.fs,
            tur=SoatTuri.KURS_ISHI,
            oqituvchi=self.oqituvchi,
            talabalar_soni=50,
        )
        yuklama = Yuklama(
            fan_semestr=self.fs,
            tur=SoatTuri.KURS_ISHI,
            oqituvchi=oqituvchi_yasa(),
            talabalar_soni=25,
        )
        yuklama.full_clean()


class FanTest(TestCase):
    def test_kredit_har_ottiz_soatga_bir(self) -> None:
        fan = fan_yasa(reja_yasa(), jami_soat=120)
        self.assertEqual(fan.kredit, 4)

    def test_begona_variant_tanlanmaydi(self) -> None:
        reja = reja_yasa()
        fan = fan_yasa(reja, raqam="1.01")
        boshqa_fan = fan_yasa(reja, raqam="1.02")
        fan.tanlangan_variant = boshqa_fan.tanlangan_variant
        with self.assertRaises(ValidationError):
            fan.full_clean()


class YuklamaKafedraCleanTest(TestCase):
    def test_boshqa_kafedra_oqituvchisi_rad_etiladi(self) -> None:
        from accounts.models import Department

        kaf1 = Department.objects.create(nomi="Birinchi")
        kaf2 = Department.objects.create(nomi="Ikkinchi")
        fan = fan_yasa(reja_yasa(), kafedra=kaf1)
        fs = fan_semestr_yasa(fan.tanlangan_variant, semestr=1)
        oqit2 = oqituvchi_yasa(kafedra=kaf2)
        yuklama = Yuklama(fan_semestr=fs, tur=SoatTuri.MARUZA, oqituvchi=oqit2)
        with self.assertRaises(ValidationError) as ctx:
            yuklama.full_clean()
        self.assertIn("oqituvchi", ctx.exception.message_dict)


class FanSemestrTest(TestCase):
    def test_oquv_va_akademik_yil(self) -> None:
        # DI2024, 3-semestr: 2-kurs, 2025/2026 akademik yil.
        fan = fan_yasa(reja_yasa(boshlanish_yili=2024))
        fs = fan_semestr_yasa(fan.tanlangan_variant, semestr=3)
        self.assertEqual(fs.oquv_yili, 2)
        self.assertEqual(fs.akademik_yil, 2025)

    def test_kurs_ishi_soati_maydondan_olinmaydi(self) -> None:
        fan = fan_yasa(reja_yasa())
        fs = fan_semestr_yasa(fan.tanlangan_variant)
        with self.assertRaises(ValueError):
            fs.tur_soat(SoatTuri.KURS_ISHI)


class FanBegonaVariantTest(TestCase):
    def test_ikkita_reja_fanlari_mustaqil(self) -> None:
        reja = reja_yasa()
        boshqa_reja = reja_yasa(yonalish_kodi="60610200", yonalish_nomi="AT")
        fan_yasa(reja, raqam="1.01")
        fan_yasa(boshqa_reja, raqam="1.01")
        self.assertEqual(Fan.objects.filter(raqam="1.01").count(), 2)
