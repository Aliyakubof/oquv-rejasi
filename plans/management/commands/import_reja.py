from argparse import ArgumentParser
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from plans.importer import ImportNatija, ImportXato, excel_reja_oqi, import_reja


class Command(BaseCommand):
    help = "O'quv reja .xlsx fayllarini bazaga import qiladi."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("files", nargs="+", type=Path)
        parser.add_argument(
            "--replace",
            action="store_true",
            help="Mavjud rejani qayta yuklaydi (yuklamalar bo'lmasa).",
        )
        parser.add_argument(
            "--yil",
            type=int,
            default=None,
            help="Boshlanish yili; varaqda o'quv yili bo'lmasa majburiy.",
        )

    def handle(self, *args: object, **options: object) -> None:
        xatolar = 0
        for yol in options["files"]:
            try:
                natija = self._bitta_fayl(yol, options)
                self._chiqarish(yol, natija)
            except ImportXato as xato:
                self.stderr.write(self.style.ERROR(f"{yol.name}: {xato}"))
                xatolar += 1
        if xatolar:
            raise CommandError(f"{xatolar} ta fayl import qilinmadi")

    def _bitta_fayl(self, yol: Path, options: dict[str, object]) -> ImportNatija:
        if not yol.exists():
            raise ImportXato("fayl topilmadi")
        return import_reja(
            excel_reja_oqi(yol, boshlanish_yili=options["yil"]),
            almashtirish=options["replace"],
        )

    def _chiqarish(self, yol: Path, natija: ImportNatija) -> None:
        holat = "yaratildi" if natija.yaratildi else "yangilandi"
        self.stdout.write(
            f"{yol.name} -> {natija.reja} "
            f"({natija.fan_soni} fan, {natija.variant_soni} variant) {holat}"
        )
        for ogohlantirish in natija.ogohlantirishlar:
            self.stdout.write(self.style.WARNING(f"  OGOHLANTIRISH: {ogohlantirish}"))
