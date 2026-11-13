"""Tests for consolidated exports, copy services, Excel import, alerts and commands."""

import json
import tempfile
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch
from zipfile import ZipFile

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from docx import Document
from openpyxl import Workbook, load_workbook

from accounts.excel_import import (
    oqituvchi_import_natija_excel,
    oqituvchilar_excel_import,
    oqituvchilar_namuna_excel,
    yonalishlar_excel_import,
)
from accounts.models import Department, Foydalanuvchi, OqituvchiTuri
from plans import dashboard, eksport, nusxalash
from plans.bildirishnoma import bildirishnoma_yubor
from plans.models import (
    Bildirishnoma,
    FanTuri,
    KafedraTasdiqHolati,
    KafedraYuklamaTasdiq,
    SoatTuri,
    TalimYonalishi,
    Yuklama,
)
from plans.shakl1_doc import shakl1_docx_render, shakl1_zip_yarat
from plans.tests.factories import (
    make_fan,
    make_fan_semestr,
    make_oqituvchi,
    make_reja,
    make_variant,
)


def _excel_fayl(nomi: str, qatorlar: list[list[object]]) -> SimpleUploadedFile:
    wb = Workbook()
    ws = wb.active
    for q in qatorlar:
        ws.append(q)
    buf = BytesIO()
    wb.save(buf)
    return SimpleUploadedFile(
        nomi,
        buf.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


class SvodVaShakl1Tests(TestCase):
    def test_svod_excel_uch_varaq_va_formula_himoyasi(self) -> None:
        yil = dashboard.joriy_akademik_yil()
        kaf = Department.objects.create(nomi="=CMD('calc')")
        oqit = make_oqituvchi(kafedra=kaf)
        reja = make_reja(boshlanish_yili=yil, yonalish_kodi="60610200")
        fan = make_fan(reja, kafedra=kaf)
        fs = make_fan_semestr(fan.tanlangan_variant, semestr=1)
        Yuklama.objects.create(fan_semestr=fs, tur=SoatTuri.MARUZA, oqituvchi=oqit)

        wb = load_workbook(eksport.svod_excel(yil), data_only=True)
        self.assertEqual(
            wb.sheetnames,
            ["Kafedralar kesimi", "O'qituvchilar kesimi", "Yo'nalishlar kesimi"],
        )
        ws_kaf = wb["Kafedralar kesimi"]
        nom_qiymat = str(ws_kaf.cell(row=4, column=2).value)
        self.assertTrue(nom_qiymat.startswith("'=CMD"))
        ws_yon = wb["Yo'nalishlar kesimi"]
        self.assertEqual(ws_yon.cell(row=4, column=2).value, "60610200")

    def test_shakl1_docx_va_zip_o1_sorgov(self) -> None:
        yil = dashboard.joriy_akademik_yil()
        kaf = Department.objects.create(nomi="Dasturiy muhandislik")
        oqit = make_oqituvchi(kafedra=kaf)
        reja = make_reja(boshlanish_yili=yil)
        fan = make_fan(reja, kafedra=kaf)
        fs = make_fan_semestr(fan.tanlangan_variant, semestr=1)
        Yuklama.objects.create(fan_semestr=fs, tur=SoatTuri.MARUZA, oqituvchi=oqit)

        doc = Document(shakl1_docx_render(oqit, yil))
        matn = "\n".join(p.text for p in doc.paragraphs)
        self.assertIn("1-SHAKL", matn)
        self.assertIn(str(oqit), matn)
        jadval_matn = " ".join(c.text for row in doc.tables[0].rows for c in row.cells)
        self.assertIn("Dasturlashga kirish", jadval_matn)
        self.assertIn("JAMI:", jadval_matn)

        with self.assertNumQueries(3):
            zip_buf = shakl1_zip_yarat(yil, kafedra=kaf)
        with ZipFile(zip_buf) as zf:
            nomlar = zf.namelist()
            self.assertEqual(len(nomlar), 1)
            self.assertTrue(nomlar[0].endswith("_1shakl.docx"))

    def test_shakl1_zip_bosh_bolsa_readme_yozadi(self) -> None:
        yil = dashboard.joriy_akademik_yil()
        with ZipFile(shakl1_zip_yarat(yil)) as zf:
            self.assertEqual(zf.namelist(), ["README.txt"])


class NusxalashServiceTests(TestCase):
    def test_manba_yillar_faqat_otgan_yillarni_koradi(self) -> None:
        joriy = dashboard.joriy_akademik_yil()
        otgan = joriy - 1
        kaf = Department.objects.create(nomi="Matematika")
        reja = make_reja(boshlanish_yili=otgan)
        fan = make_fan(reja, kafedra=kaf)
        make_fan_semestr(fan.tanlangan_variant, semestr=1)

        self.assertEqual(nusxalash.manba_yillar_royxati(joriy), [otgan])
        self.assertNotIn(otgan, dashboard.tanlanadigan_yillar())

    def test_ofis_nusxalash_qulfni_hurmat_qiladi_va_tanlovni_kochiradi(self) -> None:
        joriy = dashboard.joriy_akademik_yil()
        otgan = joriy - 1
        kaf1 = Department.objects.create(nomi="Ochiq kafedra")
        kaf2 = Department.objects.create(nomi="Qulflangan kafedra")

        manba_reja = make_reja(boshlanish_yili=otgan, yonalish_kodi="60610100")
        f_tan = make_fan(
            manba_reja, raqam="1.01", turi=FanTuri.TANLOV, nomi="Web dizayn"
        )
        v_tan = f_tan.variantlar.first()
        v_tan.kafedra = kaf1
        v_tan.save(update_fields=["kafedra"])
        f_tan.tanlangan_variant = v_tan
        f_tan.save(update_fields=["tanlangan_variant"])
        make_fan_semestr(v_tan, semestr=1)

        f_lock = make_fan(
            manba_reja, raqam="1.02", kafedra=kaf2, nomi="Tarmoq xavfsizligi"
        )
        make_fan_semestr(f_lock.tanlangan_variant, semestr=1)

        maqsad_reja = make_reja(boshlanish_yili=joriy, yonalish_kodi="60610100")
        m_tan = make_fan(
            maqsad_reja, raqam="1.01", turi=FanTuri.TANLOV, nomi="Web dizayn"
        )
        make_variant(m_tan, kodi="ALT-2", nomi="Mobil ilovalar")
        m_tan_v = m_tan.variantlar.get(nomi="Web dizayn")
        make_fan_semestr(m_tan_v, semestr=1)

        m_lock = make_fan(maqsad_reja, raqam="1.02", nomi="Tarmoq xavfsizligi")
        make_fan_semestr(m_lock.tanlangan_variant, semestr=1)
        KafedraYuklamaTasdiq.objects.create(
            kafedra=kaf2, akademik_yil=joriy, holat=KafedraTasdiqHolati.TASDIQLANGAN
        )

        natija = nusxalash.ofis_taqsimotini_nusxalash(otgan, joriy)
        m_tan.refresh_from_db()
        m_tan_v.refresh_from_db()
        m_lock_v = m_lock.tanlangan_variant
        m_lock_v.refresh_from_db()
        self.assertEqual(m_tan.tanlangan_variant_id, m_tan_v.pk)
        self.assertEqual(m_tan_v.kafedra_id, kaf1.pk)
        self.assertIsNone(m_lock_v.kafedra_id)
        self.assertEqual(natija.otkazildi_qulflangan, 1)

    def test_kafedra_nusxalash_guruh_va_maruzani_kochiradi(self) -> None:
        joriy = dashboard.joriy_akademik_yil()
        otgan = joriy - 1
        kaf = Department.objects.create(nomi="AI kafedrasi")
        oqit = make_oqituvchi(kafedra=kaf)

        reja1 = make_reja(
            boshlanish_yili=otgan, yonalish_kodi="60610500", guruhlar_soni=2
        )
        g1 = reja1.guruhlar.create(raqam=1, nomi="AI-25-1")
        fan1 = make_fan(reja1, kafedra=kaf, nomi="Sun'iy intellekt")
        fs1 = make_fan_semestr(fan1.tanlangan_variant, semestr=1)
        Yuklama.objects.create(fan_semestr=fs1, tur=SoatTuri.MARUZA, oqituvchi=oqit)
        Yuklama.objects.create(
            fan_semestr=fs1, tur=SoatTuri.AMALIYOT, oqituvchi=oqit, guruh=g1
        )

        reja2 = make_reja(
            boshlanish_yili=joriy, yonalish_kodi="60610500", guruhlar_soni=2
        )
        g2 = reja2.guruhlar.create(raqam=1, nomi="AI-26-1")
        fan2 = make_fan(reja2, kafedra=kaf, nomi="Sun'iy intellekt")
        fs2 = make_fan_semestr(fan2.tanlangan_variant, semestr=1)

        natija = nusxalash.kafedra_taqsimotini_nusxalash(kaf, otgan, joriy)
        self.assertEqual(natija.yaratilgan_yuklamalar, 2)
        self.assertTrue(
            Yuklama.objects.filter(
                fan_semestr=fs2, tur=SoatTuri.MARUZA, oqituvchi=oqit
            ).exists()
        )
        self.assertTrue(
            Yuklama.objects.filter(
                fan_semestr=fs2, tur=SoatTuri.AMALIYOT, oqituvchi=oqit, guruh=g2
            ).exists()
        )


class ExcelImportServiceTests(TestCase):
    def test_oqituvchilar_excel_import_va_parollar(self) -> None:
        kaf = Department.objects.create(nomi="Fizika")
        OqituvchiTuri.objects.create(nomi="Katta o'qituvchi", min_soat=500)
        mavjud = make_oqituvchi(kafedra=kaf)
        namuna_wb = load_workbook(oqituvchilar_namuna_excel())
        self.assertEqual(namuna_wb.sheetnames, ["O'qituvchilar", "Ma'lumotnoma"])

        fayl = _excel_fayl(
            "oqit.xlsx",
            [
                ["Familiya", "Ism", "Telefon", "Kafedra", "Lavozim"],
                ["Karimov", "Aziz", "998901112233", "Fizika", "Katta o'qituvchi"],
                [
                    "Eski",
                    "Odil",
                    mavjud.foydalanuvchi.telefon,
                    "Fizika",
                    "Katta o'qituvchi",
                ],
            ],
        )
        natija = oqituvchilar_excel_import(fayl)
        self.assertEqual(len(natija.yaratilganlar), 1)
        self.assertEqual(natija.otkazildi_mavjud, [mavjud.foydalanuvchi.telefon])
        yangi = Foydalanuvchi.objects.get(telefon="+998901112233")
        self.assertTrue(yangi.parol_ozgartirish_kerak)

        parol_wb = load_workbook(oqituvchi_import_natija_excel(natija.yaratilganlar))
        self.assertEqual(parol_wb.active.cell(row=2, column=3).value, "'+998901112233")

    def test_oqituvchi_import_xato_bolsa_atomik_qaytariladi(self) -> None:
        Department.objects.create(nomi="Fizika")
        OqituvchiTuri.objects.create(nomi="Dotsent", min_soat=450)
        fayl = _excel_fayl(
            "xato.xlsx",
            [
                ["Familiya", "Ism", "Telefon", "Kafedra", "Lavozim"],
                ["Aliyev", "Vali", "+998909998877", "Fizika", "Dotsent"],
                ["Xato", "Test", "123", "Yo'q Kafedra", "Dotsent"],
            ],
        )
        with self.assertRaises(ValidationError):
            oqituvchilar_excel_import(fayl)
        self.assertFalse(Foydalanuvchi.objects.filter(telefon="+998909998877").exists())

    def test_yonalishlar_excel_import(self) -> None:
        fayl = _excel_fayl(
            "yon.xlsx",
            [
                ["Kod", "Nom", "BS kod", "BS nom", "TS kod", "TS nom"],
                ["60990100", "Kompyuter ilmlari", "6", "AKT", "606", "IT"],
            ],
        )
        yaratildi, yangilandi = yonalishlar_excel_import(fayl)
        self.assertEqual((yaratildi, yangilandi), (1, 0))
        self.assertTrue(TalimYonalishi.objects.filter(kodi="60990100").exists())


class BildirishnomaVaCommandTests(TestCase):
    @override_settings(TELEGRAM_BOT_TOKEN="bot-token-123")
    @patch("plans.bildirishnoma.telegram_xabar_yubor", return_value=True)
    def test_bildirishnoma_yubor_va_telegram_on_commit(
        self, mock_tg: MagicMock
    ) -> None:
        oqit1 = make_oqituvchi()
        oqit1.foydalanuvchi.telegram_chat_id = "123456789"
        oqit1.foydalanuvchi.save(update_fields=["telegram_chat_id"])
        oqit2 = make_oqituvchi()
        oqit2.foydalanuvchi.is_active = False
        oqit2.foydalanuvchi.save(update_fields=["is_active"])

        with self.captureOnCommitCallbacks(execute=True):
            bildirishnoma_yubor(
                [oqit1.foydalanuvchi, oqit2.foydalanuvchi],
                "Sinov xabari",
                "Matn",
            )
        self.assertEqual(Bildirishnoma.objects.count(), 1)
        mock_tg.assert_called_once()
        self.assertEqual(mock_tg.call_args[0][0], "123456789")

    def test_zaxira_nusxa_buyrugi_zip_yaratadi(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            call_command("zaxira_nusxa", "--json", "--faqat-db", "--chiqish", tmp)
            arxivlar = list(Path(tmp).glob("zaxira_*.zip"))
            self.assertEqual(len(arxivlar), 1)
            with ZipFile(arxivlar[0]) as zf:
                self.assertIn("database.json", zf.namelist())

    @override_settings(HEMIS_BASE_URL="")
    def test_sync_hemis_buyrugi_konfiguratsiyasiz_xato_beradi(self) -> None:
        with self.assertRaises(CommandError):
            call_command("sync_hemis", "--url", "")

    @override_settings(HEMIS_API_KEY="kalit-abc")
    @patch("plans.hemis_client.urllib.request.urlopen")
    def test_sync_hemis_mock_bilan_malumotlarni_yuklaydi(
        self, mock_urlopen: MagicMock
    ) -> None:
        reja = make_reja(
            yonalish_kodi="60619900",
            boshlanish_yili=2025,
            talabalar_soni=50,
            guruhlar_soni=2,
        )
        javob_data = json.dumps(
            {
                "rejalar": [
                    {
                        "yonalish_kodi": "60619900",
                        "boshlanish_yili": 2025,
                        "talabalar_soni": 75,
                        "guruhlar_soni": 3,
                        "guruh_prefiksi": "KB",
                    }
                ]
            }
        ).encode("utf-8")
        cm = MagicMock()
        cm.__enter__.return_value.read.return_value = javob_data
        mock_urlopen.return_value = cm

        call_command("sync_hemis", "--url", "https://hemis.example.uz/api/v1/sync")
        mock_urlopen.assert_called_once()
        reja.refresh_from_db()
        self.assertEqual(
            (reja.talabalar_soni, reja.guruhlar_soni, reja.guruh_prefiksi),
            (75, 3, "KB"),
        )
