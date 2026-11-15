"""Seed departments (kafedra) with random teacher accounts and a head each.

One-off data seeding: teacher names are randomly generated placeholders since
no real HR data is available yet; every created teacher shares one default
password, printed at the end for the operator to hand out and rotate.
"""

import random

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction

from accounts.management.commands.uzbek_names import FIRST_NAMES, LAST_NAMES
from accounts.models import (
    Department,
    Foydalanuvchi,
    OqituvchiProfil,
    OqituvchiTuri,
    Rol,
)
from accounts.services import (
    mudir_tayinlash,
    oqituvchi_yaratish,
    vaqtinchalik_parol_tasodifiy,
)

DEPARTMENT_NAMES = [
    "Axborot tizimlari va texnologiyalari",
    "Raqamli texnologiyalar",
    "Menejment",
    "Ijtimoiy fanlar",
    "Buxgalteriya hisobi",
    "Xorijiy tillar",
    "Marketing",
]

PHONE_PREFIX = "+99890"
# Clear of the teacher range, which runs to +99890 0000603 (index*100 + offset).
OFFICE_ADMIN_PHONE = "+998909999999"


class Command(BaseCommand):
    help = "Create departments, random teacher accounts, and assign heads."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--parol",
            type=str,
            default="",
            help=(
                "Seed hisoblar uchun vaqtinchalik parol "
                "(bo'sh bo'lsa tasodifiy yaratiladi)."
            ),
        )

    def handle(self, *args: object, **options: object) -> None:
        turlari = list(OqituvchiTuri.objects.all())
        if not turlari:
            raise CommandError(
                "No OqituvchiTuri rows found. Create teacher types before seeding."
            )

        parol = str(options.get("parol") or "").strip() or vaqtinchalik_parol_tasodifiy(
            12
        )
        with transaction.atomic():
            self._seed_office_admin(parol)
            for index, nomi in enumerate(DEPARTMENT_NAMES):
                self._seed_department(nomi, index, turlari, parol)

        self.stdout.write(self.style.SUCCESS("Done."))
        self.stdout.write(
            f"One-time password for seeded accounts (change on login): {parol}"
        )

    def _seed_office_admin(self, parol: str) -> None:
        if Foydalanuvchi.objects.filter(telefon=OFFICE_ADMIN_PHONE).exists():
            self.stdout.write(f"Skipped (exists): office admin {OFFICE_ADMIN_PHONE}")
            return

        Foydalanuvchi.objects.create_user(
            telefon=OFFICE_ADMIN_PHONE,
            password=parol,
            first_name="Ofis",
            last_name="Admin",
            rol=Rol.OFFICE_ADMIN,
            parol_ozgartirish_kerak=True,
        )
        self.stdout.write(
            self.style.SUCCESS(f"Created: office admin ({OFFICE_ADMIN_PHONE})")
        )

    def _seed_department(
        self, nomi: str, index: int, turlari: list[OqituvchiTuri], parol: str
    ) -> None:
        department, created = Department.objects.get_or_create(nomi=nomi)
        if not created:
            self.stdout.write(f"Skipped (exists): {nomi}")
            return

        head_profil = self._create_teacher_profil(
            index * 100, department, turlari, parol
        )
        mudir_tayinlash(department, head_profil)

        for offset in range(1, 4):
            self._create_teacher_profil(
                index * 100 + offset, department, turlari, parol
            )

        self.stdout.write(self.style.SUCCESS(f"Created: {nomi} (head: {head_profil})"))

    def _create_teacher_profil(
        self,
        seed: int,
        department: Department,
        turlari: list[OqituvchiTuri],
        parol: str,
    ) -> OqituvchiProfil:
        profil = oqituvchi_yaratish(
            telefon=f"{PHONE_PREFIX}{seed:07d}",
            first_name=random.choice(FIRST_NAMES),
            last_name=random.choice(LAST_NAMES),
            parol=parol,
            kafedra=department,
            turi=random.choice(turlari),
        )
        profil.foydalanuvchi.parol_ozgartirish_kerak = True
        profil.foydalanuvchi.save(update_fields=["parol_ozgartirish_kerak"])
        return profil
