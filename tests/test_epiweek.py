from datetime import date

import pytest

from radar_lk.harmonise.epiweek import block_from_range, canonical_bounds, canonical_week


def test_monday_sunday_week_2026():
    # WER Vol 53 No 34 table reports 10–16 Aug 2026 (Mon–Sun)
    assert block_from_range(date(2026, 8, 10), date(2026, 8, 16)) == (2026, 33)


def test_saturday_friday_week_maps_to_thursday_iso_week():
    # Sat 6 Jan 2024 – Fri 12 Jan 2024 contains Thu 11 Jan 2024 = ISO 2024-W02
    assert canonical_week(date(2024, 1, 6)) == (2024, 2)


def test_year_boundary_uses_thursday():
    # Sat 28 Dec 2024 – Fri 3 Jan 2025: Thursday 2 Jan 2025 -> 2025-W01
    assert canonical_week(date(2024, 12, 28)) == (2025, 1)


def test_53_week_year():
    # 2026 has 53 ISO weeks (1 Jan 2026 is a Thursday)
    assert canonical_week(date(2026, 12, 28)) == (2026, 53)


def test_bounds_roundtrip():
    start, end = canonical_bounds(2026, 33)
    assert (start, end) == (date(2026, 8, 10), date(2026, 8, 16))
    assert canonical_week(start) == (2026, 33)


def test_bad_range_raises():
    with pytest.raises(ValueError):
        block_from_range(date(2026, 8, 10), date(2026, 8, 15))
