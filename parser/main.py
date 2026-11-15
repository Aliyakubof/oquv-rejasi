import argparse
import sys
from pathlib import Path

from parser.formatter import markdown_yarat
from parser.models import TahlilXatosi
from parser.parser import kitobni_tahlil_qil, pascal_korinishiga

MANBA_PAPKA = Path("sources")
CHIQISH_PAPKA = Path("output")


def chiqish_fayl_nomi(
    xlsx_yoli: Path, yonalish_kodi: str, yonalish_nomi: str, boshlanish_yili: str
) -> str:
    """Yo'nalish nomidan fayl nomini yasaydi; bo'lmasa asl fayl nomini oladi."""
    if yonalish_nomi:
        asos = (
            f"{pascal_korinishiga(yonalish_nomi)}_{yonalish_kodi}"
            if yonalish_kodi
            else pascal_korinishiga(yonalish_nomi)
        )
    else:
        asos = xlsx_yoli.stem
    return f"{asos}_{boshlanish_yili}" if boshlanish_yili else asos


def faylni_qayta_ishla(xlsx_yoli: Path) -> bool:
    try:
        natija = kitobni_tahlil_qil(xlsx_yoli)
    except (TahlilXatosi, OSError) as exc:
        print(f"  XATO: {xlsx_yoli.name}: {exc}", file=sys.stderr)
        return False

    sarlavha = natija.yonalish_nomi or xlsx_yoli.stem
    CHIQISH_PAPKA.mkdir(exist_ok=True)
    asos = chiqish_fayl_nomi(
        xlsx_yoli, natija.yonalish_kodi, natija.yonalish_nomi, natija.boshlanish_yili
    )
    chiqish_yoli = CHIQISH_PAPKA / (asos + ".md")
    chiqish_yoli.write_text(
        markdown_yarat(
            sarlavha,
            natija.boshlanish_yili,
            natija.daraja,
            f"{natija.davomiylik_yil:g} yil",
            natija.talim_shakli,
            natija.majburiy_fanlar,
            natija.tanlov_fanlar,
        ),
        encoding="utf-8",
    )
    print(
        f"  {xlsx_yoli.name} -> {chiqish_yoli}"
        f"  ({len(natija.majburiy_fanlar)} majburiy, "
        f"{len(natija.tanlov_fanlar)} tanlov blok)"
    )
    for ogohlantirish in natija.ogohlantirishlar:
        print(f"    OGOHLANTIRISH: {ogohlantirish}")
    return True


def asosiy() -> int:
    # Windows konsoli ko'pincha cp1252 da ishlaydi, o'zbekcha tutuq belgilar
    # chiqqanda yiqilib qolmasligi uchun oqimlarni yumshoq moslaymiz.
    for oqim in (sys.stdout, sys.stderr):
        if hasattr(oqim, "reconfigure"):
            oqim.reconfigure(errors="replace")

    cli = argparse.ArgumentParser(
        description="O'quv reja Excel (.xlsx) fayllarini tahlil qilish."
    )
    cli.add_argument(
        "fayllar",
        nargs="*",
        type=Path,
        help="Tahlil qilinadigan .xlsx fayllar (bo'sh qolsa sources/ dan oladi).",
    )
    argumentlar = cli.parse_args()

    xato_bor = False
    if argumentlar.fayllar:
        xlsx_fayllar = []
        for yol in argumentlar.fayllar:
            if not yol.exists():
                print(f"XATO: fayl topilmadi: {yol}", file=sys.stderr)
                xato_bor = True
            else:
                xlsx_fayllar.append(yol)
    else:
        xlsx_fayllar = sorted(
            f for f in MANBA_PAPKA.glob("*.xlsx") if not f.name.startswith("~$")
        )

    if not xlsx_fayllar:
        if not xato_bor:
            print(".xlsx fayllar topilmadi.")
        return 1 if xato_bor else 0
    for xlsx_yoli in xlsx_fayllar:
        if not faylni_qayta_ishla(xlsx_yoli):
            xato_bor = True
    return 1 if xato_bor else 0


if __name__ == "__main__":
    raise SystemExit(asosiy())
