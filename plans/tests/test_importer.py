from django.test import TestCase

from accounts.models import Department
from parser.models import Alternative, Course, SelectiveSlot
from plans.importer import ImportNatija, ImportXato, ParsedReja
from plans.importer import import_reja as _import_reja
from plans.models import FanSemestr, FanTuri, SoatTuri, TalimYonalishi, Yuklama
from plans.tests.factories import make_oqituvchi, make_yonalish


def import_reja(parsed: ParsedReja, **kwargs: object) -> ImportNatija:
    if not TalimYonalishi.objects.filter(kodi=parsed.yonalish_kodi).exists():
        make_yonalish(kodi=parsed.yonalish_kodi)
    return _import_reja(parsed, **kwargs)


def make_course(**kwargs: object) -> Course:
    maydonlar: dict[str, object] = {
        "num": "1.01",
        "code": "DK101",
        "name": "Dasturlashga kirish",
        "hours": 120,
        "classroom": 60,
        "lecture": 30,
        "practice": 0,
        "lab": 0,
        "seminar": 30,
        "course_proj": 0,
        "semester_credits": {1: 4},
        "semester_weekly_hours": {1: 4},
    }
    maydonlar.update(kwargs)
    return Course(**maydonlar)


def make_slot(**kwargs: object) -> SelectiveSlot:
    maydonlar: dict[str, object] = {
        "num": "2.01",
        "hours": 300,
        "semester_credits": {3: 6, 4: 4},
        "semester_weekly_hours": {3: 4, 4: 4},
        "alternatives": [
            Alternative(
                code="XA1",
                name="Xalqaro amaliyot",
                classroom=120,
                lecture=60,
                practice=60,
                lab=0,
                seminar=0,
                course_proj=0,
            ),
            Alternative(
                code="TB1",
                name="Tarmoq buxgalteriyasi",
                classroom=120,
                lecture=60,
                practice=60,
                lab=0,
                seminar=0,
                course_proj=0,
            ),
        ],
    }
    maydonlar.update(kwargs)
    return SelectiveSlot(**maydonlar)


def make_parsed(
    core: list[Course] | None = None, slots: list[SelectiveSlot] | None = None
) -> ParsedReja:
    return ParsedReja(
        yonalish_kodi="60610100",
        boshlanish_yili=2024,
        daraja="Bakalavr",
        davomiylik_yil=4,
        talim_shakli="Kunduzgi",
        fayl_nomi="di_2024.xlsx",
        core=core if core is not None else [make_course()],
        slots=slots if slots is not None else [],
    )


class ImportRejaTest(TestCase):
    def test_majburiy_fan_avtomatik_tanlanadi(self) -> None:
        natija = import_reja(make_parsed())
        self.assertTrue(natija.yaratildi)
        fan = natija.reja.fanlar.get()
        self.assertEqual(fan.turi, FanTuri.MAJBURIY)
        self.assertEqual(fan.tanlangan_variant.kodi, "DK101")
        self.assertEqual(fan.tanlangan_variant.maruza_soat, 30)

    def test_semestr_taqsimoti_materiallashadi(self) -> None:
        kurs = make_course(
            hours=240,
            classroom=120,
            lecture=60,
            practice=60,
            seminar=0,
            semester_credits={3: 4, 4: 4},
            semester_weekly_hours={3: 4, 4: 4},
        )
        natija = import_reja(make_parsed(core=[kurs]))
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
        natija = import_reja(make_parsed(core=[], slots=[make_slot()]))
        fan = natija.reja.fanlar.get()
        self.assertEqual(fan.turi, FanTuri.TANLOV)
        self.assertIsNone(fan.tanlangan_variant)
        self.assertEqual(fan.variantlar.count(), 2)
        # Alternatives inherit the slot's semester distribution.
        for variant in fan.variantlar.all():
            self.assertEqual(
                list(variant.semestrlar.values_list("semestr", flat=True)), [3, 4]
            )
            self.assertEqual(variant.semestrlar.get(semestr=3).kredit, 6)

    def test_kurs_ishi_oxirgi_semestrga_tushadi(self) -> None:
        kurs = make_course(
            course_proj=2,
            semester_credits={5: 2, 6: 2},
            semester_weekly_hours={5: 2, 6: 2},
        )
        natija = import_reja(make_parsed(core=[kurs]))
        semestrlar = FanSemestr.objects.filter(
            variant=natija.reja.fanlar.get().tanlangan_variant
        )
        self.assertFalse(semestrlar.get(semestr=5).kurs_ishi_bor)
        self.assertTrue(semestrlar.get(semestr=6).kurs_ishi_bor)

    def test_takroriy_raqam_noyoblashtiriladi(self) -> None:
        # Real sheets occasionally repeat a course number by mistake (three
        # unrelated courses all numbered "1.06" in one XM.xlsx row block).
        birinchi = make_course(num="1.06", code="IKXT1-420", name="Ikkinchi til")
        ikkinchi = make_course(num="1.06", code="AShT1730", name="Sharq tili")
        uchinchi = make_course(num="1.06", code="HMFKI106", name="XM kirish")
        natija = import_reja(make_parsed(core=[birinchi, ikkinchi, uchinchi]))
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
        kurs = make_course(semester_credits={}, semester_weekly_hours={})
        natija = import_reja(make_parsed(core=[kurs]))
        self.assertEqual(FanSemestr.objects.count(), 0)
        self.assertEqual(len(natija.ogohlantirishlar), 1)
        self.assertIn("1.01", natija.ogohlantirishlar[0])

    def test_klassifikatorda_yoq_yonalish_rad_etiladi(self) -> None:
        parsed = make_parsed()
        TalimYonalishi.objects.filter(kodi=parsed.yonalish_kodi).delete()
        with self.assertRaises(ImportXato):
            _import_reja(parsed)

    def test_qayta_import_replace_siz_rad_etiladi(self) -> None:
        import_reja(make_parsed())
        with self.assertRaises(ImportXato):
            import_reja(make_parsed())

    def test_replace_yuklama_borida_rad_etiladi(self) -> None:
        natija = import_reja(make_parsed())
        fan_semestr = FanSemestr.objects.get()
        Yuklama.objects.create(
            fan_semestr=fan_semestr, tur=SoatTuri.MARUZA, oqituvchi=make_oqituvchi()
        )
        with self.assertRaises(ImportXato):
            import_reja(make_parsed(), replace=True)
        self.assertEqual(natija.reja.fanlar.count(), 1)

    def test_replace_manual_holatni_saqlaydi(self) -> None:
        natija = import_reja(make_parsed(slots=[make_slot()]))
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

        qayta = import_reja(make_parsed(slots=[make_slot()]), replace=True)

        self.assertFalse(qayta.yaratildi)
        yangi_reja = qayta.reja
        self.assertEqual(yangi_reja.pk, reja.pk)
        self.assertEqual(yangi_reja.talabalar_soni, 75)
        self.assertEqual(yangi_reja.guruhlar_soni, 3)
        yangi_tanlov = yangi_reja.fanlar.get(turi=FanTuri.TANLOV)
        self.assertEqual(yangi_tanlov.tanlangan_variant.kodi, "XA1")
        self.assertEqual(yangi_tanlov.tanlangan_variant.kafedra, kafedra)

    def test_replace_ozgargan_variantni_ogohlantiradi(self) -> None:
        natija = import_reja(make_parsed())
        variant = natija.reja.fanlar.get().tanlangan_variant
        variant.kafedra = Department.objects.create(nomi="Raqamli texnologiyalar")
        variant.save()

        boshqa_nomli = make_course(name="Dasturlash asoslari")
        qayta = import_reja(make_parsed(core=[boshqa_nomli]), replace=True)

        yangi_variant = qayta.reja.fanlar.get().tanlangan_variant
        self.assertIsNone(yangi_variant.kafedra)
        self.assertTrue(
            any("tiklanmadi" in o for o in qayta.ogohlantirishlar),
            qayta.ogohlantirishlar,
        )
