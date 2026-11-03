"""Screenshots of every dashboard page -> docs/figures/app_*.png (Playwright, headless Chromium).

    python scripts/screenshots.py            # starts streamlit on a free port, then shoots

Each page at the latest week and at one replay week (2024-W51, post-flood leptospirosis), at a
laptop width (1440 px); "This week" and "Outlook" also at a phone width (390 px).
"""

from __future__ import annotations

import socket
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "docs" / "figures"
PAGES = ["this_week", "map", "outlook", "track_record", "data_methods"]
WEEKS = {"latest": None, "replay": "2024-W51"}
HEIGHT = {"this_week": 1900, "map": 1500, "outlook": 1900, "track_record": 5200,
          "data_methods": 2600}  # fmt: skip


def path(page: str) -> str:
    return "" if page == "this_week" else page  # the default page is served at /


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_ready(page) -> None:
    page.wait_for_function(
        "document.body.innerText.includes('Population-level signals for planning')",
        timeout=120_000,
    )
    for _ in range(120):  # until the app stops running
        if not page.query_selector('[data-testid="stStatusWidget"]'):
            break
        time.sleep(0.5)
    time.sleep(2.5)  # plotly / images settle


def shoot(page, url: str, path: Path, full: bool = True) -> None:
    page.goto(url)
    wait_ready(page)
    page.screenshot(path=str(path), full_page=full)
    print(f"wrote {path.relative_to(REPO)}")


def main() -> None:
    port = free_port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", str(REPO / "app" / "streamlit_app.py"),
         "--server.headless", "true", "--server.port", str(port),
         "--browser.gatherUsageStats", "false", "--theme.base", "light"],
        cwd=REPO, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )  # fmt: skip
    try:
        base = f"http://127.0.0.1:{port}"
        with sync_playwright() as pw:
            b = pw.chromium.launch()
            for _ in range(60):
                try:
                    socket.create_connection(("127.0.0.1", port), timeout=1).close()
                    break
                except OSError:
                    time.sleep(1)
            for tag, week in WEEKS.items():
                for p in PAGES:
                    # Streamlit scrolls inside its own container, so a full-page capture stops at
                    # the viewport: use a viewport tall enough for each page instead
                    tall = b.new_page(viewport={"width": 1440, "height": HEIGHT[p]})
                    q = f"?week={week}" if week else ""
                    shoot(tall, f"{base}/{path(p)}{q}", OUT / f"app_{p}_{tag}.png", full=False)
                    tall.close()
            phone = b.new_page(viewport={"width": 390, "height": 2400}, device_scale_factor=2)
            for p in ("this_week", "outlook"):
                shoot(phone, f"{base}/{path(p)}", OUT / f"app_{p}_phone.png", full=False)
            b.close()
    finally:
        proc.terminate()


if __name__ == "__main__":
    main()
