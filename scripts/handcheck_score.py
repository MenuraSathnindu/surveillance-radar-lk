"""Score the filled hand-check pack and put the result into docs/EXTRACTION_REPORT.md.

    python scripts/handcheck_score.py [CSV ...]   # several filled packs are pooled

Reads `verified` (Y/N) and `actual_value`; writes docs/handcheck_result.md (which the report
generator embeds on every rerun) and replaces the hand-check section of the current report.
"""

from __future__ import annotations

import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
DEFAULT = REPO / "data" / "handcheck" / "v2" / "handcheck.csv"
FRAGMENT = REPO / "docs" / "handcheck_result.md"
REPORT = REPO / "docs" / "EXTRACTION_REPORT.md"
START, END = "<!-- handcheck:start -->", "<!-- handcheck:end -->"


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return float("nan"), float("nan")
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (c - h) / d, (c + h) / d


def _rel(p: Path) -> str:
    try:
        return p.relative_to(REPO).as_posix()
    except ValueError:
        return p.as_posix()


def score(csv_paths: Path | list[Path]) -> str:
    paths = [csv_paths] if isinstance(csv_paths, Path) else list(csv_paths)
    parts = []
    for p in paths:
        d = pd.read_csv(p, dtype={"verified": str, "actual_value": str, "notes": str})
        d.insert(0, "pack", p.parent.name)
        parts.append(d)
    df = pd.concat(parts, ignore_index=True)
    csv_path = paths[0] if len(paths) == 1 else None
    v = df["verified"].fillna("").str.strip().str.upper()
    bad = v[~v.isin(["Y", "N", ""])]
    if len(bad):
        raise SystemExit(f"`verified` must be Y, N or empty; found {sorted(set(bad))}")
    done = df[v.isin(["Y", "N"])]
    k = int((v == "Y").sum())
    n = len(done)
    lo, hi = wilson(k, n)
    lines = [
        "## Hand-check (manual verification against the rendered page)",
        "",
        f"Scored {datetime.now(timezone.utc):%Y-%m-%d} from "
        + (f"`{_rel(csv_path)}`. " if csv_path else ", ".join(f"`{_rel(p)}`" for p in paths) + ". ")
        + f"Cells checked: **{n}** of {len(df)}; correct: **{k}**; accuracy "
        + (
            f"**{100 * k / n:.1f}%** (95% Wilson interval {100 * lo:.1f}-{100 * hi:.1f}%)."
            if n
            else "n/a."
        ),
    ]
    wrong = df[v == "N"]
    if len(wrong):
        lines += [
            "",
            "| no | issue | district | disease | column | extracted | actual | notes |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for _, r in wrong.iterrows():
            lines.append(
                f"| {r['no']} | {r['issue']} | {r['district']} | {r['disease']} | {r['column']} | "
                f"{r['extracted_value']} | "
                f"{r['actual_value'] if isinstance(r['actual_value'], str) else ''} | "
                f"{r['notes'] if isinstance(r['notes'], str) else ''} |"
            )
    if n < len(df):
        lines += ["", f"{len(df) - n} cells not yet checked."]
    return "\n".join(lines) + "\n"


def main() -> None:
    paths = [Path(a).resolve() for a in sys.argv[1:]] or [DEFAULT]
    text = score(paths if len(paths) > 1 else paths[0])
    FRAGMENT.write_text(text, encoding="utf-8")
    rep = REPORT.read_text(encoding="utf-8")
    block = f"{START}\n{text}{END}"
    if START in rep and END in rep:
        rep = rep[: rep.index(START)] + block + rep[rep.index(END) + len(END) :]
    else:
        rep = rep.rstrip() + "\n\n" + block + "\n"
    REPORT.write_text(rep, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
