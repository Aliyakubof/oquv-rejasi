from django.test import TestCase
from django.urls import reverse

from accounts.models import Department, Foydalanuvchi, OqituvchiTuri, Rol
from plans.models import SoatTuri, Yuklama
from plans.tests.factories import (
    make_fan,
    make_fan_semestr,
    make_oqituvchi,
    make_reja,
)
from web.tests.helpers import login, office_admin_yarat


class KafedraCrudTests(TestCase):
    def setUp(self) -> None:
        login(self.client, office_admin_yarat())

    def test_yaratish_va_tahrirlash(self) -> None:
        self.client.post(reverse("office:kafedra_yangi"), {"nomi": "Yangi kafedra"})
        kafedra = Department.objects.get(nomi="Yangi kafedra")
        self.client.post(
            reverse("office:kafedra_tahrir", args=[kafedra.pk]),
            {"nomi": "Qayta nomlangan"},
        )
        kafedra.refresh_from_db()
        self.assertEqual(kafedra.nomi, "Qayta nomlangan")

    def test_himoyalangan_ochirish_xabari(self) -> None:
        profil = make_oqituvchi()
        javob = self.client.post(
            reverse("office:kafedra_ochirish", args=[profil.kafedra.pk]),
            follow=True,
        )
        self.assertContains(javob, "avval ularni boshqa kafedraga")
        self.assertTrue(Department.objects.filter(pk=profil.kafedra.pk).exists())

    def test_bosh_kafedra_ochiriladi(self) -> None:
        kafedra = Department.objects.create(nomi="Bo'sh")
        self.client.post(reverse("office:kafedra_ochirish", args=[kafedra.pk]))
        self.assertFalse(Department.objects.filter(pk=kafedra.pk).exists())

    def test_kafedra_ochirish_next_parametri_saqlanadi(self) -> None:
        k1 = Department.objects.create(nomi="Filtrlash")
        qaytish = f"{reverse('office:kafedra_list')}?yil=2025"
        r = self.client.post(
            reverse("office:kafedra_ochirish", args=[k1.pk]),
            {"next": qaytish},
        )
        self.assertRedirects(r, qaytish, fetch_redirect_response=False)

        k2 = Department.objects.create(nomi="Xavfsiz")
        r_yomon = self.client.post(
            reverse("office:kafedra_ochirish", args=[k2.pk]),
            {"next": "https://evil.example/phish"},
        )
        self.assertRedirects(
            r_yomon, reverse("office:kafedra_list"), fetch_redirect_response=False
        )


class MudirTayinlashViewTests(TestCase):
    def setUp(self) -> None:
        self.profil = make_oqituvchi()
        login(self.client, office_admin_yarat())

    def test_mudir_tayinlanadi(self) -> None:
        self.client.post(
            reverse("office:kafedra_mudir", args=[self.profil.kafedra.pk]),
            {"profil": self.profil.pk},
        )
        self.profil.kafedra.refresh_from_db()
        self.profil.foydalanuvchi.refresh_from_db()
        self.assertEqual(self.profil.kafedra.mudir, self.profil)
        self.assertEqual(self.profil.foydalanuvchi.rol, Rol.DEPARTMENT_ADMIN)

    def test_begona_oqituvchi_xato_xabari(self) -> None:
        begona = make_oqituvchi(kafedra=Department.objects.create(nomi="Boshqa"))
        javob = self.client.post(
            reverse("office:kafedra_mudir", args=[self.profil.kafedra.pk]),
            {"profil": begona.pk},
            follow=True,
        )
        self.assertContains(javob, "boshqa kafedraga tegishli")


class OqituvchiCrudTests(TestCase):
    def setUp(self) -> None:
        self.kafedra = Department.objects.create(nomi="Tillar")
        self.turi = OqituvchiTuri.objects.create(nomi="Dotsent", min_soat=450)
        login(self.client, office_admin_yarat())

    def test_yaratish(self) -> None:
        javob = self.client.post(
            reverse("office:oqituvchi_yangi"),
            {
                "telefon": "+998 93 555 44 33",
                "first_name": "Nodira",
                "last_name": "Yusupova",
                "kafedra": self.kafedra.pk,
                "turi": self.turi.pk,
                "parol": "juda-maxfiy-parol-7",
            },
        )
        self.assertRedirects(javob, reverse("office:oqituvchi_list"))
        foydalanuvchi = Foydalanuvchi.objects.get(telefon="+998935554433")
        self.assertEqual(foydalanuvchi.oqituvchi_profil.kafedra, self.kafedra)

    def test_takroriy_telefon_xatosi(self) -> None:
        profil = make_oqituvchi(kafedra=self.kafedra)
        javob = self.client.post(
            reverse("office:oqituvchi_yangi"),
            {
                "telefon": profil.foydalanuvchi.telefon,
                "first_name": "X",
                "last_name": "Y",
                "kafedra": self.kafedra.pk,
                "turi": self.turi.pk,
                "parol": "juda-maxfiy-parol-7",
            },
        )
        self.assertContains(javob, "allaqachon ro")

    def test_tahrirlash(self) -> None:
        profil = make_oqituvchi(kafedra=self.kafedra)
        javob = self.client.post(
            reverse("office:oqituvchi_tahrir", args=[profil.pk]),
            {
                "telefon": profil.foydalanuvchi.telefon,
                "first_name": "Ozod",
                "last_name": "G'aniyev",
                "kafedra": self.kafedra.pk,
                "turi": self.turi.pk,
                "yangi_parol": "",
            },
        )
        self.assertRedirects(javob, reverse("office:oqituvchi_list"))
        profil.foydalanuvchi.refresh_from_db()
        self.assertEqual(profil.foydalanuvchi.first_name, "Ozod")

    def test_yuklamali_oqituvchi_faolsizlantiriladi(self) -> None:
        profil = make_oqituvchi(kafedra=self.kafedra)
        reja = make_reja()
        fan = make_fan(reja)
        fs = make_fan_semestr(fan.tanlangan_variant)
        Yuklama.objects.create(fan_semestr=fs, tur=SoatTuri.MARUZA, oqituvchi=profil)
        self.client.post(reverse("office:oqituvchi_ochirish", args=[profil.pk]))
        profil.foydalanuvchi.refresh_from_db()
        self.assertFalse(profil.foydalanuvchi.is_active)

    def test_yuklamasiz_oqituvchi_ochiriladi(self) -> None:
        profil = make_oqituvchi(kafedra=self.kafedra)
        self.client.post(reverse("office:oqituvchi_ochirish", args=[profil.pk]))
        self.assertFalse(
            Foydalanuvchi.objects.filter(pk=profil.foydalanuvchi_id).exists()
        )

    def test_kafedra_filtri(self) -> None:
        bizniki = make_oqituvchi(kafedra=self.kafedra)
        boshqa = make_oqituvchi(kafedra=Department.objects.create(nomi="Boshqa"))
        javob = self.client.get(
            reverse("office:oqituvchi_list"), {"kafedra": self.kafedra.pk}
        )
        self.assertContains(javob, str(bizniki))
        self.assertNotContains(javob, str(boshqa))

    def test_oqituvchi_ochirish_va_parol_next_parametri_saqlanadi(self) -> None:
        profil = make_oqituvchi(kafedra=self.kafedra)
        qaytish = f"{reverse('office:oqituvchi_list')}?yil=2025&q=test&page=2"
        r_parol = self.client.post(
            reverse("office:oqituvchi_vaqtinchalik_parol", args=[profil.pk]),
            {"next": qaytish},
        )
        self.assertRedirects(r_parol, qaytish, fetch_redirect_response=False)

        r_ochir = self.client.post(
            reverse("office:oqituvchi_ochirish", args=[profil.pk]),
            {"next": qaytish},
        )
        self.assertRedirects(r_ochir, qaytish, fetch_redirect_response=False)

        profil2 = make_oqituvchi(kafedra=self.kafedra)
        r_yomon = self.client.post(
            reverse("office:oqituvchi_ochirish", args=[profil2.pk]),
            {"next": "//evil.example/redirect"},
        )
        self.assertRedirects(
            r_yomon, reverse("office:oqituvchi_list"), fetch_redirect_response=False
        )
