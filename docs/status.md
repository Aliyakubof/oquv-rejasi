# Status

Living snapshot of current state — what's in progress, what just landed, and what to watch out for. For product/domain background see `PRD.md`; for engineering guidelines see `GEMINI.md` and `CLAUDE.md`.

## Working on now

Comprehensive codebase hardening and verification completed across security, ORM performance, UI/UX responsiveness/accessibility, parser/code-quality refactoring, and deployment configuration.

## Done recently

- **Full audit remediation (Security, DB/ORM, UI/UX, Code Quality, Deploy):**
  - *Security hardening:* Added `ActiveUserMiddleware` (blocks deactivated accounts immediately across both HTML and HTMX `HX-Redirect`), sanitized tab/semester/filter query state and escaped `.docx` XML template substitutions safely without breaking Seminar-only table columns, hardened role/privilege checks (`SUPERADMIN` vs `OFFICE_ADMIN` vs mudir, `/dev/` superadmin guard, password validation), added `DasturTopshirish` transition guards & DB partial unique constraints, tightened cascade protections, HEMIS sync validation & year-scoped locking, and trusted-proxy `X-Forwarded-For` verification + formula/XML-safe Excel export (`plans/eksport.py`, `plans/audit.py`).
  - *DB & ORM performance:* Eliminated N+1 queries and duplicate queryset evaluations across dashboard, reja, semestrovka, and teacher workload views; removed hidden GET-request DB writes (`YARATILDI` auto-fix moved out of GET views); added `transaction.atomic()` + `select_for_update()` locks, bulk operations (`bulk_create`/`bulk_update`), `WebConfig.ready()` signal registration for live polling, and database performance indexes (`accounts/0005`, `plans/0017`, `plans/0018`).
  - *UI/UX & Frontend:* Added responsive mobile navbar toggle, `method="post"` on all `hx-post` forms, global HTMX progress indicator (`#htmx-yuklanish`), OOB `#app-messages` & `#oqituvchi-excel-btn` updates, accessible `<button class="group-toggle-btn">` controls, modal Tab focus trap & `modalConfirmed` reset, `jonli.js` dirty-input protection & `401` login redirect, WCAG AA contrast tokens & unclipped popovers with `x-transition` + `Esc` closing, A4 landscape `print.css`, and uncapped workload overload percentages with Uzbek apostrophe-aware initials (`web/templatetags/ui.py`).
  - *Code quality & Deployment:* Refactored `parser/`, `plans/`, and `web/views/` into compact (`<=40`-line) strictly typed helpers without `Any`, keeping `parser/` 100% Django-free; updated `settings.py` with `SECURE_PROXY_SSL_HEADER`, `TRUST_X_FORWARDED_FOR` / `TRUSTED_PROXY_IPS`, and isolated test `MEDIA_ROOT`; locked down Nginx `/media/` (`internal;`), removed unused `tez_orada.html`, and updated `.env.example`.

- **`plans` app: full DB layer for curricula and teacher workload** (branch `feat/plans-db`). Models: `OquvReja` (intake; manual `talabalar_soni`/`guruhlar_soni`), `Guruh` (named groups synced from the count), `Fan` + `FanVariant` (every curriculum line is a slot with 1+ variants; majburiy auto-selects its single variant, tanlov stays pending until the office head selects — only the selected variant counts in demand), `FanSemestr` (materialized per-semester hours via largest-remainder split of course totals weighted by weekly hours), `Yuklama` (delegation rows; partial unique indexes forbid double-assigning a group / second lecture teacher). Hour demand: lecture ×1, amaliyot/laboratoriya/seminar × group count, kurs ishi 2h × student (owner policy; lands on the course's last semester).
- `import_reja` management command (`--replace` preserves kafedra links + tanlov selections and refuses when yuklamalar exist; `--yil` covers sheets missing the o'quv yili cell — `sources/BHA.xlsx` needs it). `plans/services.py`: demand/allocated/qoldiq reports per reja/kurs/kafedra, per-teacher annual hours, `yuklama_kamomadi` deficit report vs `min_soat`. Django admin is the interim UI (selection form, talab/taqsimlangan/qoldiq columns, autocompletes). 68 Django tests in `plans/tests/`.
- `parser/` converted to a package (CLI is now `python -m parser.main`; `read_metadata` moved into `parser/parser.py`) so Django imports its functions directly.
- Phase 2 structural refactor: introduced `models.py` (`ColumnLayout`, `Course`, `Alternative`, `SelectiveSlot`), unified numeric coercion (`_to_int`/`_cell_int`), split `detect_course_columns` into focused helpers, unified the core/selective parse loops behind `_iter_section_rows` + `_breakdown`, and moved direction resolution fully into `parser.py`.
- Phase 1 correctness fixes: fixed `"Jami"` (no colon) stop-condition bug that broke selective slot 2.04 in `60110100_ppd.xlsx`; added credit-mismatch warning (hours/30 vs. sum of per-semester credits); added a warning when program duration can't be parsed; added `_clean_name` to strip stray newlines/`|` from course names.
- Selective course (tanlov fanlar) parsing, weekly-hours columns, and per-alternative hour breakdowns added.
- Three-module split: `parser.py` (extraction), `formatter.py` (Markdown rendering), `main.py` (orchestration/CLI).

## Watch out

- **Every spreadsheet is a different shape.** All historical bugs came from assuming one sample file's layout was universal — never hardcode column indices; always keyword-search or anchor-relative (see `CLAUDE.md` Known Edge Cases).
- Course numbers sometimes carry trailing periods (`"1.00."`); already normalized via `.rstrip(".")`, but any new comparison against a raw course-number string needs the same treatment.
- The `"Jami"` stop-condition matches with or without a trailing colon, and scans all cells in the row — don't narrow it back to the name column only.
- Direction metadata can be split across two vertically adjacent rows (`mmt_23.xlsx`); `resolve_direction` already handles this.
- `plans/tests/test_uploads.py::FayldanImportTests::test_haqiqiy_fayl_import_qilinadi` references `sources/BHA.xlsx`, which is no longer in the repo — pre-existing failure, unrelated to parser changes; needs either the fixture restored or the test repointed at a file that exists.
- `Yuklama.soat` is denormalized (computed in `save()`); re-import is blocked while yuklamalar exist, so it can't go stale today — but any future "edit hours in place" feature must recompute it. The kurs-ishi over-allocation check is `clean()`-level only (not a DB constraint).
- Tests use Django's built-in runner (`python manage.py test plans accounts web`), not pytest — pytest isn't in `requirements.txt`.
- The UI's "2025/2026" year filter is the calendar akademik yil (2025); `web` views only offer years from `tanlanadigan_yillar()` (≥ current, September rollover) — past hours are hidden by construction, not by permission.
- Kafedra-scope security lives in `KafedraMudiriTalabMixin.kafedra` — every `/kafedra/` view must resolve objects through it (`variant__kafedra=self.kafedra`), never trust URL/POST ids.
- `web/forms/yuklama.py` un-excludes `fan_semestr`/`tur`/`guruh` from ModelForm validation so the DB shape constraints surface as form errors — don't "simplify" that away or duplicates come back as 500s.
- HTMX mutation responses return the changed fragment plus `hx-swap-oob` stats (and `<template>`-wrapped `<tr>` for row swaps — raw `tr` fragments get dropped by the HTML parser outside a table).
- The `/ship` skill has been removed; there is no automated commit/push/log workflow currently wired up.
