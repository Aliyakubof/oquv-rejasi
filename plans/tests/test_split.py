from django.test import SimpleTestCase

from plans.split import (
    eng_katta_qoldiq_bolish,
    semestr_vaznlari,
    soatni_semestrlarga_bol,
)


class EngKattaQoldiqBolishTest(SimpleTestCase):
    def test_yigindisi_aniq_totalga_teng(self) -> None:
        natija = eng_katta_qoldiq_bolish(100, {1: 1, 2: 1, 3: 1})
        self.assertEqual(sum(natija.values()), 100)
        self.assertEqual(natija, {1: 34, 2: 33, 3: 33})

    def test_proportsional_boladi(self) -> None:
        self.assertEqual(eng_katta_qoldiq_bolish(60, {3: 4, 4: 4}), {3: 30, 4: 30})
        self.assertEqual(eng_katta_qoldiq_bolish(90, {1: 2, 2: 4}), {1: 30, 2: 60})

    def test_teng_qoldiqda_kichik_semestr_yutadi(self) -> None:
        self.assertEqual(eng_katta_qoldiq_bolish(5, {1: 1, 2: 1}), {1: 3, 2: 2})

    def test_bitta_semestr_toliq_oladi(self) -> None:
        self.assertEqual(eng_katta_qoldiq_bolish(24, {2: 5}), {2: 24})

    def test_bosh_vaznlar_bosh_natija(self) -> None:
        self.assertEqual(eng_katta_qoldiq_bolish(24, {}), {})

    def test_nol_total_nol_taqsimot(self) -> None:
        self.assertEqual(eng_katta_qoldiq_bolish(0, {1: 2, 2: 3}), {1: 0, 2: 0})


class SemestrVaznlariTest(SimpleTestCase):
    def test_haftalik_soat_ustun(self) -> None:
        self.assertEqual(semestr_vaznlari({1: 4}, {1: 2}), {1: 4})

    def test_kreditga_qaytadi(self) -> None:
        self.assertEqual(semestr_vaznlari({}, {1: 2, 2: 4}), {1: 2, 2: 4})

    def test_ikkalasi_bosh(self) -> None:
        self.assertEqual(semestr_vaznlari({}, {}), {})

    def test_faqat_kreditdagi_semestr_qoshiladi(self) -> None:
        # Haftalikda ko'rinmay, faqat kreditda turgan semestr ham qolib ketmasin.
        self.assertEqual(semestr_vaznlari({1: 4}, {1: 2, 2: 4}), {1: 4, 2: 4})


class SoatniSemestrlargaBolTest(SimpleTestCase):
    def test_bir_semestrli_fan_ozgarishsiz(self) -> None:
        satrlar, ogohlantirishlar = soatni_semestrlarga_bol(
            24, 24, 24, 0, haftalik={1: 5}, kreditlar={1: 4}
        )
        self.assertEqual(
            satrlar,
            {
                1: {
                    "maruza_soat": 24,
                    "amaliyot_soat": 24,
                    "laboratoriya_soat": 24,
                    "seminar_soat": 0,
                }
            },
        )
        # 5 * 15 = 75 != 72: real jadvalda haftalik yaxlitlanadi, ogohlantirish chiqadi.
        self.assertEqual(len(ogohlantirishlar), 1)

    def test_kop_semestrli_fan_teng_bolinadi(self) -> None:
        satrlar, ogohlantirishlar = soatni_semestrlarga_bol(
            60, 60, 0, 0, haftalik={3: 4, 4: 4}, kreditlar={}
        )
        self.assertEqual(satrlar[3]["maruza_soat"], 30)
        self.assertEqual(satrlar[4]["maruza_soat"], 30)
        self.assertEqual(satrlar[3]["amaliyot_soat"], 30)
        self.assertEqual(ogohlantirishlar, [])

    def test_komponent_yigindisi_saqlanadi(self) -> None:
        satrlar, _ = soatni_semestrlarga_bol(
            45, 31, 7, 3, haftalik={1: 3, 2: 2, 3: 1}, kreditlar={}
        )
        for maydon, jami in [
            ("maruza_soat", 45),
            ("amaliyot_soat", 31),
            ("laboratoriya_soat", 7),
            ("seminar_soat", 3),
        ]:
            self.assertEqual(sum(satr[maydon] for satr in satrlar.values()), jami)

    def test_kredit_vaznlariga_qaytadi(self) -> None:
        satrlar, ogohlantirishlar = soatni_semestrlarga_bol(
            30, 30, 0, 0, haftalik={}, kreditlar={1: 1, 2: 1}
        )
        self.assertEqual(satrlar[1]["maruza_soat"], 15)
        self.assertEqual(satrlar[2]["maruza_soat"], 15)
        # Haftalik soat bo'lmagani uchun 15 haftalik solishtirish yuritilmaydi.
        self.assertEqual(ogohlantirishlar, [])

    def test_taqsimot_umuman_yoq(self) -> None:
        satrlar, ogohlantirishlar = soatni_semestrlarga_bol(
            30, 30, 0, 0, haftalik={}, kreditlar={}
        )
        self.assertEqual(satrlar, {})
        self.assertEqual(len(ogohlantirishlar), 1)

    def test_mos_kelmaslik_ogohlantiradi(self) -> None:
        _, ogohlantirishlar = soatni_semestrlarga_bol(
            30, 30, 0, 0, haftalik={1: 2}, kreditlar={}
        )
        self.assertTrue(any("teng emas" in o for o in ogohlantirishlar))
