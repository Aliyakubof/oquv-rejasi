"""Tests for first-login accessibility onboarding and appearance preferences."""

from pathlib import Path

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from accounts.models import Department, OqituvchiTuri, ShriftOlchami
from accounts.services import oqituvchi_yaratish
from web.tests.helpers import PAROL, login, oqituvchi_yarat


class KorinishOnboardingTests(TestCase):
    def test_yangi_user_birinchi_kirishda_savollarni_koradi(self) -> None:
        kaf = Department.objects.create(nomi="Matematika")
        turi = OqituvchiTuri.objects.create(nomi="Professor", min_soat=400)
        profil = oqituvchi_yaratish(
            telefon="+998901112233",
            first_name="Anvar",
            last_name="Karimov",
            parol=PAROL,
            kafedra=kaf,
            turi=turi,
        )
        user = profil.foydalanuvchi
        self.assertFalse(user.korinish_tanlangan)
        self.assertEqual(user.shrift_olchami, ShriftOlchami.STANDART)

        login(self.client, user)
        javob = self.client.get(reverse("men:yuklamalar"))
        self.assertEqual(javob.status_code, 200)
        self.assertContains(javob, "korinish-sozlash-modal")
        self.assertContains(javob, "majburiy: true")
        self.assertContains(javob, "ui-font-standart")

    def test_korinish_saqlash_db_va_klasslarni_yangilaydi(self) -> None:
        user = oqituvchi_yarat()
        login(self.client, user)
        javob = self.client.post(
            reverse("korinish_saqlash"),
            {
                "shrift_olchami": ShriftOlchami.JUDA_YIRIK,
                "yuqori_kontrast": "true",
                "keng_rejim": "true",
            },
            HTTP_ACCEPT="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(javob.status_code, 200)
        self.assertTrue(javob.json()["ok"])

        user.refresh_from_db()
        self.assertTrue(user.korinish_tanlangan)
        self.assertEqual(user.shrift_olchami, ShriftOlchami.JUDA_YIRIK)
        self.assertTrue(user.yuqori_kontrast)
        self.assertTrue(user.keng_rejim)

        sahifa = self.client.get(reverse("men:yuklamalar"))
        self.assertContains(sahifa, "ui-font-juda_yirik")
        self.assertContains(sahifa, "ui-kontrast")
        self.assertContains(sahifa, "ui-keng")
        self.assertContains(sahifa, "majburiy: false")

    def test_korinish_saqlash_xavfsizlik_va_validatsiya(self) -> None:
        url = reverse("korinish_saqlash")
        anon = self.client.post(url, {"shrift_olchami": ShriftOlchami.YIRIK})
        self.assertRedirects(anon, f"{reverse('kirish')}?next={url}")

        user = oqituvchi_yarat()
        login(self.client, user)
        get_javob = self.client.get(url)
        self.assertEqual(get_javob.status_code, 405)

        xato = self.client.post(
            url,
            {"shrift_olchami": "noma_lum"},
            HTTP_ACCEPT="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(xato.status_code, 400)
        self.assertFalse(xato.json()["ok"])

    def test_korinish_css_layout_himoyasi(self) -> None:
        css_yoli = (
            Path(settings.BASE_DIR) / "web" / "static" / "web" / "css" / "app.css"
        )
        css_matn = css_yoli.read_text(encoding="utf-8")
        self.assertIn("body.ui-kontrast .navbar *:focus-visible", css_matn)
        self.assertIn("body.ui-font-juda_yirik .popover-filter-chip", css_matn)
        self.assertIn("body.ui-font-juda_yirik .soat-input", css_matn)
        self.assertIn("body.ui-keng .panel-row > td", css_matn)
        eski_badge_xato = (
            "body.ui-kontrast .badge-major {\n"
            "  border-color: #1a2a6e !important;\n"
            "  color: #1a2a6e !important;"
        )
        self.assertNotIn(eski_badge_xato, css_matn)
