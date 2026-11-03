"""AppTest smoke tests: every dashboard page renders at the latest week and at a replay week."""

from pathlib import Path

import pytest

st_testing = pytest.importorskip("streamlit.testing.v1")
AppTest = st_testing.AppTest

APP = str(Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py")
PAGES = {
    "this_week": "This week",
    "map": "Map",
    "outlook": "Outlook",
    "track_record": "Track record",
    "data_methods": "Data & methods",
}


@pytest.mark.parametrize("week", [None, "2024-W05"])
@pytest.mark.parametrize("page", PAGES)
def test_page_renders(page, week):
    at = AppTest.from_file(APP, default_timeout=120)
    at.session_state["start_page"] = page  # entrypoint runs, then this page
    if week:
        at.session_state["as_of"] = week
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    text = " ".join(m.value for m in at.markdown) + " " + " ".join(c.value for c in at.caption)
    assert "No diagnosis, treatment or prophylaxis advice." in text  # footer on every page
    assert at.title[0].value == PAGES[page]
    if week:
        assert any(
            f"Replay: viewing as of {week}" in w.value for w in list(at.warning) + list(at.info)
        )
