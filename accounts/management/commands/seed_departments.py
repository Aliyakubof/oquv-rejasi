"""Kafedralar, sinov o'qituvchi hisoblari va har bir kafedraga mudir yaratish komandasi.

Bir martalik boshlang'ich to'ldirish: haqiqiy kadrlar bazasi hali yo'q paytda
tasodifiy o'zbekcha ismlar bilan hisob ochiladi; barchasiga bitta boshlang'ich parol
beriladi va oxirida ekranga chiqariladi (ilk kirishda almashtirilishi shart).
"""

import random

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction

from accounts.management.commands.uzbek_names import FAMILIYALAR, ISMLAR
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

KAFEDRA_NOMLARI = [
    "Axborot tizimlari va texnologiyalari",
    "Raqamli texnologiyalar",
    "Menejment",
    "Ijtimoiy fanlar",
    "Buxgalteriya hisobi",
    "Xorijiy tillar",
    "Marketing",
]

TELEFON_PREFIKSI = "+99890"
# O'qituvchilar +99890 0000603 gacha boradi (indeks*100 + siljish), to'qnashmaydi.
OFIS_ADMIN_TELEFONI = "+998909999999"


class Command(BaseCommand):
    help = "Kafedralar, tasodifiy o'qituvchi hisoblari va kafedra mudirlarini yaratadi."

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
                "OqituvchiTuri yozuvlari topilmadi. Avval lavozim turlarini yarating."
            )

        parol = str(options.get("parol") or "").strip() or vaqtinchalik_parol_tasodifiy(
            12
        )
        with transaction.atomic():
            self._ofis_admin_yarat(parol)
            for indeks, nomi in enumerate(KAFEDRA_NOMLARI):
                self._kafedra_yarat(nomi, indeks, turlari, parol)

        self.stdout.write(self.style.SUCCESS("Tayyor."))
        self.stdout.write(
            f"Yaratilgan hisoblar uchun bir martalik parol: {parol} "
            "(kirishda almashtiriladi)"
        )

    def _ofis_admin_yarat(self, parol: str) -> None:
        if Foydalanuvchi.objects.filter(telefon=OFIS_ADMIN_TELEFONI).exists():
            self.stdout.write(
                f"O'tkazildi (mavjud): ofis admin ({OFIS_ADMIN_TELEFONI})"
            )
            return

        Foydalanuvchi.objects.create_user(
            telefon=OFIS_ADMIN_TELEFONI,
            password=parol,
            first_name="Ofis",
            last_name="Admin",
            rol=Rol.OFFICE_ADMIN,
            parol_ozgartirish_kerak=True,
        )
        self.stdout.write(
            self.style.SUCCESS(f"Yaratildi: ofis admin ({OFIS_ADMIN_TELEFONI})")
        )

    def _kafedra_yarat(
        self, nomi: str, indeks: int, turlari: list[OqituvchiTuri], parol: str
    ) -> None:
        kafedra, yaratildi = Department.objects.get_or_create(nomi=nomi)
        if not yaratildi:
            self.stdout.write(f"O'tkazildi (mavjud): {nomi}")
            return

        mudir_profil = self._oqituvchi_yarat(indeks * 100, kafedra, turlari, parol)
        mudir_tayinlash(kafedra, mudir_profil)

        for siljish in range(1, 4):
            self._oqituvchi_yarat(indeks * 100 + siljish, kafedra, turlari, parol)

        self.stdout.write(
            self.style.SUCCESS(f"Yaratildi: {nomi} (mudir: {mudir_profil})")
        )

    def _oqituvchi_yarat(
        self,
        raqam_urugi: int,
        kafedra: Department,
        turlari: list[OqituvchiTuri],
        parol: str,
    ) -> OqituvchiProfil:
        profil = oqituvchi_yaratish(
            telefon=f"{TELEFON_PREFIKSI}{raqam_urugi:07d}",
            first_name=random.choice(ISMLAR),
            last_name=random.choice(FAMILIYALAR),
            parol=parol,
            kafedra=kafedra,
            turi=random.choice(turlari),
        )
        profil.foydalanuvchi.parol_ozgartirish_kerak = True
        profil.foydalanuvchi.save(update_fields=["parol_ozgartirish_kerak"])
        return profil
