"""Typed data model shared between the parser (producer) and formatter/future
serializers (consumers).

Numbers stay `int | None` (parsing concern); rendering to strings lives in the
formatter. These types make the producer↔consumer contract explicit and give
`dataclasses.asdict` a clean future JSON/DB path.
"""

from dataclasses import dataclass, field
from typing import NamedTuple


class ParseError(Exception):
    """The sheet's structure couldn't be reliably detected.

    Raised instead of falling back to a guessed column/row position — a wrong
    guess produces numbers that look plausible but are silently wrong.
    """


class ColumnLayout(NamedTuple):
    """0-based column indices for one curriculum sheet, detected dynamically.

    `lab`, `seminar`, and `course_proj` are None when the sheet has no header
    for that hour type (map §4.3: not every file carries all five subcategory
    columns) — the course still parses, with 0 hours for that type.
    """

    num: int
    code: int
    name: int
    hours: int
    classroom: int
    lecture: int
    practice: int
    lab: int | None
    seminar: int | None
    course_proj: int | None

    @property
    def breakdown(self) -> tuple[int, int, int, int | None, int | None, int | None]:
        """The six hour-breakdown column indices, in canonical field order."""
        return (
            self.classroom,
            self.lecture,
            self.practice,
            self.lab,
            self.seminar,
            self.course_proj,
        )


def derived_credits(hours: int | None) -> int | None:
    """Credits implied by total hours (1 credit = 30 hours)."""
    return None if hours is None else hours // 30


@dataclass
class Course:
    """One mandatory (majburiy) course with its full hour breakdown."""

    num: str
    code: str
    name: str
    hours: int | None
    classroom: int
    lecture: int
    practice: int
    lab: int
    seminar: int
    course_proj: int
    semester_credits: dict[int, int] = field(default_factory=dict)
    semester_weekly_hours: dict[int, int] = field(default_factory=dict)

    @property
    def derived_credits(self) -> int | None:
        return derived_credits(self.hours)


@dataclass
class Alternative:
    """One course option offered within a selective slot."""

    code: str
    name: str
    classroom: int
    lecture: int
    practice: int
    lab: int
    seminar: int
    course_proj: int


@dataclass
class SelectiveSlot:
    """One selective (tanlov) slot: shared hours/credits plus its alternatives."""

    num: str
    hours: int | None
    semester_credits: dict[int, int] = field(default_factory=dict)
    semester_weekly_hours: dict[int, int] = field(default_factory=dict)
    alternatives: list[Alternative] = field(default_factory=list)

    @property
    def derived_credits(self) -> int | None:
        return derived_credits(self.hours)


@dataclass
class ParseResult:
    """Everything extracted from one workbook, plus the warnings collected
    along the way. Structural failures raise ParseError instead of landing
    here — a ParseResult is always safe to use."""

    direction_code: str
    direction_name: str
    start_year: str
    degree: str
    duration_years: float
    edu_type: str
    core: list[Course]
    slots: list[SelectiveSlot]
    warnings: list[str] = field(default_factory=list)
