"""One canonical epidemiological week for every record.

Sri Lanka's reporting week was Saturday–Friday before 2026 and Monday–Sunday from 2026.
Both are mapped to a canonical week by the Thursday rule: a week belongs to the ISO year/week
of the Thursday it contains. Every 7-day block contains exactly one Thursday, so the mapping
is unambiguous whatever weekday the block starts on.

Canonical key: (epi_year, epi_week) = ISO calendar of that Thursday.
"""

from __future__ import annotations

from datetime import date, timedelta

THURSDAY = 3  # date.weekday(): Mon=0 ... Sun=6


def thursday_of(week_start: date) -> date:
    """The Thursday inside the 7-day block starting at week_start."""
    return week_start + timedelta(days=(THURSDAY - week_start.weekday()) % 7)


def canonical_week(week_start: date) -> tuple[int, int]:
    """(epi_year, epi_week) for a 7-day reporting block starting on week_start."""
    iso = thursday_of(week_start).isocalendar()
    return iso.year, iso.week


def canonical_bounds(epi_year: int, epi_week: int) -> tuple[date, date]:
    """Monday–Sunday bounds of a canonical week (for display and joins with weather)."""
    monday = date.fromisocalendar(epi_year, epi_week, 1)
    return monday, monday + timedelta(days=6)


def block_from_range(start: date, end: date) -> tuple[int, int]:
    """Map a printed date range (e.g. '10–16 Aug 2026') to the canonical week.

    Raises if the range is not exactly 7 days, which usually means a parsing error.
    """
    if (end - start).days != 6:
        raise ValueError(f"reporting range {start}..{end} is not 7 days")
    return canonical_week(start)
