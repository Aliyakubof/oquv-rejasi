from django.core.exceptions import ValidationError
from django.test import TestCase

from accounts.models import Department
from plans.models import FanTuri, SoatTuri, Yuklama
from plans.services import (
    SemestrTahrir,
    fan_semestr_talabi,
    guruhlarni_sinxronlash,
    kafedra_taqsimoti,
    kafedraga_biriktirish,
    oqituvchi_yillik_yuklamasi,
    semestrovka_yangilash,
    taqsimot_hisoboti,
    variantni_tanlash,
    yuklama_kamomadi,
)
from plans.tests.factories import (
    make_fan,
    make_fan_semestr,
    make_guruh,
    make_oqituvchi,
    make_reja,
    make_variant,
)


class FanSemestrTalabiTest(TestCase):
    def test_talab_turlar_boyicha(self) -> None:
        # 3 guruh, 75 talaba: maruza x1, guruhli turlar x3, kurs ishi 2h x 75.
        reja = make_reja()
        fan = make_fan(reja)
        fs = make_fan_semestr(fan.tanlangan_variant, kurs_ishi_bor=True)
        self.assertEqual(
            fan_semestr_talabi(fs, reja),
            {
                SoatTuri.MARUZA: 24,
                SoatTuri.AMALIYOT: 72,
                SoatTuri.LABORATORIYA: 72,
                SoatTuri.KURS_ISHI: 150,
            },
        )

    def test_sonlar_kiritilmaguncha_talab_nomalum(self) -> None:
        reja = make_reja(talabalar_soni=None, guruhlar_soni=None)
        fan = make_fan(reja)
        fs = make_fan_semestr(fan.tanlangan_variant, kurs_ishi_bor=True)
        talab = fan_semestr_talabi(fs, reja)
        self.assertEqual(talab[SoatTuri.MARUZA], 24)
        self.assertIsNone(talab[SoatTuri.AMALIYOT])
        self.assertIsNone(talab[SoatTuri.KURS_ISHI])

    def test_nol_soatli_turlar_chiqmaydi(self) -> None:
        reja = make_reja()
        fan = make_fan(reja)
        fs = make_fan_semestr(
            fan.tanlangan_variant, laboratoriya_soat=0, kurs_ishi_bor=False
        )
        talab = fan_semestr_talabi(fs, reja)
        self.assertNotIn(SoatTuri.LABORATORIYA, talab)
        self.assertNotIn(SoatTuri.KURS_ISHI, talab)
        self.assertNotIn(SoatTuri.SEMINAR, talab)


class TaqsimotHisobotiTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.reja = make_reja()
        cls.fan = make_fan(cls.reja)
        cls.fs = make_fan_semestr(cls.fan.tanlangan_variant, semestr=1)
        cls.guruh1 = make_guruh(cls.reja, 1)
        cls.guruh2 = make_guruh(cls.reja, 2)
        cls.oqituvchi = make_oqituvchi()
        Yuklama.objects.create(
            fan_semestr=cls.fs, tur=SoatTuri.MARUZA, oqituvchi=cls.oqituvchi
        )
        for guruh in (cls.guruh1, cls.guruh2):
            Yuklama.objects.create(
                fan_semestr=cls.fs,
                tur=SoatTuri.LABORATORIYA,
                oqituvchi=cls.oqituvchi,
                guruh=guruh,
            )

    def _satr(self, satrlar: list, tur: str):
        return next(s for s in satrlar if s.tur == tur)

    def test_taqsimlangan_va_qoldiq(self) -> None:
        satrlar = taqsimot_hisoboti(self.reja)
        maruza = self._satr(satrlar, SoatTuri.MARUZA)
        self.assertEqual(maruza.taqsimlangan_soat, 24)
        self.assertEqual(maruza.qoldiq_soat, 0)
        laboratoriya = self._satr(satrlar, SoatTuri.LABORATORIYA)
        self.assertEqual(laboratoriya.talab_soat, 72)
        self.assertEqual(laboratoriya.taqsimlangan_soat, 48)
        self.assertEqual(laboratoriya.qoldiq_soat, 24)
        amaliyot = self._satr(satrlar, SoatTuri.AMALIYOT)
        self.assertEqual(amaliyot.taqsimlangan_soat, 0)

    def test_tanlanmagan_tanlov_hisobga_kirmaydi(self) -> None:
        tanlov = make_fan(self.reja, raqam="2.01", turi=FanTuri.TANLOV)
        make_fan_semestr(tanlov.variantlar.first(), semestr=1)
        satrlar = taqsimot_hisoboti(self.reja)
        self.assertEqual({s.fan_semestr for s in satrlar}, {self.fs})

    def test_kurs_filtri(self) -> None:
        make_fan_semestr(self.fan.tanlangan_variant, semestr=3)
        satrlar = taqsimot_hisoboti(self.reja, kurs=2)
        self.assertTrue(all(s.fan_semestr.semestr == 3 for s in satrlar))

    def test_kafedra_taqsimoti_yil_kesimida(self) -> None:
        kafedra = Department.objects.create(nomi="Axborot tizimlari")
        variant = self.fan.tanlangan_variant
        variant.kafedra = kafedra
        variant.save()
        make_fan_semestr(variant, semestr=3)  # 2025/2026 o'quv yili
        satrlar = kafedra_taqsimoti(kafedra, 2024)
        self.assertEqual({s.fan_semestr.semestr for s in satrlar}, {1})


class GuruhSinxronlashTest(TestCase):
    def test_yaratadi_va_qisqartiradi(self) -> None:
        reja = make_reja(guruhlar_soni=3)
        guruhlar = guruhlarni_sinxronlash(reja)
        self.assertEqual(
            [g.nomi for g in guruhlar], ["DI-2024-1", "DI-2024-2", "DI-2024-3"]
        )
        reja.guruhlar_soni = 2
        reja.save()
        self.assertEqual(len(guruhlarni_sinxronlash(reja)), 2)

    def test_prefiks_bolmasa_kod_ishlatiladi(self) -> None:
        reja = make_reja(guruh_prefiksi="", guruhlar_soni=1)
        guruhlar = guruhlarni_sinxronlash(reja)
        self.assertEqual(guruhlar[0].nomi, "60610100-2024-1")

    def test_prefiks_ozgarganda_mavjud_guruh_nomi_yangilanadi(self) -> None:
        reja = make_reja(guruh_prefiksi="", guruhlar_soni=2)
        guruhlarni_sinxronlash(reja)
        reja.guruh_prefiksi = "AT"
        reja.save(update_fields=["guruh_prefiksi"])
        guruhlar = guruhlarni_sinxronlash(reja)
        self.assertEqual([g.nomi for g in guruhlar], ["AT-2024-1", "AT-2024-2"])

    def test_yuklamali_guruh_ochirilmaydi(self) -> None:
        reja = make_reja(guruhlar_soni=2)
        guruhlarni_sinxronlash(reja)
        fan = make_fan(reja)
        fs = make_fan_semestr(fan.tanlangan_variant)
        Yuklama.objects.create(
            fan_semestr=fs,
            tur=SoatTuri.AMALIYOT,
            oqituvchi=make_oqituvchi(),
            guruh=reja.guruhlar.get(raqam=2),
        )
        reja.guruhlar_soni = 1
        reja.save()
        guruhlar = guruhlarni_sinxronlash(reja)
        self.assertEqual(len(guruhlar), 2)


class YillikYuklamaTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.reja = make_reja(boshlanish_yili=2024)
        fan = make_fan(cls.reja)
        cls.fs_2024 = make_fan_semestr(fan.tanlangan_variant, semestr=1)
        cls.fs_2025 = make_fan_semestr(fan.tanlangan_variant, semestr=3)
        cls.oqituvchi = make_oqituvchi(min_soat=600)
        Yuklama.objects.create(
            fan_semestr=cls.fs_2024, tur=SoatTuri.MARUZA, oqituvchi=cls.oqituvchi
        )
        Yuklama.objects.create(
            fan_semestr=cls.fs_2025, tur=SoatTuri.MARUZA, oqituvchi=cls.oqituvchi
        )

    def test_yil_kesimida_hisoblaydi(self) -> None:
        self.assertEqual(oqituvchi_yillik_yuklamasi(self.oqituvchi, 2024), 24)
        self.assertEqual(oqituvchi_yillik_yuklamasi(self.oqituvchi, 2025), 24)
        self.assertEqual(oqituvchi_yillik_yuklamasi(self.oqituvchi, 2026), 0)

    def test_kamomad_hisoboti(self) -> None:
        bosh_oqituvchi = make_oqituvchi(min_soat=300)
        holatlar = yuklama_kamomadi(2024)
        holat = next(h for h in holatlar if h.oqituvchi == self.oqituvchi)
        self.assertEqual(holat.jami_soat, 24)
        self.assertEqual(holat.kamomad, 576)
        bosh = next(h for h in holatlar if h.oqituvchi == bosh_oqituvchi)
        self.assertEqual(bosh.jami_soat, 0)
        self.assertEqual(bosh.kamomad, 300)
        # Sorted by deficit: 576 first.
        self.assertEqual(holatlar[0].oqituvchi, self.oqituvchi)

    def test_kamomad_kafedra_filtri(self) -> None:
        boshqa_kafedra = Department.objects.create(nomi="Marketing")
        begona = make_oqituvchi(kafedra=boshqa_kafedra)
        holatlar = yuklama_kamomadi(2024, kafedra=boshqa_kafedra)
        self.assertEqual([h.oqituvchi for h in holatlar], [begona])


class VariantniTanlashTest(TestCase):
    def test_tanlov_variantini_tanlaydi(self) -> None:
        reja = make_reja()
        fan = make_fan(reja, raqam="2.01", turi=FanTuri.TANLOV)
        ikkinchi = make_variant(fan, nomi="Muqobil fan")
        variantni_tanlash(fan, ikkinchi)
        fan.refresh_from_db()
        self.assertEqual(fan.tanlangan_variant, ikkinchi)

    def test_majburiy_fan_rad_etiladi(self) -> None:
        fan = make_fan(make_reja())
        with self.assertRaises(ValidationError):
            variantni_tanlash(fan, fan.tanlangan_variant)

    def test_begona_variant_rad_etiladi(self) -> None:
        reja = make_reja()
        tanlov = make_fan(reja, raqam="2.01", turi=FanTuri.TANLOV)
        begona = make_fan(reja, raqam="1.05")
        with self.assertRaises(ValidationError):
            variantni_tanlash(tanlov, begona.tanlangan_variant)

    def test_yuklamali_variant_almashtirilmaydi(self) -> None:
        reja = make_reja()
        fan = make_fan(reja, raqam="2.01", turi=FanTuri.TANLOV)
        birinchi = fan.variantlar.first()
        ikkinchi = make_variant(fan, nomi="Muqobil fan")
        variantni_tanlash(fan, birinchi)
        fs = make_fan_semestr(birinchi, semestr=1)
        Yuklama.objects.create(
            fan_semestr=fs, tur=SoatTuri.MARUZA, oqituvchi=make_oqituvchi()
        )
        with self.assertRaises(ValidationError):
            variantni_tanlash(fan, ikkinchi)


class SemestrovkaYangilashVariantSyncTest(TestCase):
    def test_variant_soatlari_semestrovka_bilan_yangilanadi(self) -> None:
        reja = make_reja()
        fan = make_fan(reja)
        variant = fan.tanlangan_variant
        fs = make_fan_semestr(variant, semestr=1)
        semestrovka_yangilash(
            reja,
            [
                SemestrTahrir(
                    fan_semestr_id=fs.pk,
                    maruza_soat=40,
                    amaliyot_soat=20,
                    laboratoriya_soat=10,
                    seminar_soat=6,
                    kurs_ishi_bor=True,
                )
            ],
        )
        variant.refresh_from_db()
        self.assertEqual(variant.maruza_soat, 40)
        self.assertEqual(variant.amaliyot_soat, 20)
        self.assertEqual(variant.laboratoriya_soat, 10)
        self.assertEqual(variant.seminar_soat, 6)
        self.assertEqual(variant.auditoriya_soat, 76)
        self.assertGreater(variant.kurs_ishi_soat, 0)


class KafedragaBiriktirishTest(TestCase):
    def setUp(self) -> None:
        self.reja = make_reja()
        self.kafedra = Department.objects.create(nomi="Matematika")

    def test_kafedra_ornatiladi(self) -> None:
        fan = make_fan(self.reja)
        kafedraga_biriktirish(fan.tanlangan_variant, self.kafedra)
        fan.tanlangan_variant.refresh_from_db()
        self.assertEqual(fan.tanlangan_variant.kafedra, self.kafedra)

    def test_tanlanmagan_variant_rad_etiladi(self) -> None:
        fan = make_fan(self.reja, raqam="2.01", turi=FanTuri.TANLOV)
        with self.assertRaises(ValidationError):
            kafedraga_biriktirish(fan.variantlar.first(), self.kafedra)

    def test_yuklamali_variantdan_kafedra_olib_tashlanmaydi(self) -> None:
        fan = make_fan(self.reja, kafedra=self.kafedra)
        fs = make_fan_semestr(fan.tanlangan_variant)
        oqituvchi = make_oqituvchi(kafedra=self.kafedra)
        Yuklama.objects.create(fan_semestr=fs, tur=SoatTuri.MARUZA, oqituvchi=oqituvchi)
        with self.assertRaises(ValidationError):
            kafedraga_biriktirish(fan.tanlangan_variant, None)
        with self.assertRaises(ValidationError):
            kafedraga_biriktirish(
                fan.tanlangan_variant, Department.objects.create(nomi="Boshqa")
            )
