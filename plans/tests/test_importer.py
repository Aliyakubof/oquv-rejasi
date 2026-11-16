from django.test import TestCase

from accounts.models import Department
from parser.models import MajburiyFan, TanlovFani, TanlovVarianti
from plans.importer import ImportNatija, ImportXato, TahlilQilinganReja
from plans.importer import import_reja as _import_reja
from plans.models import FanSemestr, FanTuri, SoatTuri, TalimYonalishi, Yuklama
from plans.tests.factories import oqituvchi_yasa, yonalish_yasa


def import_reja(tahlil: TahlilQilinganReja, **kwargs: object) -> ImportNatija:
    if not TalimYonalishi.objects.filter(kodi=tahlil.yonalish_kodi).exists():
        yonalish_yasa(kodi=tahlil.yonalish_kodi)
    return _import_reja(tahlil, **kwargs)


def majburiy_fan_yarat(**kwargs: object) -> MajburiyFan:
    maydonlar: dict[str, object] = {
        "raqam": "1.01",
        "kod": "DK101",
        "nom": "Dasturlashga kirish",
        "soat": 120,
        "auditoriya": 60,
        "maruza": 30,
        "amaliyot": 0,
        "laboratoriya": 0,
        "seminar": 30,
        "kurs_ishi": 0,
        "semestr_kreditlari": {1: 4},
        "semestr_haftalik_soatlar": {1: 4},
    }
    maydonlar.update(kwargs)
    return MajburiyFan(**maydonlar)


def tanlov_fan_yarat(**kwargs: object) -> TanlovFani:
    maydonlar: dict[str, object] = {
        "raqam": "2.01",
        "soat": 300,
        "semestr_kreditlari": {3: 6, 4: 4},
        "semestr_haftalik_soatlar": {3: 4, 4: 4},
        "variantlar": [
            TanlovVarianti(
                kod="XA1",
                nom="Xalqaro amaliyot",
                auditoriya=120,
                maruza=60,
                amaliyot=60,
                laboratoriya=0,
                seminar=0,
                kurs_ishi=0,
            ),
            TanlovVarianti(
                kod="TB1",
                nom="Tarmoq buxgalteriyasi",
                auditoriya=120,
                maruza=60,
                amaliyot=60,
                laboratoriya=0,
                seminar=0,
                kurs_ishi=0,
            ),
        ],
    }
    maydonlar.update(kwargs)
    return TanlovFani(**maydonlar)


def tahlil_reja_yarat(
    majburiy_fanlar: list[MajburiyFan] | None = None,
    tanlov_fanlar: list[TanlovFani] | None = None,
) -> TahlilQilinganReja:
    return TahlilQilinganReja(
        yonalish_kodi="60610100",
        boshlanish_yili=2024,
        daraja="Bakalavr",
        davomiylik_yil=4,
        talim_shakli="Kunduzgi",
        fayl_nomi="di_2024.xlsx",
        majburiy_fanlar=(
            majburiy_fanlar if majburiy_fanlar is not None else [majburiy_fan_yarat()]
        ),
        tanlov_fanlar=tanlov_fanlar if tanlov_fanlar is not None else [],
    )


class ImportRejaTest(TestCase):
    def test_majburiy_fan_avtomatik_tanlanadi(self) -> None:
        natija = import_reja(tahlil_reja_yarat())
        self.assertTrue(natija.yaratildi)
        fan = natija.reja.fanlar.get()
        self.assertEqual(fan.turi, FanTuri.MAJBURIY)
        self.assertEqual(fan.tanlangan_variant.kodi, "DK101")
        self.assertEqual(fan.tanlangan_variant.maruza_soat, 30)

    def test_semestr_taqsimoti_materiallashadi(self) -> None:
        fan_m = majburiy_fan_yarat(
            soat=240,
            auditoriya=120,
            maruza=60,
            amaliyot=60,
            seminar=0,
            semestr_kreditlari={3: 4, 4: 4},
            semestr_haftalik_soatlar={3: 4, 4: 4},
        )
        natija = import_reja(tahlil_reja_yarat(majburiy_fanlar=[fan_m]))
        semestrlar = FanSemestr.objects.filter(
            variant=natija.reja.fanlar.get().tanlangan_variant
        )
        self.assertEqual(semestrlar.count(), 2)
        uchinchi = semestrlar.get(semestr=3)
        self.assertEqual(uchinchi.maruza_soat, 30)
        self.assertEqual(uchinchi.amaliyot_soat, 30)
        self.assertEqual(uchinchi.kredit, 4)
        self.assertEqual(uchinchi.haftalik_soat, 4)
        self.assertEqual(natija.ogohlantirishlar, [])

    def test_tanlov_slot_kutilmoqda_holatida(self) -> None:
        natija = import_reja(
            tahlil_reja_yarat(majburiy_fanlar=[], tanlov_fanlar=[tanlov_fan_yarat()])
        )
        fan = natija.reja.fanlar.get()
        self.assertEqual(fan.turi, FanTuri.TANLOV)
        self.assertIsNone(fan.tanlangan_variant)
        self.assertEqual(fan.variantlar.count(), 2)
        # Barcha variantlar tanlov blokining semestr taqsimotini oladi.
        for variant in fan.variantlar.all():
            self.assertEqual(
                list(variant.semestrlar.values_list("semestr", flat=True)), [3, 4]
            )
            self.assertEqual(variant.semestrlar.get(semestr=3).kredit, 6)

    def test_kurs_ishi_oxirgi_semestrga_tushadi(self) -> None:
        fan_m = majburiy_fan_yarat(
            kurs_ishi=2,
            semestr_kreditlari={5: 2, 6: 2},
            semestr_haftalik_soatlar={5: 2, 6: 2},
        )
        natija = import_reja(tahlil_reja_yarat(majburiy_fanlar=[fan_m]))
        semestrlar = FanSemestr.objects.filter(
            variant=natija.reja.fanlar.get().tanlangan_variant
        )
        self.assertFalse(semestrlar.get(semestr=5).kurs_ishi_bor)
        self.assertTrue(semestrlar.get(semestr=6).kurs_ishi_bor)

    def test_takroriy_raqam_noyoblashtiriladi(self) -> None:
        # Haqiqiy jadvallarda ba'zan adashib uchta fanga bir xil raqam yozib qo'yiladi.
        birinchi = majburiy_fan_yarat(raqam="1.06", kod="IKXT1-420", nom="Ikkinchi til")
        ikkinchi = majburiy_fan_yarat(raqam="1.06", kod="AShT1730", nom="Sharq tili")
        uchinchi = majburiy_fan_yarat(raqam="1.06", kod="HMFKI106", nom="XM kirish")
        natija = import_reja(
            tahlil_reja_yarat(majburiy_fanlar=[birinchi, ikkinchi, uchinchi])
        )
        raqamlar = sorted(natija.reja.fanlar.values_list("raqam", flat=True))
        self.assertEqual(raqamlar, ["1.06", "1.06.2", "1.06.3"])
        self.assertEqual(
            {f.tanlangan_variant.kodi for f in natija.reja.fanlar.all()},
            {"IKXT1-420", "AShT1730", "HMFKI106"},
        )
        self.assertTrue(
            any("takroriy raqam" in o for o in natija.ogohlantirishlar),
            natija.ogohlantirishlar,
        )

    def test_taqsimotsiz_fan_ogohlantiradi(self) -> None:
        fan_m = majburiy_fan_yarat(semestr_kreditlari={}, semestr_haftalik_soatlar={})
        natija = import_reja(tahlil_reja_yarat(majburiy_fanlar=[fan_m]))
        self.assertEqual(FanSemestr.objects.count(), 0)
        self.assertEqual(len(natija.ogohlantirishlar), 1)
        self.assertIn("1.01", natija.ogohlantirishlar[0])

    def test_klassifikatorda_yoq_yonalish_rad_etiladi(self) -> None:
        tahlil = tahlil_reja_yarat()
        TalimYonalishi.objects.filter(kodi=tahlil.yonalish_kodi).delete()
        with self.assertRaises(ImportXato):
            _import_reja(tahlil)

    def test_qayta_import_replace_siz_rad_etiladi(self) -> None:
        import_reja(tahlil_reja_yarat())
        with self.assertRaises(ImportXato):
            import_reja(tahlil_reja_yarat())

    def test_replace_yuklama_borida_rad_etiladi(self) -> None:
        natija = import_reja(tahlil_reja_yarat())
        fan_semestr = FanSemestr.objects.get()
        Yuklama.objects.create(
            fan_semestr=fan_semestr, tur=SoatTuri.MARUZA, oqituvchi=oqituvchi_yasa()
        )
        with self.assertRaises(ImportXato):
            import_reja(tahlil_reja_yarat(), almashtirish=True)
        self.assertEqual(natija.reja.fanlar.count(), 1)

    def test_replace_manual_holatni_saqlaydi(self) -> None:
        natija = import_reja(
            tahlil_reja_yarat(majburiy_fanlar=[], tanlov_fanlar=[tanlov_fan_yarat()])
        )
        reja = natija.reja
        reja.talabalar_soni = 75
        reja.guruhlar_soni = 3
        reja.save()
        kafedra = Department.objects.create(nomi="Buxgalteriya hisobi")
        tanlov_fan = reja.fanlar.get(turi=FanTuri.TANLOV)
        tanlangan = tanlov_fan.variantlar.get(kodi="XA1")
        tanlangan.kafedra = kafedra
        tanlangan.save()
        tanlov_fan.tanlangan_variant = tanlangan
        tanlov_fan.save()

        qayta = import_reja(
            tahlil_reja_yarat(majburiy_fanlar=[], tanlov_fanlar=[tanlov_fan_yarat()]),
            almashtirish=True,
        )

        self.assertFalse(qayta.yaratildi)
        yangi_reja = qayta.reja
        self.assertEqual(yangi_reja.pk, reja.pk)
        self.assertEqual(yangi_reja.talabalar_soni, 75)
        self.assertEqual(yangi_reja.guruhlar_soni, 3)
        yangi_tanlov = yangi_reja.fanlar.get(turi=FanTuri.TANLOV)
        self.assertEqual(yangi_tanlov.tanlangan_variant.kodi, "XA1")
        self.assertEqual(yangi_tanlov.tanlangan_variant.kafedra, kafedra)

    def test_replace_ozgargan_variantni_ogohlantiradi(self) -> None:
        natija = import_reja(tahlil_reja_yarat())
        variant = natija.reja.fanlar.get().tanlangan_variant
        variant.kafedra = Department.objects.create(nomi="Raqamli texnologiyalar")
        variant.save()

        boshqa_nomli = majburiy_fan_yarat(nom="Dasturlash asoslari")
        qayta = import_reja(
            tahlil_reja_yarat(majburiy_fanlar=[boshqa_nomli]), almashtirish=True
        )

        yangi_variant = qayta.reja.fanlar.get().tanlangan_variant
        self.assertIsNone(yangi_variant.kafedra)
        self.assertTrue(
            any("tiklanmadi" in o for o in qayta.ogohlantirishlar),
            qayta.ogohlantirishlar,
        )
