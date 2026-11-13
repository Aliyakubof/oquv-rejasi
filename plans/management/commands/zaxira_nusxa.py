"""Create timestamped backup archive of the database and media files."""

import sqlite3
import subprocess
from io import StringIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.utils import timezone


def _sqlite_nusxa(db_path: Path, nishon: Path) -> None:
    manba = sqlite3.connect(str(db_path))
    vaqtincha = sqlite3.connect(str(nishon))
    try:
        manba.backup(vaqtincha)
    finally:
        vaqtincha.close()
        manba.close()


def _postgres_nusxa(db_conf: dict[str, object], nishon: Path) -> None:
    cmd = ["pg_dump", "--no-owner", "--no-privileges", "-f", str(nishon)]
    name = str(db_conf.get("NAME") or "")
    host = str(db_conf.get("HOST") or "")
    port = str(db_conf.get("PORT") or "")
    user = str(db_conf.get("USER") or "")
    if host:
        cmd.extend(["-h", host])
    if port:
        cmd.extend(["-p", port])
    if user:
        cmd.extend(["-U", user])
    if name:
        cmd.append(name)
    natija = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if natija.returncode != 0:
        raise CommandError(f"pg_dump xatosi: {natija.stderr.strip() or 'noma`lum'}")


def _json_dump_nusxa(nishon: Path) -> None:
    bufer = StringIO()
    call_command(
        "dumpdata",
        "--natural-foreign",
        "--natural-primary",
        "--exclude=contenttypes",
        "--exclude=auth.permission",
        stdout=bufer,
    )
    nishon.write_text(bufer.getvalue(), encoding="utf-8")


def _media_qoshish(arxiv: ZipFile, media_root: Path) -> int:
    if not media_root.exists():
        return 0
    soni = 0
    for fayl in media_root.rglob("*"):
        if fayl.is_file():
            arxiv.write(fayl, arcname=Path("media") / fayl.relative_to(media_root))
            soni += 1
    return soni


class Command(BaseCommand):
    help = "Ma'lumotlar bazasi va media fayllarning .zip zaxira nusxasini yaratish."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--chiqish",
            default="",
            help="Zaxira fayllari papkasi (standart: BASE_DIR/backups).",
        )
        parser.add_argument(
            "--faqat-db",
            action="store_true",
            help="Faqat bazani zaxiralash, media fayllarni o'tkazib yuborish.",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Bazani Django dumpdata JSON formatida zaxiralash.",
        )

    def handle(self, *args: object, **options: object) -> None:
        chiqish_matni = str(options.get("chiqish") or "").strip()
        katalog = (
            Path(chiqish_matni) if chiqish_matni else settings.BASE_DIR / "backups"
        )
        katalog.mkdir(parents=True, exist_ok=True)
        vaqt_tamga = timezone.localtime().strftime("%Y%m%d_%H%M%S")
        zip_yoli = katalog / f"zaxira_{vaqt_tamga}.zip"

        db_conf = settings.DATABASES["default"]
        engine = str(db_conf.get("ENGINE", "")).lower()
        json_rejim = bool(options.get("json"))

        db_vaqtincha: Path | None = None
        try:
            if json_rejim:
                db_vaqtincha = katalog / f"_tmp_db_{vaqt_tamga}.json"
                _json_dump_nusxa(db_vaqtincha)
                arxiv_ichki_nomi = "database.json"
            elif "sqlite3" in engine:
                db_path = Path(str(db_conf.get("NAME") or ""))
                if not db_path.exists():
                    raise CommandError(f"SQLite bazasi topilmadi: {db_path}")
                db_vaqtincha = katalog / f"_tmp_db_{vaqt_tamga}.sqlite3"
                _sqlite_nusxa(db_path, db_vaqtincha)
                arxiv_ichki_nomi = "db.sqlite3"
            elif "postgresql" in engine:
                db_vaqtincha = katalog / f"_tmp_db_{vaqt_tamga}.sql"
                _postgres_nusxa(db_conf, db_vaqtincha)
                arxiv_ichki_nomi = "database.sql"
            else:
                db_vaqtincha = katalog / f"_tmp_db_{vaqt_tamga}.json"
                _json_dump_nusxa(db_vaqtincha)
                arxiv_ichki_nomi = "database.json"

            media_soni = 0
            with ZipFile(zip_yoli, "w", compression=ZIP_DEFLATED) as arxiv:
                arxiv.write(db_vaqtincha, arcname=arxiv_ichki_nomi)
                if not options.get("faqat_db"):
                    media_soni = _media_qoshish(arxiv, Path(settings.MEDIA_ROOT))
        finally:
            if db_vaqtincha is not None:
                db_vaqtincha.unlink(missing_ok=True)

        self.stdout.write(
            self.style.SUCCESS(
                f"Zaxira nusxa yaratildi: {zip_yoli} (media fayllar: {media_soni} ta)"
            )
        )
