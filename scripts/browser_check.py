"""Real-browser checks of the dashboard (Playwright, headless Chromium).

    python scripts/browser_check.py
    python scripts/browser_check.py --python F:/_fv/Scripts/python.exe   # serve from another venv

1. every page URL resolves (/this_week, /map, ...) and "/" forwards to /this_week;
2. ?week= survives the forward (replay links work);
3. clicking a district on the map selects it (small multiples follow the click).
Exit code 1 on any failure.
"""

from __future__ import annotations

import socket
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[1]
PAGES = {
    "this_week": "This week",
    "map": "Map",
    "outlook": "Outlook",
    "track_record": "Track record",
    "data_methods": "Data & methods",
}


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def ready(page) -> None:
    page.wait_for_function(
        "document.body.innerText.includes('Population-level signals for planning')",
        timeout=120_000,
    )
    time.sleep(1.5)


def title(page) -> str:
    return page.locator("h1").first.inner_text().strip()


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--python", default=sys.executable, help="interpreter that serves the app")
    server_py = ap.parse_args().python
    port = free_port()
    proc = subprocess.Popen(
        [server_py, "-m", "streamlit", "run", str(REPO / "app" / "streamlit_app.py"),
         "--server.headless", "true", "--server.port", str(port)],
        cwd=REPO, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )  # fmt: skip
    fails = []
    try:
        base = f"http://127.0.0.1:{port}"
        for _ in range(60):
            try:
                socket.create_connection(("127.0.0.1", port), timeout=1).close()
                break
            except OSError:
                time.sleep(1)
        with sync_playwright() as pw:
            b = pw.chromium.launch()
            page = b.new_page(viewport={"width": 1440, "height": 1400})
            for slug, want in PAGES.items():
                page.goto(f"{base}/{slug}")
                ready(page)
                got = title(page)
                nf = "Page not found" in page.inner_text("body")
                ok = got == want and not nf
                print(
                    f"/{slug}: title {got!r}{' + Page not found' if nf else ''}",
                    "OK" if ok else "FAIL",
                )
                ok or fails.append(f"/{slug}")
            page.goto(f"{base}/?week=2024-W51")
            ready(page)
            ok = page.url.split("?")[0].endswith("/this_week") and "week=2024-W51" in page.url
            ok = ok and "Replay: viewing as of 2024-W51" in page.inner_text("body")
            print(f"/ -> {page.url}", "OK" if ok else "FAIL")
            ok or fails.append("/ forward with ?week=")

            page.goto(f"{base}/map?week=2024-W51")
            ready(page)

            def shown() -> str:  # the district whose small multiples are on screen
                txt = page.inner_text("body")
                i = txt.find(": last 52 reported weeks")
                return txt[: max(i, 0)].splitlines()[-1].strip()

            before = shown()
            polys = page.locator(".choroplethlayer path")
            polys.first.wait_for(state="attached", timeout=60_000)  # plotly draws after load
            time.sleep(1)
            n = polys.count()
            # polygons are drawn in the order of the (alphabetical) district list, Kalmunai excluded
            areas = sorted(
                ["Ampara", "Anuradhapura", "Badulla", "Batticaloa", "Colombo", "Galle", "Gampaha",
                 "Hambantota", "Jaffna", "Kalutara", "Kandy", "Kegalle", "Kilinochchi",
                 "Kurunegala", "Mannar", "Matale", "Matara", "Monaragala", "Mullaitivu",
                 "Nuwara Eliya", "Polonnaruwa", "Puttalam", "Ratnapura", "Trincomalee", "Vavuniya"]
            )  # fmt: skip
            target = "Anuradhapura"
            bb = polys.nth(areas.index(target)).bounding_box()
            x, y = bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2
            page.mouse.move(x, y)
            time.sleep(0.5)
            page.mouse.click(x, y)  # a real click at the polygon's centre
            time.sleep(4)
            ready(page)
            after = shown()
            ok = n == 25 and after == target and before != target
            print(
                f"map click: {n} polygons; shown district {before!r} -> {after!r}",
                "OK" if ok else "FAIL",
            )
            ok or fails.append("map click")
            b.close()
    finally:
        proc.terminate()
    print("ALL OK" if not fails else f"FAILED: {fails}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
