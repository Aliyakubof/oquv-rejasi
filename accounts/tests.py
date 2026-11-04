from django.core.exceptions import ValidationError
from django.test import TestCase

from accounts.models import Department, Foydalanuvchi, OqituvchiTuri, Rol
from accounts.services import mudir_tayinlash, oqituvchi_yangilash, oqituvchi_yaratish
from plans.tests.factories import make_oqituvchi


def _kafedra(nomi: str = "Kimyo") -> Department:
    return Department.objects.create(nomi=nomi)


def _turi() -> OqituvchiTuri:
    return OqituvchiTuri.objects.create(nomi="Professor", min_soat=300)


class OqituvchiYaratishTests(TestCase):
    def test_profil_va_hisob_yaratiladi(self) -> None:
        profil = oqituvchi_yaratish(
            telefon="+998911111111",
            first_name="Anvar",
            last_name="Karimov",
            parol="juda-maxfiy-123",
            kafedra=_kafedra(),
            turi=_turi(),
        )
        self.assertEqual(profil.foydalanuvchi.rol, Rol.TEACHER)
        self.assertTrue(profil.foydalanuvchi.check_password("juda-maxfiy-123"))

    def test_takroriy_telefon_atomik_rad_etiladi(self) -> None:
        kafedra, turi = _kafedra(), _turi()
        oqituvchi_yaratish(
            telefon="+998911111111",
            first_name="A",
            last_name="B",
            parol="juda-maxfiy-123",
            kafedra=kafedra,
            turi=turi,
        )
        with self.assertRaises(ValidationError):
            oqituvchi_yaratish(
                telefon="+998911111111",
                first_name="C",
                last_name="D",
                parol="juda-maxfiy-123",
                kafedra=kafedra,
                turi=turi,
            )
        self.assertEqual(Foydalanuvchi.objects.filter(rol=Rol.TEACHER).count(), 1)


class OqituvchiYangilashTests(TestCase):
    def test_maydonlar_va_parol_yangilanadi(self) -> None:
        profil = make_oqituvchi()
        oqituvchi_yangilash(
            profil,
            telefon="+998 90 123 45 67",
            first_name="Yangi",
            last_name="Ism",
            kafedra=profil.kafedra,
            turi=profil.turi,
            yangi_parol="boshqa-parol-99",
        )
        profil.foydalanuvchi.refresh_from_db()
        self.assertEqual(profil.foydalanuvchi.telefon, "+998901234567")
        self.assertEqual(profil.foydalanuvchi.first_name, "Yangi")
        self.assertTrue(profil.foydalanuvchi.check_password("boshqa-parol-99"))

    def test_mudir_boshqa_kafedraga_otsa_mudirlik_bekor_qilinadi(self) -> None:
        eski_kafedra = _kafedra("Biologiya")
        yangi_kafedra = _kafedra("Ekologiya")
        profil = make_oqituvchi(kafedra=eski_kafedra)
        mudir_tayinlash(eski_kafedra, profil)

        oqituvchi_yangilash(
            profil,
            telefon=profil.foydalanuvchi.telefon,
            first_name=profil.foydalanuvchi.first_name,
            last_name=profil.foydalanuvchi.last_name,
            kafedra=yangi_kafedra,
            turi=profil.turi,
        )

        eski_kafedra.refresh_from_db()
        profil.foydalanuvchi.refresh_from_db()
        self.assertIsNone(eski_kafedra.mudir)
        self.assertEqual(profil.foydalanuvchi.rol, Rol.TEACHER)


class MudirTayinlashTests(TestCase):
    def setUp(self) -> None:
        self.kafedra = _kafedra()
        self.birinchi = make_oqituvchi(kafedra=self.kafedra)
        self.ikkinchi = make_oqituvchi(kafedra=self.kafedra)

    def test_tayinlash_rolni_kotaradi(self) -> None:
        mudir_tayinlash(self.kafedra, self.birinchi)
        self.kafedra.refresh_from_db()
        self.birinchi.foydalanuvchi.refresh_from_db()
        self.assertEqual(self.kafedra.mudir, self.birinchi)
        self.assertEqual(self.birinchi.foydalanuvchi.rol, Rol.DEPARTMENT_ADMIN)

    def test_almashtirish_eskisini_tushiradi(self) -> None:
        mudir_tayinlash(self.kafedra, self.birinchi)
        self.kafedra.refresh_from_db()
        mudir_tayinlash(self.kafedra, self.ikkinchi)
        self.birinchi.foydalanuvchi.refresh_from_db()
        self.ikkinchi.foydalanuvchi.refresh_from_db()
        self.assertEqual(self.birinchi.foydalanuvchi.rol, Rol.TEACHER)
        self.assertEqual(self.ikkinchi.foydalanuvchi.rol, Rol.DEPARTMENT_ADMIN)

    def test_bekor_qilish(self) -> None:
        mudir_tayinlash(self.kafedra, self.birinchi)
        self.kafedra.refresh_from_db()
        mudir_tayinlash(self.kafedra, None)
        self.kafedra.refresh_from_db()
        self.birinchi.foydalanuvchi.refresh_from_db()
        self.assertIsNone(self.kafedra.mudir)
        self.assertEqual(self.birinchi.foydalanuvchi.rol, Rol.TEACHER)

    def test_begona_kafedra_oqituvchisi_rad_etiladi(self) -> None:
        begona = make_oqituvchi(kafedra=_kafedra("Fizika"))
        with self.assertRaises(ValidationError):
            mudir_tayinlash(self.kafedra, begona)
