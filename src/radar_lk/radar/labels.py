"""Radar wording shared by the dashboard and the brief (config/sources.yaml `radar_display`).

Held-back alerts (week flagged `completeness_low`) are shown greyed out, never hidden, with the
`held_back` label filled in with that week's reporting completeness.
"""

from __future__ import annotations

import math
import re

from radar_lk import CONFIG_PATH, load_config


def display_cfg() -> dict:
    return load_config()["radar_display"]


def labels() -> dict:
    return display_cfg()["labels"]


def held_back(completeness_pct: float | None, template: str | None = None) -> str:
    t = template or labels()["held_back"]
    if completeness_pct is None or (
        isinstance(completeness_pct, float) and math.isnan(completeness_pct)
    ):
        # completeness_low needs a value, so this should not happen; keep the sentence readable
        return t.replace(" ({completeness_pct:.0f}%)", "")
    return t.format(completeness_pct=float(completeness_pct))


def tiers_adopted() -> bool:
    return bool(display_cfg().get("tiers_adopted"))


def write_tiers_adopted(adopted: bool, why: str) -> None:
    """Record the two-tier decision in config (one line, replaced in place)."""
    text = CONFIG_PATH.read_text(encoding="utf-8")
    line = f"  tiers_adopted: {'true' if adopted else 'false'}   # {why}"
    text, n = re.subn(r"^  tiers_adopted:.*$", line, text, count=1, flags=re.M)
    if n != 1:
        raise RuntimeError("radar_display.tiers_adopted not found in config/sources.yaml")
    CONFIG_PATH.write_text(text, encoding="utf-8")
