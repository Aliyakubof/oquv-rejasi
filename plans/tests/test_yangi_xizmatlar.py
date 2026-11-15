"""Yig'ma eksport, yildan-yilga ko'chirish, Excel import va ogohlantirish testlari."""

import json
import tempfile
from io import BytesIO, StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch
from zipfile import ZipFile

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db.models import ProtectedError
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
from plans import dashboard, eksport, nusxalash, services
from plans.bildirishnoma import bildirishnoma_yubor
from plans.models import (
    Bildirishnoma,
    DasturTopshirish,
    FanTuri,
    KafedraTasdiqHolati,
    KafedraYuklamaTasdiq,
    OquvReja,
    SoatTuri,
    TalimYonalishi,
    Yuklama,
)
from plans.shakl1_doc import shakl1_docx_render, shakl1_zip_yarat
from plans.tests.factories import (
    fan_semestr_yasa,
    fan_yasa,
    oqituvchi_yasa,
    reja_yasa,
    variant_yasa,
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
        oqit = oqituvchi_yasa(kafedra=kaf)
        reja = reja_yasa(boshlanish_yili=yil, yonalish_kodi="60610200")
        fan = fan_yasa(reja, kafedra=kaf)
        fs = fan_semestr_yasa(fan.tanlangan_variant, semestr=1)
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
        oqit = oqituvchi_yasa(kafedra=kaf)
        reja = reja_yasa(boshlanish_yili=yil)
        fan = fan_yasa(reja, kafedra=kaf)
        fs = fan_semestr_yasa(fan.tanlangan_variant, semestr=1)
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

        # Ko'p o'qituvchi bo'lganda ham so'rovlar soni O(1) (3 ta) bo'lib qoladi
        oqituvchi_yasa(kafedra=kaf)
        oqituvchi_yasa(kafedra=kaf)
        with self.assertNumQueries(3):
            shakl1_zip_yarat(yil, kafedra=kaf)

    def test_shakl1_zip_bosh_bolsa_readme_yozadi(self) -> None:
        yil = dashboard.joriy_akademik_yil()
        with ZipFile(shakl1_zip_yarat(yil)) as zf:
            self.assertEqual(zf.namelist(), ["README.txt"])


class NusxalashServiceTests(TestCase):
    def test_manba_yillar_faqat_otgan_yillarni_koradi(self) -> None:
        joriy = dashboard.joriy_akademik_yil()
        otgan = joriy - 1
        kaf = Department.objects.create(nomi="Matematika")
        reja = reja_yasa(boshlanish_yili=otgan)
        fan = fan_yasa(reja, kafedra=kaf)
        fan_semestr_yasa(fan.tanlangan_variant, semestr=1)

        self.assertEqual(nusxalash.manba_yillar_royxati(joriy), [otgan])
        self.assertNotIn(otgan, dashboard.tanlanadigan_yillar())

    def test_ofis_nusxalash_qulfni_hurmat_qiladi_va_tanlovni_kochiradi(self) -> None:
        joriy = dashboard.joriy_akademik_yil()
        otgan = joriy - 1
        kaf1 = Department.objects.create(nomi="Ochiq kafedra")
        kaf2 = Department.objects.create(nomi="Qulflangan kafedra")

        manba_reja = reja_yasa(boshlanish_yili=otgan, yonalish_kodi="60610100")
        f_tan = fan_yasa(
            manba_reja, raqam="1.01", turi=FanTuri.TANLOV, nomi="Web dizayn"
        )
        v_tan = f_tan.variantlar.first()
        v_tan.kafedra = kaf1
        v_tan.save(update_fields=["kafedra"])
        f_tan.tanlangan_variant = v_tan
        f_tan.save(update_fields=["tanlangan_variant"])
        fan_semestr_yasa(v_tan, semestr=1)

        f_lock = fan_yasa(
            manba_reja, raqam="1.02", kafedra=kaf2, nomi="Tarmoq xavfsizligi"
        )
        fan_semestr_yasa(f_lock.tanlangan_variant, semestr=1)

        maqsad_reja = reja_yasa(boshlanish_yili=joriy, yonalish_kodi="60610100")
        m_tan = fan_yasa(
            maqsad_reja, raqam="1.01", turi=FanTuri.TANLOV, nomi="Web dizayn"
        )
        variant_yasa(m_tan, kodi="ALT-2", nomi="Mobil ilovalar")
        m_tan_v = m_tan.variantlar.get(nomi="Web dizayn")
        fan_semestr_yasa(m_tan_v, semestr=1)

        m_lock = fan_yasa(maqsad_reja, raqam="1.02", nomi="Tarmoq xavfsizligi")
        fan_semestr_yasa(m_lock.tanlangan_variant, semestr=1)
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
        oqit = oqituvchi_yasa(kafedra=kaf)

        reja1 = reja_yasa(
            boshlanish_yili=otgan, yonalish_kodi="60610500", guruhlar_soni=2
        )
        g1 = reja1.guruhlar.create(raqam=1, nomi="AI-25-1")
        fan1 = fan_yasa(reja1, kafedra=kaf, nomi="Sun'iy intellekt")
        fs1 = fan_semestr_yasa(fan1.tanlangan_variant, semestr=1)
        Yuklama.objects.create(fan_semestr=fs1, tur=SoatTuri.MARUZA, oqituvchi=oqit)
        Yuklama.objects.create(
            fan_semestr=fs1, tur=SoatTuri.AMALIYOT, oqituvchi=oqit, guruh=g1
        )

        reja2 = reja_yasa(
            boshlanish_yili=joriy, yonalish_kodi="60610500", guruhlar_soni=2
        )
        g2 = reja2.guruhlar.create(raqam=1, nomi="AI-26-1")
        fan2 = fan_yasa(reja2, kafedra=kaf, nomi="Sun'iy intellekt")
        fs2 = fan_semestr_yasa(fan2.tanlangan_variant, semestr=1)

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
        mavjud = oqituvchi_yasa(kafedra=kaf)
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
        oqit1 = oqituvchi_yasa()
        oqit1.foydalanuvchi.telegram_chat_id = "123456789"
        oqit1.foydalanuvchi.save(update_fields=["telegram_chat_id"])
        oqit2 = oqituvchi_yasa()
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
    @patch("plans.hemis_client.urllib.request.build_opener")
    def test_sync_hemis_mock_bilan_malumotlarni_yuklaydi(
        self, mock_build_opener: MagicMock
    ) -> None:
        reja = reja_yasa(
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
        mock_build_opener.return_value.open.return_value = cm

        call_command("sync_hemis", "--url", "https://hemis.example.uz/api/v1/sync")
        mock_build_opener.return_value.open.assert_called_once()
        reja.refresh_from_db()
        self.assertEqual(
            (reja.talabalar_soni, reja.guruhlar_soni, reja.guruh_prefiksi),
            (75, 3, "KB"),
        )

    def test_hemis_redirect_kalitni_uzatmaydi(self) -> None:
        import urllib.error
        import urllib.request
        from http.client import HTTPMessage

        from plans.hemis_client import _YoqRedirectHandler, hemis_dan_yuklash

        req = urllib.request.Request("https://hemis.example.uz/api/v1/sync")
        with self.assertRaises(urllib.error.HTTPError):
            _YoqRedirectHandler().redirect_request(
                req, object(), 302, "Found", HTTPMessage(), "https://evil.example/"
            )
        with self.assertRaises(ValueError):
            hemis_dan_yuklash(base_url="ftp://hemis.example.uz/file")
        with override_settings(DEBUG=False):
            with self.assertRaises(ValueError):
                hemis_dan_yuklash(base_url="http://hemis.example.uz/api/v1/sync")

    def test_excel_import_zip_bomb_va_formulani_qaytaradi(self) -> None:
        from plans.uploads import zip_faylini_tekshir

        katta_buf = BytesIO()
        with ZipFile(katta_buf, "w") as zf:
            for idx in range(5):
                zf.writestr(f"xl/fayl_{idx}.xml", "x")
        fayl = SimpleUploadedFile("bomb.xlsx", katta_buf.getvalue())
        with self.assertRaises(ValidationError):
            zip_faylini_tekshir(
                fayl,
                kutilgan_kengaytma=".xlsx",
                max_hajm=10 * 1024 * 1024,
                max_fayl_soni=2,
            )

        from accounts.excel_import import _xavfsiz

        self.assertEqual(_xavfsiz(" =1+1"), "' =1+1")


class Stage2BiznesVaQulflashTests(TestCase):
    def test_ofis_nusxa_talim_shakli_va_tanlanmagan_variantni_ajratadi(self) -> None:
        joriy = dashboard.joriy_akademik_yil()
        otgan = joriy - 1
        kaf = Department.objects.create(nomi="Kaf-A")

        m_kunduzgi = reja_yasa(
            boshlanish_yili=otgan, yonalish_kodi="60619901", talim_shakli="Kunduzgi"
        )
        m_fan = fan_yasa(
            m_kunduzgi, raqam="1.01", turi=FanTuri.TANLOV, nomi="Kiberxavfsizlik"
        )
        mv = m_fan.variantlar.first()
        assert mv is not None
        mv.kafedra = kaf
        mv.save(update_fields=["kafedra"])
        m_fan.tanlangan_variant = mv
        m_fan.save(update_fields=["tanlangan_variant"])
        fan_semestr_yasa(mv, semestr=1)

        t_sirtqi = reja_yasa(
            boshlanish_yili=joriy, yonalish_kodi="60619901", talim_shakli="Sirtqi"
        )
        ts_fan = fan_yasa(
            t_sirtqi, raqam="1.01", turi=FanTuri.TANLOV, nomi="Kiberxavfsizlik"
        )
        fan_semestr_yasa(ts_fan.variantlar.first(), semestr=1)

        t_kunduzgi = reja_yasa(
            boshlanish_yili=joriy, yonalish_kodi="60619901", talim_shakli="Kunduzgi"
        )
        tk_fan = fan_yasa(
            t_kunduzgi, raqam="1.01", turi=FanTuri.TANLOV, nomi="Kiberxavfsizlik"
        )
        tk_v1 = tk_fan.variantlar.first()
        tk_v2 = variant_yasa(tk_fan, kodi="ALT-X", nomi="Kiberxavfsizlik")
        tk_fan.tanlangan_variant = tk_v1
        tk_fan.save(update_fields=["tanlangan_variant"])
        fan_semestr_yasa(tk_v2, semestr=1)

        nusxalash.ofis_taqsimotini_nusxalash(otgan, joriy)
        ts_fan.refresh_from_db()
        tk_v2.refresh_from_db()
        self.assertIsNone(ts_fan.tanlangan_variant_id)
        self.assertIsNone(tk_v2.kafedra_id)

    def test_qulflangan_kafedra_ozgartirishlarini_bloklaydi(self) -> None:
        joriy = dashboard.joriy_akademik_yil()
        kaf1 = Department.objects.create(nomi="Qulf Kaf 1")
        kaf2 = Department.objects.create(nomi="Qulf Kaf 2")
        reja = reja_yasa(boshlanish_yili=joriy, guruhlar_soni=2)
        services.guruhlarni_sinxronlash(reja)
        fan = fan_yasa(reja, raqam="2.01", turi=FanTuri.TANLOV)
        v = fan.variantlar.first()
        assert v is not None
        services.variantni_tanlash(fan, v)
        services.kafedraga_biriktirish(v, kaf1)
        alt = variant_yasa(fan, kodi="B-2", nomi="Muqobil")
        fs = fan_semestr_yasa(v, semestr=1)
        oqit = oqituvchi_yasa(kafedra=kaf1)
        KafedraYuklamaTasdiq.objects.create(
            kafedra=kaf1, akademik_yil=joriy, holat=KafedraTasdiqHolati.TASDIQLANGAN
        )

        with self.assertRaises(ValidationError):
            services.variantni_tanlash(fan, alt)
        with self.assertRaises(ValidationError):
            services.kafedraga_biriktirish(v, kaf2)
        with self.assertRaises(ValidationError):
            services.kafedraga_ommaviy_biriktirish([v.pk], kaf2)
        with self.assertRaises(ValidationError):
            services.guruhlarga_ommaviy_taqsimlash(fs, oqit, SoatTuri.AMALIYOT)

    def test_yuklama_kamomadi_va_taqsimlangan_none_qoldiq(self) -> None:
        joriy = dashboard.joriy_akademik_yil()
        kaf = Department.objects.create(nomi="Faolsiz Kaf")
        reja = reja_yasa(boshlanish_yili=joriy, guruhlar_soni=None)
        fan = fan_yasa(reja, kafedra=kaf)
        variant = fan.tanlangan_variant
        assert variant is not None
        fs = fan_semestr_yasa(variant, semestr=1)
        oqit = oqituvchi_yasa(kafedra=kaf)
        Yuklama.objects.create(fan_semestr=fs, tur=SoatTuri.MARUZA, oqituvchi=oqit)
        oqit.foydalanuvchi.is_active = False
        oqit.foydalanuvchi.save(update_fields=["is_active"])

        holatlar = services.yuklama_kamomadi(joriy, kafedra=kaf)
        self.assertEqual([h.oqituvchi.pk for h in holatlar], [oqit.pk])

        talab = services.TalabSatri(
            fan_semestr=fs, tur=SoatTuri.AMALIYOT, talab_soat=None, taqsimlangan_soat=0
        )
        satr = dashboard.SemestrKesimSatri(
            fan=fan,
            variant=variant,
            fan_semestr=fs,
            tanlanmagan=False,
            talab_satrlari=[talab],
            yuklamalar=[],
        )
        self.assertFalse(satr.taqsimlangan)

    def test_dastur_topshirish_variant_protect(self) -> None:
        kaf = Department.objects.create(nomi="Protect Kaf")
        reja = reja_yasa()
        fan = fan_yasa(reja, kafedra=kaf)
        variant = fan.tanlangan_variant
        assert variant is not None
        oqit = oqituvchi_yasa(kafedra=kaf)
        DasturTopshirish.objects.create(
            variant=variant,
            urinish_raqami=1,
            oqituvchi=oqit,
            fayl="dasturlar/test_protect.docx",
        )
        with self.assertRaises(ProtectedError):
            reja.delete()

    def test_kafedra_nusxa_kodi_va_qulflanganni_tekshiradi(self) -> None:
        joriy = dashboard.joriy_akademik_yil()
        otgan = joriy - 1
        kaf = Department.objects.create(nomi="Kod Ajrat Kaf")
        o1 = oqituvchi_yasa(kafedra=kaf)
        o2 = oqituvchi_yasa(kafedra=kaf)

        r1 = reja_yasa(boshlanish_yili=otgan, yonalish_kodi="60619902")
        f1 = fan_yasa(r1, raqam="1.01", kafedra=kaf, kodi="FAN-A", nomi="Dasturlash")
        fs1 = fan_semestr_yasa(f1.tanlangan_variant, semestr=1)
        Yuklama.objects.create(fan_semestr=fs1, tur=SoatTuri.MARUZA, oqituvchi=o1)
        f2 = fan_yasa(r1, raqam="1.02", kafedra=kaf, kodi="FAN-B", nomi="Dasturlash")
        fs2 = fan_semestr_yasa(f2.tanlangan_variant, semestr=1)
        Yuklama.objects.create(fan_semestr=fs2, tur=SoatTuri.MARUZA, oqituvchi=o2)

        r2 = reja_yasa(boshlanish_yili=joriy, yonalish_kodi="60619902")
        tf = fan_yasa(
            r2, raqam="1.01", kafedra=kaf, kodi="YANGI-KOD", nomi="Dasturlash"
        )
        tfs = fan_semestr_yasa(tf.tanlangan_variant, semestr=1)
        natija = nusxalash.kafedra_taqsimotini_nusxalash(kaf, otgan, joriy)
        self.assertEqual(natija.yaratilgan_yuklamalar, 1)
        self.assertEqual(
            Yuklama.objects.get(fan_semestr=tfs, tur=SoatTuri.MARUZA).oqituvchi_id,
            o1.pk,
        )
        KafedraYuklamaTasdiq.objects.create(
            kafedra=kaf, akademik_yil=joriy, holat=KafedraTasdiqHolati.TASDIQDA
        )
        with self.assertRaises(ValidationError):
            nusxalash.kafedra_taqsimotini_nusxalash(kaf, otgan, joriy)

    def test_yonalish_bulk_upsert_va_kesilgan_takror_tekshiruvi(self) -> None:
        wb = Workbook()
        ws = wb.active
        ws.append(["Kodi", "Nomi", "BS kodi", "BS nomi", "TS kodi", "TS nomi"])
        ws.append(["12345678901234567890A", "Yo'nalish 1", "6", "BS", "60", "TS"])
        ws.append(["12345678901234567890B", "Yo'nalish 2", "6", "BS", "60", "TS"])
        buf = BytesIO()
        wb.save(buf)
        with self.assertRaises(ValidationError):
            yonalishlar_excel_import(SimpleUploadedFile("yon.xlsx", buf.getvalue()))

        wb2 = Workbook()
        ws2 = wb2.active
        ws2.append(["Kodi", "Nomi", "BS kodi", "BS nomi", "TS kodi", "TS nomi"])
        for i in range(10):
            ws2.append([f"6099{i:04d}", f"Nom {i}", "6", "BS", "60", "TS"])
        buf2 = BytesIO()
        wb2.save(buf2)
        with self.assertNumQueries(4):
            yaratildi, yangilandi = yonalishlar_excel_import(
                SimpleUploadedFile("yon_ok.xlsx", buf2.getvalue())
            )
        self.assertEqual((yaratildi, yangilandi), (10, 0))

    def test_import_reja_cli_buyrugi(self) -> None:
        from plans.tests.test_parser import _standart_jadval

        with self.assertRaises(CommandError):
            call_command("import_reja", "mavjud_emas_reja.xlsx", stderr=StringIO())

        TalimYonalishi.objects.create(
            kodi="60610999",
            nomi="CLI Yo'nalish",
            bilim_sohasi_kodi="6",
            bilim_sohasi_nomi="BS",
            talim_sohasi_kodi="60",
            talim_sohasi_nomi="TS",
        )
        rows = _standart_jadval(
            8,
            "Ta'lim yo'nalishi: 60610999 - CLI Yo'nalish",
            "4 yil",
            "2024-2025",
        )
        wb = Workbook()
        ws = wb.active
        for (r, c), v in rows.items():
            ws.cell(row=r, column=c, value=v)
        with tempfile.TemporaryDirectory() as tmpdir:
            xlsx_path = Path(tmpdir) / "cli_reja.xlsx"
            wb.save(xlsx_path)
            wb.close()
            call_command("import_reja", str(xlsx_path), stdout=StringIO())
            self.assertTrue(OquvReja.objects.filter(yonalish_kodi="60610999").exists())

    def test_topshirilmagan_dasturlar_kop_semestrli_va_yil_filtri(self) -> None:
        from plans.dastur.topshirish import (
            topshirilmagan_dasturlar,
            topshirilmagan_dasturlar_soni,
        )

        yil = dashboard.joriy_akademik_yil()
        kaf = Department.objects.create(nomi="Dastur Kaf")
        o1 = oqituvchi_yasa(kafedra=kaf)
        o2 = oqituvchi_yasa(kafedra=kaf)
        reja = reja_yasa(boshlanish_yili=yil)
        fan = fan_yasa(reja, kafedra=kaf)
        fs1 = fan_semestr_yasa(fan.tanlangan_variant, semestr=1)
        fs2 = fan_semestr_yasa(fan.tanlangan_variant, semestr=2)
        Yuklama.objects.create(fan_semestr=fs1, tur=SoatTuri.MARUZA, oqituvchi=o1)
        Yuklama.objects.create(fan_semestr=fs2, tur=SoatTuri.MARUZA, oqituvchi=o2)

        royxat = topshirilmagan_dasturlar(kafedra_id=kaf.pk, yil=yil)
        self.assertEqual(len(royxat), 2)
        self.assertEqual(topshirilmagan_dasturlar_soni(kafedra_id=kaf.pk, yil=yil), 2)
        self.assertEqual(
            topshirilmagan_dasturlar_soni(kafedra_id=kaf.pk, yil=yil + 5), 0
        )
