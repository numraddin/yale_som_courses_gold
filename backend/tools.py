"""Agent tools over the Yale SOM course data.

Two tools are in play for the agent:

  1. search_courses — implemented here, searches data/yale_som_classes.json.
  2. web_search     — OpenAI's *native* web search, so there is no local
                      function to implement. It is attached to the agent in
                      agent.py via `capabilities=[NativeTool(WebSearchTool())]`
                      and runs provider-side. See the note at the bottom.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from models import Course, CourseSearchResult

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DATA_PATH = ROOT / "data" / "yale_som_classes.json"

MAX_RESULTS = 15


@lru_cache(maxsize=1)
def _load_courses() -> tuple[Course, ...]:
    """Parse and validate the course file once per process."""
    raw = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    return tuple(Course.model_validate(row) for row in raw)


def reload_courses() -> None:
    """Drop the cache so an edited data file is picked up without a restart."""
    _load_courses.cache_clear()


def all_courses() -> tuple[Course, ...]:
    return _load_courses()


def search_courses(query: str, units: float | None = None) -> CourseSearchResult:
    """Search the Yale SOM course catalog.

    Matches the query against course title, course number, faculty name and
    email, category, course type, meeting days and times, room, section,
    session, description, and faculty bio.

    Multi-word queries are treated as AND: every whitespace-separated term must
    appear somewhere in the course record. Matching is case-insensitive.

    Args:
        query: What to look for, e.g. "negotiation", "MGMT 7307",
            "Simonsohn", "Tuesday afternoon", or "accounting fall-1". Pass an
            empty string to match every course (useful with `units`).
        units: Optional exact credit-unit filter, e.g. 2 or 0.5. Use this
            argument instead of putting units in `query` — units is a bare
            number, so searching "2" as text would also hit course MGT 402 and
            room EVANS 4210. Can be combined with `query`.

    Returns:
        Matching courses, capped at 15. `total_matched` reports how many rows
        matched before the cap, and `truncated` says whether rows were dropped.
        When you only need a count, read `total_matched` — do not count the
        returned rows, which stop at the cap.
    """
    courses = _load_courses()
    terms = [t for t in (query or "").lower().split() if t]

    if not terms:
        matched = list(courses)
    else:
        matched = [c for c in courses if all(t in c.haystack() for t in terms)]

    if units is not None:
        target = float(units)
        matched = [c for c in matched if c.units_value() == target]

    # Stable, useful ordering: title-hits first, then by course number.
    needle = " ".join(terms)
    matched.sort(key=lambda c: (needle not in c.title.lower(), c.course_number))

    window = matched[:MAX_RESULTS]
    return CourseSearchResult(
        query=query,
        units=units,
        total_matched=len(matched),
        returned=len(window),
        truncated=len(matched) > len(window),
        courses=[c.to_match() for c in window],
    )


# --- web_search -------------------------------------------------------------
#
# web_search is OpenAI's native/server-side tool, requested through the
# Responses API. The model issues the search itself and the results never pass
# through this process, so there is nothing to implement here and no API key
# beyond PORTKEY_API_KEY is needed.
#
# It is wired up in agent.py:
#
#     from pydantic_ai import WebSearchTool
#     from pydantic_ai.capabilities import NativeTool
#     Agent(..., capabilities=[NativeTool(WebSearchTool())])
#
# Native calls surface as NativeToolCallPart / NativeToolReturnPart in the
# message history, which is how agent.py records "web_search" in tools_used.
