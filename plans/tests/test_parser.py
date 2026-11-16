"""parser/parser.py uchun testlar: docs/oquv_reja_map.md dagi haqiqiy
jadvallarga o'xshash kichik openpyxl fayllar xotirada yasalib tekshiriladi."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import openpyxl
from django.test import SimpleTestCase

from parser import main as parser_asosiy
from parser.formatter import markdown_yarat
from parser.models import MajburiyFan, TahlilXatosi, TanlovFani, TanlovVarianti
from parser.parser import kitobni_tahlil_qil

_YARATILGAN_KITOBLAR: list[Path] = []


def _kitob_yozish(
    qatorlar: dict[tuple[int, int], object], varaq_nomlari: list[str] | None = None
) -> Path:
    """{(qator, ustun): qiymat} lug'atidan vaqtincha .xlsx fayl yasaydi."""
    kitob = openpyxl.Workbook()
    varaq = kitob.active
    for (qator, ustun), qiymat in qatorlar.items():
        varaq.cell(row=qator, column=ustun, value=qiymat)
    for nom in (varaq_nomlari or [])[1:]:
        kitob.create_sheet(nom)
    if varaq_nomlari:
        varaq.title = varaq_nomlari[0]
    vaqtincha = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
    vaqtincha.close()
    try:
        kitob.save(vaqtincha.name)
    finally:
        kitob.close()
    yol = Path(vaqtincha.name)
    _YARATILGAN_KITOBLAR.append(yol)
    return yol


def _standart_jadval(
    n: int, yonalish: str, muddat: str, yil: str
) -> dict[tuple[int, int], object]:
    """Minimal to'liq jadval: meta-qatorlar, bitta majburiy va bitta tanlov fan."""
    qatorlar: dict[tuple[int, int], object] = {
        (2, 1): yonalish,
        (3, 1): f"O'qish muddati - {muddat}",
        (4, 1): "Akademik daraja - BAKALAVR",
        (4, 2): "O'qish shakli - Kredit-modul",
        (5, 1): "Ta'lim shakli - kunduzgi",
        (6, 1): f"{yil} o'quv yili",
        (17, 1): "II. O'QUV REJASI",
        (18, 4): "Umumiy yuklama",
        (18, 5): "Auditoriya",
        (18, 11): "Semestrdagi haftalar soni",
        (18, 19): "Semestrdagi kreditlar taqsimoti",
        (19, 6): "Ma'ruza",
        (19, 7): "Amaliy",
        (19, 8): "Laboratoriya",
        (19, 9): "Seminar",
        (19, 10): "Kurs ishi",
        (20, 1): "1.00",
        (20, 3): "Majburiy fanlar",
        (21, 1): "1.01",
        (21, 2): "COD1",
        (21, 3): "Course A",
        (21, 4): 120,
        (21, 5): 60,
        (21, 6): 30,
        (21, 7): 30,
        (22, 1): "2.00",
        (22, 3): "Tanlov fanlar",
        (23, 1): "2.01",
        (23, 2): "SEL1",
        (23, 3): "Selective A",
        (23, 4): 90,
        (23, 5): 45,
        (23, 6): 45,
        (24, 2): "SEL2",
        (24, 3): "Selective B",
        (25, 3): "Jami:",
    }
    for i in range(n):
        qatorlar[(19, 11 + i)] = i + 1
        qatorlar[(19, 19 + i)] = i + 1
    qatorlar[(21, 11)] = 4  # majburiy fan: 1-semestr haftalik soati
    qatorlar[(21, 19)] = 4  # majburiy fan: 1-semestr krediti
    qatorlar[(23, 13)] = 3  # tanlov fan: 3-semestr haftalik soati
    qatorlar[(23, 21)] = 3  # tanlov fan: 3-semestr krediti
    return qatorlar


class KitobTahliliMuvaffaqiyatTest(SimpleTestCase):
    def tearDown(self) -> None:
        while _YARATILGAN_KITOBLAR:
            _YARATILGAN_KITOBLAR.pop().unlink(missing_ok=True)
        super().tearDown()

    def test_toliq_varaqni_ochadi(self) -> None:
        yol = _kitob_yozish(
            _standart_jadval(
                8,
                "Ta'lim yo'nalishi: 60110500 - Boshlang'ich ta'lim",
                "4 yil",
                "2024-2025",
            )
        )
        natija = kitobni_tahlil_qil(yol)
        self.assertEqual(natija.yonalish_kodi, "60110500")
        self.assertEqual(natija.yonalish_nomi, "Boshlang'ich ta'lim")
        self.assertEqual(natija.boshlanish_yili, "2024")
        self.assertEqual(natija.davomiylik_yil, 4)
        self.assertEqual(natija.talim_shakli, "Kunduzgi")
        self.assertEqual(len(natija.majburiy_fanlar), 1)
        self.assertEqual(natija.majburiy_fanlar[0].semestr_kreditlari, {1: 4})
        self.assertEqual(len(natija.tanlov_fanlar), 1)
        self.assertEqual(len(natija.tanlov_fanlar[0].variantlar), 2)

    def test_slash_yil_ham_ishlaydi(self) -> None:
        yol = _kitob_yozish(
            _standart_jadval(
                8,
                "Ta'lim yo'nalishi: 60110500 - Boshlang'ich ta'lim",
                "4 yil",
                "2023/2024",
            )
        )
        natija = kitobni_tahlil_qil(yol)
        self.assertEqual(natija.boshlanish_yili, "2023")

    def test_en_dash_yonalish(self) -> None:
        yol = _kitob_yozish(
            _standart_jadval(
                8,
                "Ta'lim yo'nalishi: 60110500 – Boshlang'ich ta'lim",
                "4 yil",
                "2024-2025",
            )
        )
        natija = kitobni_tahlil_qil(yol)
        self.assertEqual(natija.yonalish_kodi, "60110500")
        self.assertEqual(natija.yonalish_nomi, "Boshlang'ich ta'lim")

    def test_uch_yillik_dastur_oltita_semestr(self) -> None:
        yol = _kitob_yozish(
            _standart_jadval(
                6,
                "Ta'lim yo'nalishi: 60111200 - Jismoniy madaniyat",
                "3 yil",
                "2024-2025",
            )
        )
        natija = kitobni_tahlil_qil(yol)
        self.assertEqual(natija.davomiylik_yil, 3)
        self.assertEqual(natija.majburiy_fanlar[0].semestr_kreditlari, {1: 4})

    def test_faol_varaq_birinchisi_bolmasa_ham_birinchisi_oqiladi(self) -> None:
        qatorlar = _standart_jadval(
            8, "Ta'lim yo'nalishi: 60110500 - Boshlang'ich ta'lim", "4 yil", "2024-2025"
        )
        yol = _kitob_yozish(qatorlar, varaq_nomlari=["Kunduzgi", "Sirtqi"])
        kitob = openpyxl.load_workbook(yol)
        try:
            kitob.active = 1
            kitob.save(yol)
        finally:
            kitob.close()
        natija = kitobni_tahlil_qil(yol)
        self.assertEqual(natija.yonalish_kodi, "60110500")
        self.assertTrue(any("bir nechta varaq" in o for o in natija.ogohlantirishlar))

    def test_vergulli_kredit_yaxlitlanadi_va_ogohlantiradi(self) -> None:
        qatorlar = _standart_jadval(
            8, "Ta'lim yo'nalishi: 60110500 - Boshlang'ich ta'lim", "4 yil", "2024-2025"
        )
        qatorlar[(21, 19)] = "1,5"
        yol = _kitob_yozish(qatorlar)
        natija = kitobni_tahlil_qil(yol)
        self.assertEqual(natija.majburiy_fanlar[0].semestr_kreditlari, {1: 2})
        self.assertTrue(any("1,5" in o for o in natija.ogohlantirishlar))

    def test_talim_shakli_oqish_shakli_bilan_adashmaydi(self) -> None:
        qatorlar = _standart_jadval(
            8, "Ta'lim yo'nalishi: 60110500 - Boshlang'ich ta'lim", "4 yil", "2024-2025"
        )
        yol = _kitob_yozish(qatorlar)
        natija = kitobni_tahlil_qil(yol)
        self.assertEqual(natija.talim_shakli, "Kunduzgi")

    def test_talim_shakli_apostrof_variantlari(self) -> None:
        for yorliq in ("Ta’lim shakli - kunduzgi", "Ta‘lim shakli - kunduzgi"):
            qatorlar = _standart_jadval(
                8,
                "Ta'lim yo'nalishi: 60110500 - Boshlang'ich ta'lim",
                "4 yil",
                "2024-2025",
            )
            qatorlar[(5, 1)] = yorliq
            yol = _kitob_yozish(qatorlar)
            natija = kitobni_tahlil_qil(yol)
            self.assertEqual(natija.talim_shakli, "Kunduzgi")

    def test_notanish_talim_shakli_ogohlantiradi(self) -> None:
        qatorlar = _standart_jadval(
            8, "Ta'lim yo'nalishi: 60110500 - Boshlang'ich ta'lim", "4 yil", "2024-2025"
        )
        qatorlar[(5, 1)] = "Ta'lim shakli - masofaviy"
        yol = _kitob_yozish(qatorlar)
        natija = kitobni_tahlil_qil(yol)
        self.assertEqual(natija.talim_shakli, "")
        self.assertTrue(
            any("ta'lim shakli tanilmadi" in o for o in natija.ogohlantirishlar)
        )

    def test_kurs_loyihasi_ishi_yorlig_topiladi(self) -> None:
        qatorlar = _standart_jadval(
            8,
            "Ta'lim yo'nalishi: 60610100 - Axborot texnologiyalari",
            "4 yil",
            "2024-2025",
        )
        qatorlar[(19, 10)] = "Kurs loyihasi (ishi)"
        qatorlar[(21, 10)] = 20
        yol = _kitob_yozish(qatorlar)
        natija = kitobni_tahlil_qil(yol)
        self.assertEqual(natija.majburiy_fanlar[0].kurs_ishi, 20)

    def test_ustun_raqamlari_qatori_yoq_bolsada_yorliq_orqali_topiladi(self) -> None:
        """Ustun raqamlari qatori bo'lmasa ham yorliq orqali topilishi kerak."""
        qatorlar = _standart_jadval(
            8, "Ta'lim yo'nalishi: 60110500 - Boshlang'ich ta'lim", "4 yil", "2024-2025"
        )
        yol = _kitob_yozish(qatorlar)
        natija = kitobni_tahlil_qil(yol)
        self.assertEqual(len(natija.majburiy_fanlar), 1)

    def test_zaxira_ustun_raqami_qatoridan_topiladi(self) -> None:
        """Guruh sarlavha yorliqlari yo'q bo'lsa, mantiqiy ustun raqamlaridan topadi."""
        qatorlar = _standart_jadval(
            8, "Ta'lim yo'nalishi: 60110500 - Boshlang'ich ta'lim", "4 yil", "2024-2025"
        )
        del qatorlar[(18, 11)]
        del qatorlar[(18, 19)]
        # Mantiqiy ustun raqamlari: haftalik = 12..19, kredit = 20..27 (siljish 11).
        for i in range(8):
            qatorlar[(19, 11 + i)] = 12 + i
            qatorlar[(19, 19 + i)] = 20 + i
        yol = _kitob_yozish(qatorlar)
        natija = kitobni_tahlil_qil(yol)
        self.assertEqual(len(natija.majburiy_fanlar), 1)
        self.assertEqual(natija.majburiy_fanlar[0].semestr_kreditlari, {1: 4})


class KitobTahliliXatoTest(SimpleTestCase):
    def tearDown(self) -> None:
        while _YARATILGAN_KITOBLAR:
            _YARATILGAN_KITOBLAR.pop().unlink(missing_ok=True)
        super().tearDown()

    def test_1_00_belgisi_yoq_xato(self) -> None:
        # Fanlar jadvali umuman yo'q: langar belgi topilmaydi.
        qatorlar = {
            (2, 1): "Ta'lim yo'nalishi: 60110500 - Boshlang'ich ta'lim",
            (3, 1): "O'qish muddati - 4 yil",
            (6, 1): "2024-2025 o'quv yili",
            (7, 1): "II. O'QUV REJASI",
        }
        yol = _kitob_yozish(qatorlar)
        with self.assertRaises(TahlilXatosi):
            kitobni_tahlil_qil(yol)

    def test_oqish_muddati_yoq_xato(self) -> None:
        qatorlar = _standart_jadval(
            8, "Ta'lim yo'nalishi: 60110500 - Boshlang'ich ta'lim", "4 yil", "2024-2025"
        )
        del qatorlar[(3, 1)]
        yol = _kitob_yozish(qatorlar)
        with self.assertRaises(TahlilXatosi):
            kitobni_tahlil_qil(yol)

    def test_semestr_ustunlari_topilmasa_xato(self) -> None:
        qatorlar = _standart_jadval(
            8, "Ta'lim yo'nalishi: 60110500 - Boshlang'ich ta'lim", "4 yil", "2024-2025"
        )
        for kalit in list(qatorlar):
            qator, ustun = kalit
            if qator in (18, 19) and ustun >= 11:
                del qatorlar[kalit]
        yol = _kitob_yozish(qatorlar)
        with self.assertRaises(TahlilXatosi):
            kitobni_tahlil_qil(yol)

    def test_buzilgan_xlsx_parse_xato_beradi(self) -> None:
        with tempfile.TemporaryDirectory() as vaqtincha_papka:
            buzilgan = Path(vaqtincha_papka) / "buzilgan.xlsx"
            buzilgan.write_bytes(b"zip arxivi emas")
            with self.assertRaises(TahlilXatosi):
                kitobni_tahlil_qil(buzilgan)


class FormatlashVaCliTests(SimpleTestCase):
    def tearDown(self) -> None:
        while _YARATILGAN_KITOBLAR:
            _YARATILGAN_KITOBLAR.pop().unlink(missing_ok=True)
        super().tearDown()

    def test_markdown_yarat_majburiy_va_tanlov_fanlar(self) -> None:
        majburiy = [
            MajburiyFan(
                raqam="1.01",
                kod="FAN1",
                nom="Matematika",
                soat=120,
                auditoriya=60,
                maruza=30,
                amaliyot=30,
                laboratoriya=0,
                seminar=0,
                kurs_ishi=0,
                semestr_kreditlari={1: 4},
                semestr_haftalik_soatlar={1: 4},
            )
        ]
        tanlov = [
            TanlovFani(
                raqam="2.01",
                soat=90,
                variantlar=[
                    TanlovVarianti(
                        kod="T1",
                        nom="Algoritmlar",
                        auditoriya=45,
                        maruza=15,
                        amaliyot=30,
                        laboratoriya=0,
                        seminar=0,
                        kurs_ishi=0,
                    )
                ],
                semestr_kreditlari={2: 3},
                semestr_haftalik_soatlar={2: 3},
            )
        ]
        md = markdown_yarat(
            "Dasturiy injiniring",
            "2024",
            "BAKALAVR",
            "4 yil",
            "Kunduzgi",
            majburiy,
            tanlov,
        )
        self.assertIn("# Oquv Reja: Dasturiy injiniring", md)
        self.assertIn("## Majburiy Fanlar", md)
        self.assertIn("Matematika", md)
        self.assertIn("## Tanlov Fanlar", md)
        self.assertIn("Algoritmlar", md)
        self.assertIn("**O'quv yili:** 2024", md)

    def test_parser_main_cli_kodlari(self) -> None:
        xlsx = _kitob_yozish(
            _standart_jadval(
                8,
                "Ta'lim yo'nalishi: 60610100 - Axborot texnologiyalari",
                "4 yil",
                "2024-2025",
            )
        )
        with tempfile.TemporaryDirectory() as chiqish_papkasi:
            with patch.object(parser_asosiy, "CHIQISH_PAPKA", Path(chiqish_papkasi)):
                with patch("sys.argv", ["parser.main", str(xlsx)]):
                    self.assertEqual(parser_asosiy.asosiy(), 0)
                yozilgan = list(Path(chiqish_papkasi).glob("*.md"))
                self.assertEqual(len(yozilgan), 1)
                self.assertIn("Axborot texnologiyalari", yozilgan[0].read_text("utf-8"))

                with patch(
                    "sys.argv", ["parser.main", str(Path(chiqish_papkasi) / "yoq.xlsx")]
                ):
                    self.assertEqual(parser_asosiy.asosiy(), 1)

                yomon = Path(chiqish_papkasi) / "bad.xlsx"
                yomon.write_bytes(b"buzilgan")
                with patch("sys.argv", ["parser.main", str(yomon)]):
                    self.assertEqual(parser_asosiy.asosiy(), 1)

    def test_parser_bosh_boshliq_tanlov_qatori_va_kasr_intga(self) -> None:
        from parser.parser import _intga

        self.assertIsNone(_intga(1.5))
        self.assertIsNone(_intga(-3))
        self.assertEqual(_intga(72.0), 72)

        qatorlar = _standart_jadval(
            8,
            "Ta'lim yo'nalishi: 60610100 - Axborot texnologiyalari",
            "4 yil",
            "2024-2025",
        )
        # 3-variant qatorining raqam katagida faqat bo'shliq bo'lsa ham o'qilishi shart.
        qatorlar[(25, 1)] = "   "
        qatorlar[(25, 2)] = "TV-2.2"
        qatorlar[(25, 3)] = "Sun'iy intellekt"
        qatorlar[(26, 1)] = "Jami:"
        yol = _kitob_yozish(qatorlar)
        natija = kitobni_tahlil_qil(yol)
        self.assertEqual(len(natija.tanlov_fanlar), 1)
        self.assertEqual(len(natija.tanlov_fanlar[0].variantlar), 3)
        self.assertEqual(natija.tanlov_fanlar[0].variantlar[2].nom, "Sun'iy intellekt")

    def test_buzilgan_xml_tahlil_xatosiga_otadi(self) -> None:
        from zipfile import ZipFile

        with tempfile.TemporaryDirectory() as tmp:
            yol = Path(tmp) / "xml_buzilgan.xlsx"
            with ZipFile(yol, "w") as zf:
                zf.writestr("[Content_Types].xml", "<Types><broken>")
                zf.writestr("xl/workbook.xml", "<workbook/>")
            with self.assertRaises(TahlilXatosi):
                kitobni_tahlil_qil(yol)
