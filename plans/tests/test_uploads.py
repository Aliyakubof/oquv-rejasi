from io import BytesIO
from unittest.mock import patch
from zipfile import ZIP_DEFLATED, ZipFile

import openpyxl
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from plans.importer import ImportXato
from plans.models import OquvReja, TalimYonalishi
from plans.tests.factories import yonalish_yasa
from plans.tests.test_parser import _standart_jadval
from plans.uploads import (
    YuklashParametrlari,
    fayldan_import_qilish,
    zip_faylini_tekshir,
)


def _namuna_xlsx_baytlari() -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    qatorlar = _standart_jadval(
        8,
        "Ta'lim yo'nalishi: 60410200 - Buxgalteriya hisobi",
        "4 yil",
        "2025-2026",
    )
    for (row, col), value in qatorlar.items():
        ws.cell(row=row, column=col, value=value)
    xotira = BytesIO()
    wb.save(xotira)
    return xotira.getvalue()


def _parametrlar(**kwargs: object) -> YuklashParametrlari:
    maydonlar: dict[str, object] = {
        "talabalar_soni": 50,
        "guruhlar_soni": 2,
        "guruh_prefiksi": "BH",
        "boshlanish_yili": 2025,
        "almashtirish": False,
    }
    maydonlar.update(kwargs)
    return YuklashParametrlari(**maydonlar)


class FayldanImportTests(TestCase):
    def test_haqiqiy_fayl_import_qilinadi(self) -> None:
        if not TalimYonalishi.objects.filter(kodi="60410200").exists():
            yonalish_yasa(kodi="60410200")
        fayl = SimpleUploadedFile("BHA.xlsx", _namuna_xlsx_baytlari())

        natija = fayldan_import_qilish(fayl, _parametrlar())

        reja = OquvReja.objects.get(pk=natija.reja.pk)
        self.assertTrue(natija.yaratildi)
        self.assertGreater(natija.fan_soni, 0)
        self.assertEqual(reja.talabalar_soni, 50)
        self.assertEqual(reja.guruhlar_soni, 2)
        guruh_nomlari = list(reja.guruhlar.values_list("nomi", flat=True))
        self.assertEqual(guruh_nomlari, ["BH-2025-1", "BH-2025-2"])

    def test_notogri_fayl_import_xato(self) -> None:
        fayl = SimpleUploadedFile("reja.xlsx", b"bu excel emas")
        with self.assertRaises(ImportXato):
            fayldan_import_qilish(fayl, _parametrlar())

    def test_bosh_varaq_import_xato(self) -> None:
        kitob = openpyxl.Workbook()
        xotira = BytesIO()
        kitob.save(xotira)
        fayl = SimpleUploadedFile("bosh.xlsx", xotira.getvalue())
        with self.assertRaises(ImportXato):
            fayldan_import_qilish(fayl, _parametrlar())

    def test_soxta_sarlavhali_zip_bomba_rad_etiladi(self) -> None:
        buf = BytesIO()
        with ZipFile(buf, "w", compression=ZIP_DEFLATED) as zf:
            zf.writestr("xl/workbook.xml", "<workbook/>")
            zf.writestr("xl/katta.bin", b"A" * (128 * 1024))
        fayl = SimpleUploadedFile("bomba.xlsx", buf.getvalue())

        # Sarlavha hajmi kichik deb aldaganda ham oqim o'qishi to'xtatishi kerak.
        with ZipFile(BytesIO(buf.getvalue())) as real_zf:
            infos = real_zf.infolist()
        for inf in infos:
            inf.file_size = 1
        with patch("zipfile.ZipFile.infolist", return_value=infos):
            with self.assertRaises(ValidationError):
                zip_faylini_tekshir(
                    fayl,
                    kutilgan_kengaytma=".xlsx",
                    max_hajm=10 * 1024 * 1024,
                    max_chiqarilgan_hajm=4096,
                    zarur_fayl="xl/workbook.xml",
                )

    def test_klassifikator_xatosi_buzilgan_xlsxga_almashtirilmaydi(self) -> None:
        TalimYonalishi.objects.filter(kodi="60410200").delete()
        fayl = SimpleUploadedFile("BHA.xlsx", _namuna_xlsx_baytlari())
        with patch(
            "plans.uploads.import_reja",
            side_effect=ValueError("ichki biznes qoida xatosi"),
        ):
            with self.assertRaisesMessage(ValueError, "ichki biznes qoida xatosi"):
                fayldan_import_qilish(fayl, _parametrlar())
