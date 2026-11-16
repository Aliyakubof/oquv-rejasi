from django.contrib.auth import SESSION_KEY
from django.test import TestCase, override_settings
from django.urls import reverse

from web.tests.helpers import (
    mudir_yarat,
    ofis_admin_yarat,
    oqituvchi_yarat,
    tizimga_kir,
)
from web.views.dev import ASL_KEY


class DebugOchiqTests(TestCase):
    """DEBUG o'chirilganda rol almashtirgich umuman ishlamasligi kerak."""

    def test_almashtirish_debugsiz_404(self) -> None:
        tizimga_kir(self.client, ofis_admin_yarat())
        javob = self.client.post(
            reverse("dev:almashtirish"), {"foydalanuvchi": mudir_yarat().pk}
        )
        self.assertEqual(javob.status_code, 404)

    def test_panel_debugsiz_404(self) -> None:
        tizimga_kir(self.client, ofis_admin_yarat())
        self.assertEqual(self.client.get(reverse("dev:panel")).status_code, 404)

    def test_navbarda_almashtirgich_yoq(self) -> None:
        tizimga_kir(self.client, ofis_admin_yarat())
        javob = self.client.get(reverse("office:dashboard"))
        self.assertNotContains(javob, "user-avatar")
        self.assertContains(javob, f'href="{reverse("parol_ozgartirish")}">Parol</a>')


@override_settings(DEBUG=True)
class RolAlmashtirishTests(TestCase):
    def setUp(self) -> None:
        self.admin = ofis_admin_yarat()
        self.mudir = mudir_yarat()
        self.kafedra = self.mudir.oqituvchi_profil.kafedra
        self.oqituvchi = oqituvchi_yarat(kafedra=self.kafedra)
        tizimga_kir(self.client, self.admin)

    def _almashtir(self, foydalanuvchi_pk: int) -> None:
        self.client.post(
            reverse("dev:almashtirish"), {"foydalanuvchi": foydalanuvchi_pk}
        )

    def _joriy_pk(self) -> int:
        return int(self.client.session[SESSION_KEY])

    def test_anonim_kirishga_yonaltiriladi(self) -> None:
        self.client.logout()
        javob = self.client.post(reverse("dev:almashtirish"), {"foydalanuvchi": 1})
        self.assertEqual(javob.status_code, 302)
        self.assertIn(reverse("kirish"), javob["Location"])

    def test_navbarda_almashtirgich_bor(self) -> None:
        javob = self.client.get(reverse("office:dashboard"))
        self.assertContains(javob, "user-avatar")
        self.assertContains(javob, "menu-parol-link")
        self.assertContains(javob, "Parolni o'zgartirish")
        self.assertNotContains(
            javob, f'href="{reverse("parol_ozgartirish")}">Parol</a>'
        )

    def test_mudirga_otib_kafedrani_ocha_oladi(self) -> None:
        """Rolni shunchaki almashtirmay, haqiqiy /kafedra/ sahifasini ochib beradi."""
        self._almashtir(self.mudir.pk)
        self.assertEqual(self._joriy_pk(), self.mudir.pk)
        self.assertEqual(self.client.get(reverse("kafedra:dashboard")).status_code, 200)

    def test_oqituvchiga_otib_yuklamalarni_ocha_oladi(self) -> None:
        self._almashtir(self.oqituvchi.pk)
        self.assertEqual(self.client.get(reverse("men:yuklamalar")).status_code, 200)

    def test_asl_hisob_oraliq_almashuvda_saqlanadi(self) -> None:
        self._almashtir(self.mudir.pk)
        self._almashtir(self.oqituvchi.pk)
        self.assertEqual(self.client.session[ASL_KEY], self.admin.pk)

        self.client.post(reverse("dev:qaytish"))
        self.assertEqual(self._joriy_pk(), self.admin.pk)
        self.assertNotIn(ASL_KEY, self.client.session)

    def test_ozini_tanlasa_asl_hisob_yozilmaydi(self) -> None:
        self._almashtir(self.admin.pk)
        self.assertNotIn(ASL_KEY, self.client.session)

    def test_qaytish_asl_hisobsiz_zararsiz(self) -> None:
        javob = self.client.post(reverse("dev:qaytish"))
        self.assertRedirects(javob, reverse("bosh_sahifa"), target_status_code=302)
        self.assertEqual(self._joriy_pk(), self.admin.pk)

    def test_panel_uchala_guruhni_beradi(self) -> None:
        javob = self.client.get(reverse("dev:panel"))
        self.assertContains(javob, self.admin.get_full_name())
        self.assertContains(javob, self.mudir.get_full_name())
        self.assertContains(javob, self.oqituvchi.get_full_name())
        self.assertContains(javob, self.kafedra.nomi)

    def test_panel_oqituvchi_soatini_korsatadi(self) -> None:
        norma = self.oqituvchi.oqituvchi_profil.turi.min_soat
        javob = self.client.get(reverse("dev:panel"))
        self.assertContains(javob, f"0 / {norma}")
