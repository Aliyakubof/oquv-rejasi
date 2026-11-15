"""Xavfsizlik middleware, RBAC izolyatsiyasi, N+1 cheklovlari, yuklama qulfi,
jonli yangilanish va UI filtrlari bo'yicha regressiya testlari."""

from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import connection
from django.test import RequestFactory, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from accounts.models import Department, OqituvchiProfil, Rol
from accounts.phone import validate_uzbek_phone
from plans import dashboard, services
from plans.audit import sorovdan_ip
from plans.models import KafedraYuklamaTasdiq, SoatTuri
from plans.tests.factories import (
    fan_semestr_yasa,
    fan_yasa,
    oqituvchi_yasa,
    reja_yasa,
)
from web.templatetags.ui import bosh_harflar, foiz
from web.tests.helpers import (
    foydalanuvchi_yarat,
    mudir_yarat,
    ofis_admin_yarat,
    oqituvchi_yarat,
    tizimga_kir,
)
from web.views.jonli import holat_versiyasi


class XavfsizlikVaRuxsatTests(TestCase):
    def setUp(self) -> None:
        self.yil = dashboard.joriy_akademik_yil()
        self.mudir = mudir_yarat()
        self.kafedra = self.mudir.oqituvchi_profil.kafedra

    def test_faolsiz_foydalanuvchi_middleware_chiqaradi_va_htmx_401(self) -> None:
        tizimga_kir(self.client, self.mudir)
        self.mudir.is_active = False
        self.mudir.save(update_fields=["is_active"])

        oddiy = self.client.get(reverse("kafedra:dashboard"))
        self.assertRedirects(
            oddiy, f"{reverse('kirish')}?next={reverse('kafedra:dashboard')}"
        )

        tizimga_kir(self.client, self.mudir)
        htmx = self.client.get(reverse("kafedra:dashboard"), HTTP_HX_REQUEST="true")
        self.assertEqual(htmx.status_code, 401)
        self.assertEqual(htmx["HX-Redirect"], reverse("kirish"))

    def test_reja_detail_notogri_tab_va_sem_tozalanadi(self) -> None:
        reja = reja_yasa(boshlanish_yili=self.yil)
        fan = fan_yasa(reja, kafedra=self.kafedra)
        fan_semestr_yasa(fan.tanlangan_variant, semestr=1)
        tizimga_kir(self.client, ofis_admin_yarat())

        url = reverse("office:reja_detail", args=[reja.pk])
        javob = self.client.get(url, {"tab": "<script>alert(1)</script>", "sem": "bad"})
        self.assertEqual(javob.status_code, 200)
        self.assertEqual(javob.context["tab"], "jadval")
        self.assertEqual(javob.context["tanlangan_semestr"], 1)
        self.assertNotContains(javob, "<script>alert(1)</script>")

    def test_mudir_office_admin_profilini_tahrirlay_olmaydi(self) -> None:
        admin = ofis_admin_yarat()
        turi = self.mudir.oqituvchi_profil.turi
        admin_profil = OqituvchiProfil.objects.create(
            foydalanuvchi=admin, kafedra=self.kafedra, turi=turi
        )
        tizimga_kir(self.client, self.mudir)
        javob = self.client.get(
            reverse("kafedra:oqituvchi_tahrir", args=[admin_profil.pk])
        )
        self.assertEqual(javob.status_code, 404)

    @override_settings(DEBUG=True)
    def test_dev_panel_mudir_va_oqituvchiga_taqiqlanadi(self) -> None:
        tizimga_kir(self.client, self.mudir)
        self.assertEqual(self.client.get(reverse("dev:panel")).status_code, 403)
        tizimga_kir(self.client, oqituvchi_yarat(kafedra=self.kafedra))
        self.assertEqual(
            self.client.post(
                reverse("dev:almashtirish"), {"foydalanuvchi": self.mudir.pk}
            ).status_code,
            403,
        )

    def test_office_admin_superadmin_hisobini_tahrirlay_va_ochira_olmaydi(self) -> None:
        admin = ofis_admin_yarat()
        super_user = foydalanuvchi_yarat(Rol.SUPERADMIN)
        super_prof = OqituvchiProfil.objects.create(
            foydalanuvchi=super_user,
            kafedra=self.kafedra,
            turi=self.mudir.oqituvchi_profil.turi,
        )
        tizimga_kir(self.client, admin)

        r_get = self.client.get(
            reverse("office:oqituvchi_tahrir", args=[super_prof.pk])
        )
        self.assertEqual(r_get.status_code, 404)

        r_del = self.client.post(
            reverse("office:oqituvchi_ochirish", args=[super_prof.pk]),
            follow=True,
        )
        self.assertContains(r_del, "Superadmin hisobini")
        super_user.refresh_from_db()
        self.assertTrue(super_user.is_active)

    @override_settings(TRUST_X_FORWARDED_FOR=True, TRUSTED_PROXY_IPS=[])
    def test_bosh_trusted_proxy_xff_ishonchsiz(self) -> None:
        req = RequestFactory().get(
            "/", REMOTE_ADDR="10.0.0.5", HTTP_X_FORWARDED_FOR="1.2.3.4"
        )
        req.user = AnonymousUser()
        self.assertEqual(sorovdan_ip(req), "10.0.0.5")

    @override_settings(LOGIN_MAX_URINISH=2, LOGIN_BLOK_SONIYA=120)
    def test_bitta_foydalanuvchi_bloklansa_boshqasi_kira_oladi(self) -> None:
        cache.clear()
        oqit1 = oqituvchi_yarat(kafedra=self.kafedra)
        oqit2 = oqituvchi_yarat(kafedra=self.kafedra)
        for _ in range(2):
            self.client.post(
                reverse("kirish"), {"username": oqit1.telefon, "password": "xato"}
            )
        r_blok = self.client.post(
            reverse("kirish"), {"username": oqit1.telefon, "password": "xato"}
        )
        self.assertEqual(r_blok.status_code, 429)

        r_boshqa = self.client.post(
            reverse("kirish"),
            {"username": oqit2.telefon, "password": "test-parol-123"},
        )
        self.assertEqual(r_boshqa.status_code, 302)
        cache.clear()


class OrmVaTasdiqTests(TestCase):
    def setUp(self) -> None:
        self.yil = dashboard.joriy_akademik_yil()
        self.mudir = mudir_yarat()
        self.kafedra = self.mudir.oqituvchi_profil.kafedra

    def test_kafedra_dashboard_get_bazaga_yozmaydi(self) -> None:
        tizimga_kir(self.client, self.mudir)
        javob = self.client.get(reverse("kafedra:dashboard"))
        self.assertEqual(javob.status_code, 200)
        self.assertEqual(KafedraYuklamaTasdiq.objects.count(), 0)

    def test_qayta_yuborishda_tasdiqlagan_tozalanadi(self) -> None:
        admin = ofis_admin_yarat()
        services.yuklamani_tasdiqqa_yuborish(self.kafedra, self.yil, "V1")
        services.yuklamani_tasdiqlash(self.kafedra, self.yil, admin, "Ok")
        services.yuklamani_qaytarish(self.kafedra, self.yil, admin, "Tuzating")
        qayta = services.yuklamani_tasdiqqa_yuborish(self.kafedra, self.yil, "V2")
        self.assertIsNone(qayta.tasdiqlagan)
        self.assertIsNone(qayta.tasdiqlangan_vaqt)

    def test_n_plus_1_sorovlar_soni_cheklangan(self) -> None:
        reja = reja_yasa(boshlanish_yili=self.yil)
        services.guruhlarni_sinxronlash(reja)
        fan1 = fan_yasa(reja, raqam="1.01", kafedra=self.kafedra)
        fan_semestr_yasa(fan1.tanlangan_variant, semestr=1)

        tizimga_kir(self.client, self.mudir)

        def _count(url: str) -> int:
            with CaptureQueriesContext(connection) as ctx:
                self.client.get(url)
            return len(ctx)

        k_kichik = _count(reverse("kafedra:dashboard"))
        for idx in range(2, 10):
            fan = fan_yasa(reja, raqam=f"1.{idx:02d}", kafedra=self.kafedra)
            fan_semestr_yasa(fan.tanlangan_variant, semestr=1)
        k_katta = _count(reverse("kafedra:dashboard"))
        self.assertLessEqual(abs(k_katta - k_kichik), 1)

        admin = ofis_admin_yarat()
        tizimga_kir(self.client, admin)
        o_katta = _count(reverse("office:dashboard"))
        for idx in range(10, 18):
            fan = fan_yasa(reja, raqam=f"1.{idx:02d}", kafedra=self.kafedra)
            fan_semestr_yasa(fan.tanlangan_variant, semestr=1)
        o_juda_katta = _count(reverse("office:dashboard"))
        self.assertLessEqual(abs(o_juda_katta - o_katta), 1)

    def test_jonli_holat_anonim_401_va_ommaviy_taqsimot_kesh_yangilanadi(self) -> None:
        anonim = self.client.get(reverse("jonli_holat"))
        self.assertEqual(anonim.status_code, 401)

        reja = reja_yasa(boshlanish_yili=self.yil)
        services.guruhlarni_sinxronlash(reja)
        fan = fan_yasa(reja, kafedra=self.kafedra)
        fs = fan_semestr_yasa(fan.tanlangan_variant, semestr=1)
        oqituvchi = oqituvchi_yasa(kafedra=self.kafedra)

        v1 = holat_versiyasi()
        services.guruhlarga_ommaviy_taqsimlash(fs, oqituvchi, SoatTuri.AMALIYOT)
        v2 = holat_versiyasi()
        self.assertNotEqual(v1, v2)

        cache.clear()
        tizimga_kir(self.client, self.mudir)
        for _ in range(60):
            self.assertEqual(self.client.get(reverse("jonli_holat")).status_code, 200)
        self.assertEqual(self.client.get(reverse("jonli_holat")).status_code, 429)
        cache.clear()

    def test_last_login_jonli_keshni_ochirmaydi_va_htmx_xabar_sorgovisiz(self) -> None:
        from django.utils import timezone

        from plans.services import JONLI_KESH_KALITI

        cache.clear()
        v1 = holat_versiyasi()
        self.assertEqual(cache.get(JONLI_KESH_KALITI), v1)
        self.mudir.last_login = timezone.now()
        self.mudir.save(update_fields=["last_login"])
        self.assertEqual(cache.get(JONLI_KESH_KALITI), v1)

        tizimga_kir(self.client, self.mudir)
        with CaptureQueriesContext(connection) as ctx:
            self.client.get(reverse("parol_ozgartirish"), HTTP_HX_REQUEST="true")
        sql = " ".join(q["sql"] for q in ctx)
        self.assertNotIn("plans_bildirishnoma", sql)


class UiVaTelefonTests(TestCase):
    def test_ui_filtrlar_apostrof_va_cheksiz_foiz(self) -> None:
        self.assertEqual(bosh_harflar("O'zbekiston G‘afur"), "OG")
        self.assertEqual(bosh_harflar("Sa’dullaʻ Boburʼ"), "SB")
        self.assertEqual(foiz(150, 100), 150)
        self.assertEqual(foiz(-5, 100), 0)
        self.assertEqual(foiz(10, 0), 0)

    def test_navbar_va_oqituvchi_excel_oob_shablonlari(self) -> None:
        admin = ofis_admin_yarat()
        Department.objects.create(nomi="Matematika")
        tizimga_kir(self.client, admin)
        javob = self.client.get(reverse("office:oqituvchi_list"))
        self.assertEqual(javob.status_code, 200)
        for belgi in (
            'class="navbar-toggle"',
            'id="htmx-yuklanish"',
            'id="app-messages"',
            'id="oqituvchi-excel-btn"',
            'hx-select-oob="#oqituvchi-excel-btn"',
        ):
            self.assertContains(javob, belgi)

    def test_telefon_validator_ozbek_tilida_xato_beradi(self) -> None:
        with self.assertRaises(ValidationError) as ctx:
            validate_uzbek_phone("123")
        matn = str(ctx.exception)
        self.assertIn("998", matn)
        self.assertNotIn("Phone number must", matn)

    def test_healthcheck_holatlari_200_va_503(self) -> None:
        ok = self.client.get(reverse("healthcheck"))
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.json()["status"], "ok")

        with patch("web.views.health._baza_tekshir", return_value=False):
            db_xato = self.client.get(reverse("healthcheck"))
        self.assertEqual(db_xato.status_code, 503)
        self.assertEqual(
            db_xato.json(), {"status": "degraded", "db": "error", "cache": "ok"}
        )

        with patch("web.views.health._kesh_tekshir", return_value=False):
            kesh_xato = self.client.get(reverse("healthcheck"))
        self.assertEqual(kesh_xato.status_code, 503)
        self.assertEqual(
            kesh_xato.json(), {"status": "degraded", "db": "ok", "cache": "error"}
        )


class BackendAuditRegressiyaTests(TestCase):
    def setUp(self) -> None:
        cache.clear()
        self.yil = dashboard.joriy_akademik_yil()
        self.kaf1 = Department.objects.create(nomi="Audit Kaf 1")
        self.kaf2 = Department.objects.create(nomi="Audit Kaf 2")
        self.admin = ofis_admin_yarat()

    def tearDown(self) -> None:
        cache.clear()

    def test_tasdiqqa_yuborilmagan_kafedrani_tasdiqlash_va_qaytarish_500_bermaydi(
        self,
    ) -> None:
        tizimga_kir(self.client, self.admin)
        r_tasdiq = self.client.post(
            reverse("office:kafedra_tasdiqlash", args=[self.kaf1.pk]),
            {"yil": self.yil},
            follow=True,
        )
        self.assertEqual(r_tasdiq.status_code, 200)
        self.assertContains(r_tasdiq, "yuborilishi kerak")

        r_qaytar = self.client.post(
            reverse("office:kafedra_qaytarish", args=[self.kaf1.pk]),
            {"yil": self.yil},
            follow=True,
        )
        self.assertEqual(r_qaytar.status_code, 200)
        self.assertContains(r_qaytar, "yuborilgan bo&#x27;lishi kerak")

    def test_yuklamali_oqituvchini_boshqa_kafedraga_otkazish_rad_etiladi(self) -> None:
        from plans.models import Yuklama

        reja = reja_yasa(boshlanish_yili=self.yil)
        fan = fan_yasa(reja, kafedra=self.kaf1)
        fs = fan_semestr_yasa(fan.tanlangan_variant, semestr=1)
        oqit = oqituvchi_yasa(kafedra=self.kaf1)
        Yuklama.objects.create(fan_semestr=fs, tur=SoatTuri.MARUZA, oqituvchi=oqit)

        tizimga_kir(self.client, self.admin)
        javob = self.client.post(
            reverse("office:oqituvchi_tahrir", args=[oqit.pk]),
            {
                "telefon": oqit.foydalanuvchi.telefon,
                "first_name": oqit.foydalanuvchi.first_name,
                "last_name": oqit.foydalanuvchi.last_name,
                "kafedra": self.kaf2.pk,
                "turi": oqit.turi.pk,
                "yangi_parol": "",
            },
        )
        self.assertEqual(javob.status_code, 200)
        self.assertContains(javob, "yuklama biriktirilgan")
        oqit.refresh_from_db()
        self.assertEqual(oqit.kafedra_id, self.kaf1.pk)

    def test_reja_tahrir_band_guruh_va_qulflangan_kafedrani_himoyalaydi(self) -> None:
        from plans.models import KafedraTasdiqHolati, Yuklama

        reja = reja_yasa(boshlanish_yili=self.yil, guruhlar_soni=2, talabalar_soni=50)
        guruhlar = services.guruhlarni_sinxronlash(reja)
        fan = fan_yasa(reja, kafedra=self.kaf1)
        fs = fan_semestr_yasa(fan.tanlangan_variant, semestr=1)
        oqit = oqituvchi_yasa(kafedra=self.kaf1)
        Yuklama.objects.create(
            fan_semestr=fs, tur=SoatTuri.AMALIYOT, oqituvchi=oqit, guruh=guruhlar[1]
        )

        tizimga_kir(self.client, self.admin)
        r_guruh = self.client.post(
            reverse("office:reja_tahrir", args=[reja.pk]),
            {
                "bilim_sohasi_kodi": reja.bilim_sohasi_kodi,
                "bilim_sohasi_nomi": reja.bilim_sohasi_nomi,
                "talim_sohasi_kodi": reja.talim_sohasi_kodi,
                "talim_sohasi_nomi": reja.talim_sohasi_nomi,
                "yonalish_kodi": reja.yonalish_kodi,
                "yonalish_nomi": reja.yonalish_nomi,
                "talim_shakli": reja.talim_shakli,
                "daraja": reja.daraja,
                "talabalar_soni": 50,
                "guruhlar_soni": 1,
                "guruh_prefiksi": reja.guruh_prefiksi,
            },
        )
        self.assertContains(r_guruh, "2-guruhga allaqachon")

        KafedraYuklamaTasdiq.objects.create(
            kafedra=self.kaf1,
            akademik_yil=self.yil,
            holat=KafedraTasdiqHolati.TASDIQLANGAN,
        )
        r_qulf = self.client.post(
            reverse("office:reja_tahrir", args=[reja.pk]),
            {
                "bilim_sohasi_kodi": reja.bilim_sohasi_kodi,
                "bilim_sohasi_nomi": reja.bilim_sohasi_nomi,
                "talim_sohasi_kodi": reja.talim_sohasi_kodi,
                "talim_sohasi_nomi": reja.talim_sohasi_nomi,
                "yonalish_kodi": reja.yonalish_kodi,
                "yonalish_nomi": reja.yonalish_nomi,
                "talim_shakli": reja.talim_shakli,
                "daraja": reja.daraja,
                "talabalar_soni": 60,
                "guruhlar_soni": 2,
                "guruh_prefiksi": reja.guruh_prefiksi,
            },
        )
        self.assertContains(r_qulf, "qulflangan")

    @override_settings(
        HEMIS_API_KEY="test-kalit-99",
        LOGIN_MAX_URINISH=2,
        API_MAX_SOROV_DAQIQA=3,
    )
    def test_api_kafedralar_aniqligi_va_rate_limit(self) -> None:
        from plans.models import FanTuri
        from plans.tests.factories import variant_yasa

        faol = oqituvchi_yasa(kafedra=self.kaf1)
        nofaol = oqituvchi_yasa(kafedra=self.kaf1)
        nofaol.foydalanuvchi.is_active = False
        nofaol.foydalanuvchi.save(update_fields=["is_active"])
        self.assertTrue(faol.foydalanuvchi.is_active)

        reja = reja_yasa(boshlanish_yili=self.yil)
        fan = fan_yasa(reja, turi=FanTuri.TANLOV, kafedra=self.kaf1)
        v1 = fan.variantlar.first()
        v2 = variant_yasa(fan, kodi="ALT-2", nomi="Tanlanmagan", kafedra=self.kaf1)
        self.assertIsNotNone(v2.pk)
        fan.tanlangan_variant = v1
        fan.save(update_fields=["tanlangan_variant"])

        auth = "Bearer test-kalit-99"
        javob = self.client.get(reverse("api:kafedralar"), HTTP_AUTHORIZATION=auth)
        self.assertEqual(javob.status_code, 200)
        kaf_data = next(k for k in javob.json()["results"] if k["id"] == self.kaf1.pk)
        self.assertEqual(kaf_data["oqituvchilar_soni"], 1)
        self.assertEqual(kaf_data["fanlar_soni"], 1)

        # API rate limit (3 ta so'rovdan so'ng 429)
        self.client.get(reverse("api:kafedralar"), HTTP_AUTHORIZATION=auth)
        self.client.get(reverse("api:kafedralar"), HTTP_AUTHORIZATION=auth)
        r_limit = self.client.get(reverse("api:kafedralar"), HTTP_AUTHORIZATION=auth)
        self.assertEqual(r_limit.status_code, 429)
