"""Veb ko'rinish testlari uchun rollarga mos foydalanuvchi va kirish yordamchilari."""

from itertools import count

from django.test import Client

from accounts.models import Department, Foydalanuvchi, Rol
from plans.tests.factories import oqituvchi_yasa

_raqam = count(1)

PAROL = "test-parol-123"


def foydalanuvchi_yarat(rol: str) -> Foydalanuvchi:
    n = next(_raqam)
    return Foydalanuvchi.objects.create_user(
        telefon=f"+9988{n:08d}",
        password=PAROL,
        first_name="Web",
        last_name=f"Test{n}",
        rol=rol,
    )


def ofis_admin_yarat() -> Foydalanuvchi:
    return foydalanuvchi_yarat(Rol.OFFICE_ADMIN)


def mudir_yarat(kafedra: Department | None = None) -> Foydalanuvchi:
    """Kafedra mudiri sifatida biriktirilgan profilga ega DEPARTMENT_ADMIN yaratadi."""
    profil = oqituvchi_yasa(kafedra=kafedra)
    foydalanuvchi = profil.foydalanuvchi
    foydalanuvchi.rol = Rol.DEPARTMENT_ADMIN
    foydalanuvchi.save(update_fields=["rol"])
    profil.kafedra.mudir = profil
    profil.kafedra.save(update_fields=["mudir"])
    return foydalanuvchi


def oqituvchi_yarat(kafedra: Department | None = None) -> Foydalanuvchi:
    return oqituvchi_yasa(kafedra=kafedra).foydalanuvchi


def tizimga_kir(client: Client, foydalanuvchi: Foydalanuvchi) -> None:
    client.force_login(foydalanuvchi)
