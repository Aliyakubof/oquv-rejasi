from io import BytesIO

import openpyxl
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from plans.importer import ImportXato
from plans.models import OquvReja, TalimYonalishi
from plans.tests.factories import make_yonalish
from plans.tests.test_parser import _standard_layout
from plans.uploads import YuklashParametrlari, fayldan_import_qilish


def _namuna_xlsx_baytlari() -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    qatorlar = _standard_layout(
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
        "replace": False,
    }
    maydonlar.update(kwargs)
    return YuklashParametrlari(**maydonlar)


class FayldanImportTests(TestCase):
    def test_haqiqiy_fayl_import_qilinadi(self) -> None:
        if not TalimYonalishi.objects.filter(kodi="60410200").exists():
            make_yonalish(kodi="60410200")
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
