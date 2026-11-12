"""Regression tests for Excel export hardening, audit IP/object tracking,
dastur rendering/workflow guards, parser validation, and test MEDIA_ROOT isolation."""

import math
import tempfile
from io import BytesIO
from pathlib import Path
from unittest import mock

import openpyxl
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from docx import Document
from docx.oxml.ns import qn

from accounts.models import Department, Foydalanuvchi, OqituvchiProfil, OqituvchiTuri
from parser.models import ParseError
from parser.parser import _to_float, parse_workbook
from plans import dashboard
from plans.audit import audit_yoz
from plans.dastur.service import dastur_render
from plans.dastur.topshirish import (
    dastur_qabul_qilish,
    dastur_rad_etish,
    dastur_topshirish,
)
from plans.models import (
    AuditAmali,
    DasturTopshirish,
    SoatTuri,
    TopshirishHolati,
    Yuklama,
)
from plans.tests.factories import (
    make_fan,
    make_fan_semestr,
    make_oqituvchi,
    make_reja,
)
from web.tests.helpers import login, office_admin_yarat


class EksportXavfsizlikTests(TestCase):
    def test_formula_va_nazorat_belgilari_ekranlanadi_ikkinchi_varaq_keng(self) -> None:
        yil = dashboard.joriy_akademik_yil()
        kafedra = Department.objects.create(nomi="@EvilDept")
        turi = OqituvchiTuri.objects.create(nomi="+Prof", min_soat=300)
        foyd = Foydalanuvchi.objects.create_user(
            telefon="+998901234567",
            password="parol-123",
            first_name="=SUM(1,2)",
            last_name="cmd\x00\x07Test",
        )
        profil = OqituvchiProfil.objects.create(
            foydalanuvchi=foyd, kafedra=kafedra, turi=turi
        )
        reja = make_reja(boshlanish_yili=yil)
        fan = make_fan(reja, kafedra=kafedra, nomi='=HYPERLINK("http://x")')
        fs = make_fan_semestr(fan.tanlangan_variant, semestr=1)
        Yuklama.objects.create(fan_semestr=fs, tur=SoatTuri.MARUZA, oqituvchi=profil)

        login(self.client, office_admin_yarat())
        javob = self.client.get(reverse("office:oqituvchi_excel"), {"yil": yil})
        self.assertEqual(javob.status_code, 200)

        xlsx_baytlar = b"".join(javob.streaming_content)
        wb = openpyxl.load_workbook(BytesIO(xlsx_baytlar))
        ws1, ws2 = wb.worksheets[0], wb.worksheets[1]
        matnlar1 = [
            v
            for row in ws1.iter_rows(values_only=True)
            for v in row
            if isinstance(v, str)
        ]
        self.assertIn("'=SUM(1,2) cmdTest", matnlar1)
        self.assertIn("'+Prof", matnlar1)
        self.assertIn("'@EvilDept", matnlar1)
        self.assertNotIn("\x00", "".join(matnlar1))

        matnlar2 = [v for row in ws2.iter_rows(values_only=True) for v in row if v]
        self.assertTrue(
            any(isinstance(v, str) and v.startswith("'=HYPERLINK") for v in matnlar2)
        )
        for col_letter in ("A", "B", "C", "D", "E", "F", "G"):
            kenglik = ws2.column_dimensions[col_letter].width
            self.assertIsNotNone(kenglik)
            self.assertGreaterEqual(kenglik, 10)


class AuditLogTests(TestCase):
    def setUp(self) -> None:
        self.rf = RequestFactory()

    def test_ishonchsiz_xff_e_tiborga_olinmaydi(self) -> None:
        req = self.rf.post("/", REMOTE_ADDR="10.0.0.5", HTTP_X_FORWARDED_FOR="1.2.3.4")
        req.user = AnonymousUser()
        yozuv = audit_yoz(AuditAmali.YARATILDI, "Sinov", request=req)
        self.assertEqual(yozuv.ip_manzil, "10.0.0.5")

    @override_settings(TRUST_X_FORWARDED_FOR=True, TRUSTED_PROXY_IPS=["127.0.0.1"])
    def test_ishonchli_va_begona_proksi_ajratiladi(self) -> None:
        ishonchli = self.rf.post(
            "/",
            REMOTE_ADDR="127.0.0.1",
            HTTP_X_FORWARDED_FOR="8.8.8.8, 203.0.113.9, 127.0.0.1",
        )
        ishonchli.user = AnonymousUser()
        self.assertEqual(
            audit_yoz(AuditAmali.YARATILDI, "A", request=ishonchli).ip_manzil,
            "203.0.113.9",
        )
        begona = self.rf.post(
            "/", REMOTE_ADDR="10.9.9.9", HTTP_X_FORWARDED_FOR="8.8.8.8"
        )
        begona.user = AnonymousUser()
        self.assertEqual(
            audit_yoz(AuditAmali.YARATILDI, "B", request=begona).ip_manzil,
            "10.9.9.9",
        )

    def test_obyekt_id_nol_va_uzun_nom_qisqartiriladi(self) -> None:
        yozuv = audit_yoz(
            AuditAmali.TAHRIRLANDI,
            "Nol id sinovi",
            model_nomi="M" * 80,
            obyekt_id=0,
        )
        self.assertEqual(yozuv.obyekt_id, "0")
        self.assertEqual(len(yozuv.model_nomi), 60)


class DasturXavfsizlikTests(TestCase):
    def setUp(self) -> None:
        self.kafedra = Department.objects.create(nomi="IT & AI <Lab>")
        self.reja = make_reja(boshlanish_yili=dashboard.joriy_akademik_yil())
        self.fan = make_fan(
            self.reja,
            kafedra=self.kafedra,
            nomi="C++ <Algorithms> & Systems",
            maruza_soat=0,
            amaliyot_soat=0,
            laboratoriya_soat=0,
            seminar_soat=16,
        )
        self.variant = self.fan.tanlangan_variant
        self.fs = make_fan_semestr(
            self.variant,
            semestr=1,
            maruza_soat=0,
            amaliyot_soat=0,
            laboratoriya_soat=0,
            seminar_soat=16,
        )

    def test_xml_maxsus_belgilari_va_faqat_seminar_buzilmaydi(self) -> None:
        doc = Document(dastur_render(self.variant))
        barcha_matn = "\n".join(
            cell.text
            for jadval in doc.tables
            for row in jadval.rows
            for cell in row.cells
        )
        self.assertIn("C++ <Algorithms> & Systems", barcha_matn)

        jadval1 = doc.tables[2]
        j1_matn = "\n".join(c.text for r in jadval1.rows for c in r.cells)
        self.assertIn("Seminar", j1_matn)
        for keraksiz in ("Ma’ruza", "Amaliy", "Lab-ya"):
            self.assertNotIn(keraksiz, j1_matn)
        kengliklar = [
            int(gc.get(qn("w:w")))
            for gc in jadval1._tbl.find(qn("w:tblGrid")).findall(qn("w:gridCol"))
        ]
        self.assertEqual(sum(kengliklar), 9961)

    def test_eski_urinish_rad_va_db_constraint(self) -> None:
        oqituvchi = make_oqituvchi(kafedra=self.kafedra)
        Yuklama.objects.create(
            fan_semestr=self.fs, tur=SoatTuri.MARUZA, oqituvchi=oqituvchi
        )
        fayl = SimpleUploadedFile("d.docx", b"abc")
        v1 = dastur_topshirish(self.variant, oqituvchi, fayl)
        admin = office_admin_yarat()
        dastur_rad_etish(v1, admin, "Kamchilik bor")
        v2 = dastur_topshirish(
            self.variant, oqituvchi, SimpleUploadedFile("d2.docx", b"xyz")
        )

        with self.assertRaises(ValidationError):
            dastur_qabul_qilish(v1, admin)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                DasturTopshirish.objects.create(
                    variant=self.variant,
                    urinish_raqami=v2.urinish_raqami + 1,
                    oqituvchi=oqituvchi,
                    fayl=SimpleUploadedFile("d3.docx", b"dup"),
                    holat=TopshirishHolati.KUTILMOQDA,
                    yuborilgan_vaqt=timezone.now(),
                )


class ParserVaMuhitTests(SimpleTestCase):
    def test_to_float_chegara_holatlari(self) -> None:
        for yaroqsiz in (True, False, "nan", "inf", "-inf", math.nan, math.inf):
            self.assertIsNone(_to_float(yaroqsiz))
        self.assertEqual(_to_float("3,5"), 3.5)

    def test_bosh_yoki_maruzasiz_kitob_xato_kotaradi(self) -> None:
        bosh_wb = openpyxl.Workbook()
        bosh_wb._sheets.clear()
        with mock.patch("parser.parser.openpyxl.load_workbook", return_value=bosh_wb):
            with self.assertRaises(ParseError):
                parse_workbook(Path("dummy.xlsx"))

        with tempfile.TemporaryDirectory() as tmp:
            maruzasiz_yoli = Path(tmp) / "maruzasiz.xlsx"
            wb2 = openpyxl.Workbook()
            ws = wb2.active
            ws.cell(row=2, column=1, value="Ta'lim yo'nalishi: 60610100 - Test")
            ws.cell(row=3, column=1, value="O'qish muddati - 4 yil")
            ws.cell(row=6, column=1, value="2024-2025 o'quv yili")
            ws.cell(row=18, column=7, value="Auditoriya mashg'ulotlari")
            ws.cell(row=19, column=8, value="Seminar")
            ws.cell(row=20, column=1, value="1.00")
            wb2.save(maruzasiz_yoli)
            with self.assertRaises(ParseError):
                parse_workbook(maruzasiz_yoli)

    def test_media_root_test_papka_ichida(self) -> None:
        temp_qism = Path(tempfile.gettempdir()).resolve()
        media_qism = Path(settings.MEDIA_ROOT).resolve()
        self.assertTrue(media_qism.is_relative_to(temp_qism))
        self.assertNotEqual(media_qism, (Path(settings.BASE_DIR) / "media").resolve())
