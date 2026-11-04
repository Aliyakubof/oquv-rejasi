import argparse
import sys
from pathlib import Path

from parser.formatter import build_markdown
from parser.models import ParseError
from parser.parser import parse_workbook, to_pascal_case

SOURCES_DIR = Path("sources")
OUTPUT_DIR = Path("output")


def output_stem(
    xlsx_path: Path, direction_code: str, direction_name: str, start_year: str
) -> str:
    """Build the output filename stem from the program direction (falling back
    to the source filename), suffixed with the start year when known."""
    if direction_name:
        stem = (
            f"{to_pascal_case(direction_name)}_{direction_code}"
            if direction_code
            else to_pascal_case(direction_name)
        )
    else:
        stem = xlsx_path.stem
    return f"{stem}_{start_year}" if start_year else stem


def process_file(xlsx_path: Path) -> None:
    try:
        result = parse_workbook(xlsx_path)
    except ParseError as exc:
        print(f"  ERROR: {xlsx_path.name}: {exc}")
        return

    title = result.direction_name or xlsx_path.stem
    OUTPUT_DIR.mkdir(exist_ok=True)
    stem = output_stem(
        xlsx_path, result.direction_code, result.direction_name, result.start_year
    )
    out_path = OUTPUT_DIR / (stem + ".md")
    out_path.write_text(
        build_markdown(
            title,
            result.start_year,
            result.degree,
            f"{result.duration_years:g} yil",
            result.edu_type,
            result.core,
            result.slots,
        ),
        encoding="utf-8",
    )
    print(
        f"  {xlsx_path.name} -> {out_path}"
        f"  ({len(result.core)} core, {len(result.slots)} selective slots)"
    )
    for warning in result.warnings:
        print(f"    WARNING: {warning}")


def main() -> None:
    # Windows consoles often default to cp1252, which can't encode every
    # character in these Uzbek-language warnings (apostrophe variants, etc).
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")

    arg_parser = argparse.ArgumentParser(description="Parse oquv reja Excel files.")
    arg_parser.add_argument(
        "files",
        nargs="*",
        type=Path,
        help="One or more .xlsx files to parse. Defaults to all files in sources/.",
    )
    args = arg_parser.parse_args()

    if args.files:
        xlsx_files = []
        for p in args.files:
            if not p.exists():
                print(f"WARNING: file not found: {p}")
            else:
                xlsx_files.append(p)
    else:
        xlsx_files = sorted(
            f for f in SOURCES_DIR.glob("*.xlsx") if not f.name.startswith("~$")
        )

    if not xlsx_files:
        print("No .xlsx files found.")
        return
    for xlsx_path in xlsx_files:
        process_file(xlsx_path)


if __name__ == "__main__":
    main()
