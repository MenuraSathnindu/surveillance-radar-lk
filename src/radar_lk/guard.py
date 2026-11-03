"""Non-clinical guard: no treatment, diagnosis or prophylaxis vocabulary in anything we publish.

The blocklist and the exempt disclaimer sentences live in config/sources.yaml (`nonclinical`).
`assert_nonclinical` raises on any hit; the brief build calls it on every brief and the tests
call it on the dashboard's text.
"""

from __future__ import annotations

import re
from functools import lru_cache

from radar_lk import load_config


class NonClinicalError(ValueError):
    pass


@lru_cache(maxsize=1)
def _rules() -> tuple[re.Pattern, tuple[str, ...]]:
    c = load_config()["nonclinical"]
    words = sorted({w.lower() for w in c["blocklist"]}, key=len, reverse=True)
    pat = re.compile(r"\b(" + "|".join(re.escape(w) for w in words) + r")\b", re.IGNORECASE)
    return pat, tuple(c["allowed_phrases"])


def hits(text: str) -> list[str]:
    """Blocked words found in `text` (after removing the approved disclaimer sentences)."""
    pat, allowed = _rules()
    for a in allowed:
        text = text.replace(a, " ")
    return [m.group(0) for m in pat.finditer(text)]


def assert_nonclinical(text: str, where: str = "text") -> None:
    h = hits(text)
    if h:
        raise NonClinicalError(f"clinical vocabulary in {where}: {sorted(set(h))}")
