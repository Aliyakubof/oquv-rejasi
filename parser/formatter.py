from parser.models import Alternative, Course, SelectiveSlot


def fmt_num(value: int | float | None) -> str:
    """Render a numeric field for Markdown: None becomes an empty cell."""
    return "" if value is None else str(value)


def md_row(cells: list[str], suffix: str = "") -> str:
    """Assemble a Markdown table row from cell strings, plus an optional suffix."""
    return "| " + " | ".join(cells) + " |" + suffix


def breakdown_cells(obj: Course | Alternative | None) -> list[str]:
    """The six hour-breakdown cells of a Course/Alternative, or blanks if None."""
    if obj is None:
        return ["", "", "", "", "", ""]
    return [
        fmt_num(obj.classroom),
        fmt_num(obj.lecture),
        fmt_num(obj.practice),
        fmt_num(obj.lab),
        fmt_num(obj.seminar),
        fmt_num(obj.course_proj),
    ]


def _sem_cells(item: Course | SelectiveSlot, active_semesters: list[int]) -> str:
    return "".join(
        f" {fmt_num(item.semester_credits.get(s))} |"
        f" {fmt_num(item.semester_weekly_hours.get(s))} |"
        for s in active_semesters
    )


def _jadval_sarlavhasi(active_semesters: list[int]) -> tuple[str, str]:
    sem_header = "".join(f" S{s} | W{s} |" for s in active_semesters)
    sem_sep = "".join(" --- | --- |" for _ in active_semesters)
    header = (
        "| # | Code | Name | Hours | Credits | Classroom"
        " | Lecture | Practice | Lab | Seminar | Course Proj |" + sem_header
    )
    separator = (
        "|---|------|------|-------|---------|-----------|---------|"
        "----------|-----|---------|-------------|" + sem_sep
    )
    return header, separator


def _tanlov_qatorlari(
    selective_slots: list[SelectiveSlot],
    active_semesters: list[int],
    header: str,
    separator: str,
) -> list[str]:
    lines = ["", "## Tanlov Fanlar (Selective Courses)", "", header, separator]
    empty_sem = "".join("  |  |" for _ in active_semesters)
    for slot in selective_slots:
        first = slot.alternatives[0] if slot.alternatives else None
        cells = [
            slot.num,
            first.code if first else "",
            first.name if first else "",
            fmt_num(slot.hours),
            fmt_num(slot.derived_credits),
            *breakdown_cells(first),
        ]
        lines.append(md_row(cells, _sem_cells(slot, active_semesters)))
        for alt in slot.alternatives[1:]:
            alt_cells = ["", alt.code, alt.name, "", "", *breakdown_cells(alt)]
            lines.append(md_row(alt_cells, empty_sem))
    return lines


def _majburiy_qatorlar(
    core_courses: list[Course],
    active_semesters: list[int],
    header: str,
    separator: str,
) -> list[str]:
    lines = ["## Majburiy Fanlar (Core Courses)", "", header, separator]
    for course in core_courses:
        cells = [
            course.num,
            course.code,
            course.name,
            fmt_num(course.hours),
            fmt_num(course.derived_credits),
            *breakdown_cells(course),
        ]
        lines.append(md_row(cells, _sem_cells(course, active_semesters)))
    return lines


def build_markdown(
    title: str,
    start_year: str,
    degree: str,
    duration: str,
    edu_type: str,
    core_courses: list[Course],
    selective_slots: list[SelectiveSlot] | None = None,
) -> str:
    """Render parsed curriculum data into a Markdown document."""
    all_items = list(core_courses) + list(selective_slots or [])
    active_semesters = sorted(
        {sem for item in all_items for sem in item.semester_credits}
        | {sem for item in all_items for sem in item.semester_weekly_hours}
    )

    lines = [f"# Oquv Reja: {title}", ""]
    for yorliq, qiymat in (
        ("Akademik daraja", degree),
        ("O'qish muddati", duration),
        ("Ta'lim shakli", edu_type),
    ):
        if qiymat:
            lines.append(f"**{yorliq}:** {qiymat}")
    if degree or duration or edu_type:
        lines.append("")

    header, separator = _jadval_sarlavhasi(active_semesters)
    lines.extend(_majburiy_qatorlar(core_courses, active_semesters, header, separator))
    if selective_slots:
        lines.extend(
            _tanlov_qatorlari(selective_slots, active_semesters, header, separator)
        )
    lines.append("")
    if start_year:
        lines.extend(["---", f"**O'quv yili:** {start_year}", ""])
    return "\n".join(lines)
