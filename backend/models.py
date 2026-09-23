"""Pydantic models shared by tools.py and agent.py.

The raw rows in data/yale_som_classes.json use human-readable keys with spaces
("Course Title", "Faculty 1"). `Course` maps those onto python-friendly field
names via aliases, so the rest of the backend never touches the raw spellings.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# Days appear two ways in the source data, neither of them spelled out:
#   Daytimes    — single letters before the time, e.g. "M T W Th F 8:30 AM-4:30 PM"
#   Timings Day — comma abbreviations, e.g. "Mo,Tu,We,Th,Fr" (blank on most rows)
# Both are expanded to full day names so a search for "Tuesday" works.
_DAY_TOKENS = {
    "m": "monday", "mo": "monday", "mon": "monday",
    "t": "tuesday", "tu": "tuesday", "tue": "tuesday", "tues": "tuesday",
    "w": "wednesday", "we": "wednesday", "wed": "wednesday",
    "th": "thursday", "thu": "thursday", "thur": "thursday", "thurs": "thursday",
    "f": "friday", "fr": "friday", "fri": "friday",
    "sa": "saturday", "sat": "saturday",
    "su": "sunday", "sun": "sunday",
}


class Course(BaseModel):
    """One row of yale_som_classes.json.

    Every field in the source data is a string, including numeric-looking ones
    such as Units and TermCode, so they are kept as strings here rather than
    coerced. Missing keys default to "" so a partial row never breaks a search.
    """

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    course_id: str = Field("", alias="Course ID")
    course_number: str = Field("", alias="Course Number")
    title: str = Field("", alias="Course Title")
    category: str = Field("", alias="Course Category")
    course_type: str = Field("", alias="Course Type")
    description: str = Field("", alias="Course Description")

    faculty: str = Field("", alias="Faculty 1")
    faculty_email: str = Field("", alias="Faculty 1 Email")
    faculty_bio: str = Field("", alias="faculty_bio")

    daytimes: str = Field("", alias="Daytimes")
    day: str = Field("", alias="Timings Day")
    start_time: str = Field("", alias="Timings StartTime")
    end_time: str = Field("", alias="Timings EndTime")
    room: str = Field("", alias="Room")

    session: str = Field("", alias="Course Session")
    session_start_date: str = Field("", alias="Course Session Start date")
    session_end_date: str = Field("", alias="Course Session End Date")
    term_code: str = Field("", alias="TermCode")

    section: str = Field("", alias="Section")
    units: str = Field("", alias="Units")
    bid_or_permission: str = Field("", alias="Bid Or Permission")
    syllabus: str = Field("", alias="Syllabus")
    old_syllabus: str = Field("", alias="Old Syllabus")
    visible: str = Field("", alias="Visible")

    def haystack(self) -> str:
        """Lowercased text blob used for substring matching in search_courses.

        `units` is deliberately excluded: it is a bare number, and substring
        matching on "2" collides with course numbers (MGT 402), rooms (EVANS
        4210) and times. Unit filtering goes through search_courses' `units`
        argument, which compares numerically.
        """
        return " ".join(
            [
                self.course_number,
                self.title,
                self.category,
                self.course_type,
                self.faculty,
                self.faculty_email,
                self.daytimes,
                self.day,
                self.start_time,
                self.end_time,
                self.room,
                self.session,
                self.section,
                " ".join(self.days()),
                self.description,
                self.faculty_bio,
            ]
        ).lower()

    def units_value(self) -> float | None:
        """Units as a number, or None when the field is blank/unparseable."""
        try:
            return float(self.units)
        except (TypeError, ValueError):
            return None

    def days(self) -> list[str]:
        """Full weekday names this course meets on, in week order.

        Reads both day fields. In `daytimes` only the leading alphabetic tokens
        are days — parsing stops at the first token containing a digit, which
        is where the time starts.
        """
        found: list[str] = []

        def add(token: str) -> None:
            day = _DAY_TOKENS.get(token.strip().lower())
            if day and day not in found:
                found.append(day)

        for token in self.day.replace(",", " ").split():
            add(token)

        for token in self.daytimes.split():
            if any(ch.isdigit() for ch in token):
                break
            add(token)

        order = list(_DAY_TOKENS.values())
        return sorted(found, key=order.index)

    def to_match(self) -> CourseMatch:
        """Project onto the compact shape handed back to the model."""
        return CourseMatch(
            course_number=self.course_number,
            title=self.title,
            faculty=self.faculty,
            faculty_email=self.faculty_email,
            daytimes=self.daytimes,
            room=self.room,
            units=self.units,
            category=self.category,
            session=self.session,
            description=_clip(self.description, 600),
            faculty_bio=_clip(self.faculty_bio, 400),
        )


class CourseMatch(BaseModel):
    """A search hit as the agent sees it.

    Deliberately narrower than `Course`: long prose is clipped and bookkeeping
    fields (Visible, TermCode, syllabus URLs) are dropped so a 15-row result
    stays a reasonable size in the model's context.
    """

    course_number: str
    title: str
    faculty: str
    faculty_email: str = ""
    daytimes: str = ""
    room: str = ""
    units: str = ""
    category: str = ""
    session: str = ""
    description: str = ""
    faculty_bio: str = ""


class CourseSearchResult(BaseModel):
    """Return type of the search_courses tool."""

    query: str
    units: float | None = None
    total_matched: int
    returned: int
    truncated: bool
    courses: list[CourseMatch] = Field(default_factory=list)


class ToolInvocation(BaseModel):
    """One tool call recorded for the audit trail."""

    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    result_summary: str = ""


class AuditEntry(BaseModel):
    """One agent loop, appended to output/audit_trail.json."""

    time: str
    user_message: str
    thoughts: list[str] = Field(default_factory=list)
    tool_calls: list[ToolInvocation] = Field(default_factory=list)
    reply: str = ""
    stop_reason: str = ""


class AgentResult(BaseModel):
    """What run_agent hands back to main.py's /api/chat route."""

    reply: str
    tools_used: list[str] = Field(default_factory=list)


def _clip(text: str, limit: int) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "…"
