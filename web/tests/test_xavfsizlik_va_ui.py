"""Regression tests for security middleware, RBAC isolation, N+1 ORM budgets,
workload confirmation locks, live-polling auth, and UI filters."""

from django.core.exceptions import ValidationError
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from accounts.models import Department, OqituvchiProfil
from accounts.phone import validate_uzbek_phone
from plans import dashboard, services
from plans.models import KafedraYuklamaTasdiq, SoatTuri
from plans.tests.factories import (
    make_fan,
    make_fan_semestr,
    make_oqituvchi,
    make_reja,
)
from web.templatetags.ui import bosh_harflar, foiz
from web.tests.helpers import (
    login,
    mudir_yarat,
    office_admin_yarat,
    oqituvchi_yarat,
)
from web.views.jonli import holat_versiyasi


class XavfsizlikVaRuxsatTests(TestCase):
    def setUp(self) -> None:
        self.yil = dashboard.joriy_akademik_yil()
        self.mudir = mudir_yarat()
        self.kafedra = self.mudir.oqituvchi_profil.kafedra

    def test_faolsiz_foydalanuvchi_middleware_chiqaradi_va_htmx_401(self) -> None:
        login(self.client, self.mudir)
        self.mudir.is_active = False
        self.mudir.save(update_fields=["is_active"])

        oddiy = self.client.get(reverse("kafedra:dashboard"))
        self.assertRedirects(
            oddiy, f"{reverse('kirish')}?next={reverse('kafedra:dashboard')}"
        )

        login(self.client, self.mudir)
        htmx = self.client.get(reverse("kafedra:dashboard"), HTTP_HX_REQUEST="true")
        self.assertEqual(htmx.status_code, 401)
        self.assertEqual(htmx["HX-Redirect"], reverse("kirish"))

    def test_reja_detail_notogri_tab_va_sem_tozalanadi(self) -> None:
        reja = make_reja(boshlanish_yili=self.yil)
        fan = make_fan(reja, kafedra=self.kafedra)
        make_fan_semestr(fan.tanlangan_variant, semestr=1)
        login(self.client, office_admin_yarat())

        url = reverse("office:reja_detail", args=[reja.pk])
        javob = self.client.get(url, {"tab": "<script>alert(1)</script>", "sem": "bad"})
        self.assertEqual(javob.status_code, 200)
        self.assertEqual(javob.context["tab"], "jadval")
        self.assertEqual(javob.context["tanlangan_semestr"], 1)
        self.assertNotContains(javob, "<script>alert(1)</script>")

    def test_mudir_office_admin_profilini_tahrirlay_olmaydi(self) -> None:
        admin = office_admin_yarat()
        turi = self.mudir.oqituvchi_profil.turi
        admin_profil = OqituvchiProfil.objects.create(
            foydalanuvchi=admin, kafedra=self.kafedra, turi=turi
        )
        login(self.client, self.mudir)
        javob = self.client.get(
            reverse("kafedra:oqituvchi_tahrir", args=[admin_profil.pk])
        )
        self.assertEqual(javob.status_code, 404)

    @override_settings(DEBUG=True)
    def test_dev_panel_mudir_va_oqituvchiga_taqiqlanadi(self) -> None:
        login(self.client, self.mudir)
        self.assertEqual(self.client.get(reverse("dev:panel")).status_code, 403)
        login(self.client, oqituvchi_yarat(kafedra=self.kafedra))
        self.assertEqual(
            self.client.post(
                reverse("dev:almashtirish"), {"foydalanuvchi": self.mudir.pk}
            ).status_code,
            403,
        )


class OrmVaTasdiqTests(TestCase):
    def setUp(self) -> None:
        self.yil = dashboard.joriy_akademik_yil()
        self.mudir = mudir_yarat()
        self.kafedra = self.mudir.oqituvchi_profil.kafedra

    def test_kafedra_dashboard_get_bazaga_yozmaydi(self) -> None:
        login(self.client, self.mudir)
        javob = self.client.get(reverse("kafedra:dashboard"))
        self.assertEqual(javob.status_code, 200)
        self.assertEqual(KafedraYuklamaTasdiq.objects.count(), 0)

    def test_qayta_yuborishda_tasdiqlagan_tozalanadi(self) -> None:
        admin = office_admin_yarat()
        services.yuklamani_tasdiqqa_yuborish(self.kafedra, self.yil, "V1")
        services.yuklamani_tasdiqlash(self.kafedra, self.yil, admin, "Ok")
        services.yuklamani_qaytarish(self.kafedra, self.yil, admin, "Tuzating")
        qayta = services.yuklamani_tasdiqqa_yuborish(self.kafedra, self.yil, "V2")
        self.assertIsNone(qayta.tasdiqlagan)
        self.assertIsNone(qayta.tasdiqlangan_vaqt)

    def test_n_plus_1_sorovlar_soni_cheklangan(self) -> None:
        reja = make_reja(boshlanish_yili=self.yil)
        services.guruhlarni_sinxronlash(reja)
        fan1 = make_fan(reja, raqam="1.01", kafedra=self.kafedra)
        make_fan_semestr(fan1.tanlangan_variant, semestr=1)

        login(self.client, self.mudir)

        def _count(url: str) -> int:
            with CaptureQueriesContext(connection) as ctx:
                self.client.get(url)
            return len(ctx)

        k_kichik = _count(reverse("kafedra:dashboard"))
        for idx in range(2, 10):
            fan = make_fan(reja, raqam=f"1.{idx:02d}", kafedra=self.kafedra)
            make_fan_semestr(fan.tanlangan_variant, semestr=1)
        k_katta = _count(reverse("kafedra:dashboard"))
        self.assertLessEqual(abs(k_katta - k_kichik), 1)

        admin = office_admin_yarat()
        login(self.client, admin)
        o_katta = _count(reverse("office:dashboard"))
        for idx in range(10, 18):
            fan = make_fan(reja, raqam=f"1.{idx:02d}", kafedra=self.kafedra)
            make_fan_semestr(fan.tanlangan_variant, semestr=1)
        o_juda_katta = _count(reverse("office:dashboard"))
        self.assertLessEqual(abs(o_juda_katta - o_katta), 1)

    def test_jonli_holat_anonim_401_va_ommaviy_taqsimot_kesh_yangilanadi(self) -> None:
        anonim = self.client.get(reverse("jonli_holat"))
        self.assertEqual(anonim.status_code, 401)

        reja = make_reja(boshlanish_yili=self.yil)
        services.guruhlarni_sinxronlash(reja)
        fan = make_fan(reja, kafedra=self.kafedra)
        fs = make_fan_semestr(fan.tanlangan_variant, semestr=1)
        oqituvchi = make_oqituvchi(kafedra=self.kafedra)

        v1 = holat_versiyasi()
        services.guruhlarga_ommaviy_taqsimlash(fs, oqituvchi, SoatTuri.AMALIYOT)
        v2 = holat_versiyasi()
        self.assertNotEqual(v1, v2)


class UiVaTelefonTests(TestCase):
    def test_ui_filtrlar_apostrof_va_cheksiz_foiz(self) -> None:
        self.assertEqual(bosh_harflar("O'zbekiston G‘afur"), "OG")
        self.assertEqual(bosh_harflar("Sa’dullaʻ Boburʼ"), "SB")
        self.assertEqual(foiz(150, 100), 150)
        self.assertEqual(foiz(-5, 100), 0)
        self.assertEqual(foiz(10, 0), 0)

    def test_navbar_va_oqituvchi_excel_oob_shablonlari(self) -> None:
        admin = office_admin_yarat()
        Department.objects.create(nomi="Matematika")
        login(self.client, admin)
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
