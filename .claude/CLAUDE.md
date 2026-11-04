# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository. It covers how to write code for this project. For product/domain background (what the tool does, glossary, Excel format, output format, roadmap), see `PRD.md`. For current implementation state, see `status.md`.

## Response style

Be brief. Answer in short, direct sentences. No preambles, no recaps of what I asked, no "Great question!" filler. When explaining what you changed, 5 sentences max. When proposing a plan, use a numbered list — no paragraph per step. Skip the summary paragraph at the end. If I need more detail I'll ask.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run Django dev server
python manage.py runserver

# Run migrations
python manage.py migrate

# Parse all files in sources/
python -m parser.main

# Parse specific file(s)
python -m parser.main sources/mmt_23.xlsx

# Import parsed curricula into the Django DB
python manage.py import_reja sources/mmt_23.xlsx
python manage.py import_reja sources/mmt_23.xlsx --replace

# Run tests
python manage.py test

# Format + lint
ruff format .
ruff check .
ruff check --fix .
```

## Linting & Formatting

Tool: ruff. Config lives in `pyproject.toml`
(line-length 88; rules E, F, W, I).

Always run `ruff format .` before committing. If ruff and a hand-written style
choice conflict, ruff wins — don't use `# fmt: skip` to preserve alignment.

## Tech Stack

- **Python 3.10+** (uses lowercase `tuple[...]` type hints)
- **openpyxl** — reads `.xlsx` files with `data_only=True` (formulas resolve to cached values)
- **Standard library only** otherwise (`re`, `pathlib`)
- **Django** for the backend
- **Frontend** — Django templates with HTML, CSS. HTMX for dynamic server interactions, Alpine.js for client-side state

## Document maps

The `docs/` folder contains structural maps of the documents this project parses and generates:

- `docs/oquv_reja_map.md` — row-by-row and column-by-column layout of the O'quv Reja Excel file. Defines where metadata lives, where course rows start, section markers, column positions, and known format variations across files.
- `docs/oquv_dastur_map.md` — field-by-field layout of the O'quv Dastur DOCX template. Defines which cells/paragraphs the platform pre-fills and which are left for teachers.

**Read the relevant map before writing or modifying any parser or document-generation code.** The maps are the source of truth for document structure; `PRD.md` explains the domain, the maps explain the byte-level layout.

## Architecture rules

- One module = one responsibility. New concern → new file, not a new section in an existing file.
- Parser modules live in `parser/`. Django app code lives in the Django apps. Don't import Django in parser modules — the parser is a standalone package.
- Document generation (O'quv Dastur DOCX creation) is its own module, separate from the parser.

## Code conventions

- Full type hints on all public functions. No `Any` in signatures.
- Functions under ~40 lines; split otherwise.
- Names over comments. Comments only for "why" (Excel-format quirks, non-obvious decisions), never for "what".
- Raise specific exceptions with messages on parse failures — never silently skip malformed rows.
- Return dataclasses or typed dicts from the parser, not raw tuples or openpyxl objects.


## Rules

- After finishing a task, explain what you changed and why in 5 sentences max.
- Before writing parser or docx-generation code, read the relevant document map in `docs/`.
- When a task touches the Excel parsing logic, verify against at least 2 sample files from `sources/`.