"""Pull curriculum student/group counts from configured HEMIS API URL."""

from django.core.management.base import BaseCommand, CommandError, CommandParser

from plans.hemis_client import hemis_dan_yuklash, hemis_elementlarni_sinxronlash


class Command(BaseCommand):
    help = "Tashqi HEMIS API dan talabalar va guruhlar sonini sinxronlash."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--url",
            default="",
            help=(
                "HEMIS endpoint URL (bo'sh bo'lsa settings.HEMIS_BASE_URL ishlatiladi)."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Bazaga yozmasdan faqat olinadigan elementlar sonini ko'rsatish.",
        )

    def handle(self, *args: object, **options: object) -> None:
        url = str(options.get("url") or "").strip() or None
        try:
            elementlar = hemis_dan_yuklash(base_url=url)
        except (ValueError, ConnectionError) as err:
            raise CommandError(str(err)) from err

        if options.get("dry_run"):
            self.stdout.write(
                self.style.SUCCESS(
                    f"Dry-run: HEMIS dan {len(elementlar)} ta yozuv olindi."
                )
            )
            return

        yangilangan, xatolar = hemis_elementlarni_sinxronlash(elementlar)
        self.stdout.write(
            self.style.SUCCESS(
                f"Yangilandi: {len(yangilangan)} ta reja, xatolar: {len(xatolar)} ta."
            )
        )
        for xato in xatolar:
            self.stderr.write(self.style.WARNING(xato))
