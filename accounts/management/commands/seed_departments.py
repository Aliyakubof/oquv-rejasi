"""Seed departments (kafedra) with random teacher accounts and a head each.

One-off data seeding: teacher names are randomly generated placeholders since
no real HR data is available yet; every created teacher shares one default
password, printed at the end for the operator to hand out and rotate.
"""

import random

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.management.commands.uzbek_names import FIRST_NAMES, LAST_NAMES
from accounts.models import (
    Department,
    Foydalanuvchi,
    OqituvchiProfil,
    OqituvchiTuri,
    Rol,
)
from accounts.services import mudir_tayinlash, oqituvchi_yaratish

DEPARTMENT_NAMES = [
    "Axborot tizimlari va texnologiyalari",
    "Raqamli texnologiyalar",
    "Menejment",
    "Ijtimoiy fanlar",
    "Buxgalteriya hisobi",
    "Xorijiy tillar",
    "Marketing",
]

DEFAULT_PASSWORD = "Oquvreja2026!"
PHONE_PREFIX = "+99890"
# Clear of the teacher range, which runs to +99890 0000603 (index*100 + offset).
OFFICE_ADMIN_PHONE = "+998909999999"


class Command(BaseCommand):
    help = "Create departments, random teacher accounts, and assign heads."

    def handle(self, *args: object, **options: object) -> None:
        turlari = list(OqituvchiTuri.objects.all())
        if not turlari:
            raise CommandError(
                "No OqituvchiTuri rows found. Create teacher types before seeding."
            )

        with transaction.atomic():
            self._seed_office_admin()
            for index, nomi in enumerate(DEPARTMENT_NAMES):
                self._seed_department(nomi, index, turlari)

        self.stdout.write(self.style.SUCCESS("Done."))
        self.stdout.write(
            f"Default password for all seeded teachers: {DEFAULT_PASSWORD}"
        )

    def _seed_office_admin(self) -> None:
        if Foydalanuvchi.objects.filter(telefon=OFFICE_ADMIN_PHONE).exists():
            self.stdout.write(f"Skipped (exists): office admin {OFFICE_ADMIN_PHONE}")
            return

        Foydalanuvchi.objects.create_user(
            telefon=OFFICE_ADMIN_PHONE,
            password=DEFAULT_PASSWORD,
            first_name="Ofis",
            last_name="Admin",
            rol=Rol.OFFICE_ADMIN,
        )
        self.stdout.write(
            self.style.SUCCESS(f"Created: office admin ({OFFICE_ADMIN_PHONE})")
        )

    def _seed_department(
        self, nomi: str, index: int, turlari: list[OqituvchiTuri]
    ) -> None:
        department, created = Department.objects.get_or_create(nomi=nomi)
        if not created:
            self.stdout.write(f"Skipped (exists): {nomi}")
            return

        head_profil = self._create_teacher_profil(index * 100, department, turlari)
        mudir_tayinlash(department, head_profil)

        for offset in range(1, 4):
            self._create_teacher_profil(index * 100 + offset, department, turlari)

        self.stdout.write(self.style.SUCCESS(f"Created: {nomi} (head: {head_profil})"))

    def _create_teacher_profil(
        self, seed: int, department: Department, turlari: list[OqituvchiTuri]
    ) -> OqituvchiProfil:
        return oqituvchi_yaratish(
            telefon=f"{PHONE_PREFIX}{seed:07d}",
            first_name=random.choice(FIRST_NAMES),
            last_name=random.choice(LAST_NAMES),
            parol=DEFAULT_PASSWORD,
            kafedra=department,
            turi=random.choice(turlari),
        )
