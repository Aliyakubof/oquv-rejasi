from django.test import TestCase
from django.urls import reverse

from accounts.models import Rol
from web.tests.helpers import (
    PAROL,
    foydalanuvchi_yarat,
    mudir_yarat,
    ofis_admin_yarat,
    oqituvchi_yarat,
    tizimga_kir,
)


class KirishTests(TestCase):
    def setUp(self) -> None:
        self.user = ofis_admin_yarat()

    def test_togri_telefon_bilan_kiradi(self) -> None:
        javob = self.client.post(
            reverse("kirish"),
            {"username": self.user.telefon, "password": PAROL},
        )
        self.assertRedirects(javob, reverse("bosh_sahifa"), target_status_code=302)

    def test_probelli_telefon_normallashtiriladi(self) -> None:
        telefon = self.user.telefon
        probelli = f"{telefon[:4]} {telefon[4:6]} {telefon[6:]}"
        javob = self.client.post(
            reverse("kirish"), {"username": probelli, "password": PAROL}
        )
        self.assertRedirects(javob, reverse("bosh_sahifa"), target_status_code=302)

    def test_notogri_parol_uzbekcha_xato(self) -> None:
        javob = self.client.post(
            reverse("kirish"),
            {"username": self.user.telefon, "password": "notogri"},
        )
        self.assertContains(
            javob, "Telefon raqam yoki parol noto&#x27;g&#x27;ri.", html=False
        )


class BoshSahifaTests(TestCase):
    def test_office_admin_office_ga(self) -> None:
        tizimga_kir(self.client, ofis_admin_yarat())
        javob = self.client.get(reverse("bosh_sahifa"))
        self.assertRedirects(javob, reverse("office:dashboard"))

    def test_superadmin_office_ga(self) -> None:
        tizimga_kir(self.client, foydalanuvchi_yarat(Rol.SUPERADMIN))
        javob = self.client.get(reverse("bosh_sahifa"))
        self.assertRedirects(javob, reverse("office:dashboard"))

    def test_mudir_kafedra_ga(self) -> None:
        tizimga_kir(self.client, mudir_yarat())
        javob = self.client.get(reverse("bosh_sahifa"))
        self.assertRedirects(javob, reverse("kafedra:dashboard"))

    def test_oqituvchi_men_ga(self) -> None:
        tizimga_kir(self.client, oqituvchi_yarat())
        javob = self.client.get(reverse("bosh_sahifa"))
        self.assertRedirects(javob, reverse("men:yuklamalar"))


class RuxsatTests(TestCase):
    def test_anonim_kirishga_yonaltiriladi(self) -> None:
        javob = self.client.get(reverse("office:dashboard"))
        self.assertRedirects(
            javob, f"{reverse('kirish')}?next={reverse('office:dashboard')}"
        )

    def test_oqituvchi_office_ga_kira_olmaydi(self) -> None:
        tizimga_kir(self.client, oqituvchi_yarat())
        javob = self.client.get(reverse("office:dashboard"))
        self.assertRedirects(javob, reverse("bosh_sahifa"), target_status_code=302)

    def test_kafedrasiz_mudir_yonaltiriladi(self) -> None:
        user = foydalanuvchi_yarat(Rol.DEPARTMENT_ADMIN)
        tizimga_kir(self.client, user)
        javob = self.client.get(reverse("kafedra:dashboard"))
        self.assertRedirects(javob, reverse("bosh_sahifa"), target_status_code=302)

    def test_mudir_oz_sahifasini_ochadi(self) -> None:
        tizimga_kir(self.client, mudir_yarat())
        javob = self.client.get(reverse("kafedra:dashboard"))
        self.assertEqual(javob.status_code, 200)
