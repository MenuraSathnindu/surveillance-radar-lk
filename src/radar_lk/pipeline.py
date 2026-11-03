"""One command for the whole weekly batch.

    python -m radar_lk.pipeline --all                  # download -> parse/validate -> radar ->
                                                       # outlook -> briefs
    python -m radar_lk.pipeline --all --force          # rerun every step
    python -m radar_lk.pipeline --steps radar,briefs   # only some steps
    python -m radar_lk.pipeline --all --with-backtests # also rebuild the radar backtest report

Idempotent: each step records a fingerprint of its inputs in data/logs/pipeline_state.json and is
skipped when the inputs have not changed since its last successful run (download and weather
always run, and only fetch what is new). A step's entry is removed from the state BEFORE it runs
and written back only after it exits 0, so a step that fails or is killed half-way is never
recorded as done and the next run redoes it. The state file is written atomically.

A failed download (e.g. the source site is down) is logged and the run continues on the data
already on disk (exit 0; the dashboard's stale-data banner then shows how old the latest WER issue
is). A failed weather step (e.g. a district without weather) also lets the run continue on the
previous weather file, but the run exits 1. Any other failure stops the run (exit 1). Every run
writes data/logs/pipeline_<timestamp>.log.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from datetime import date, datetime
from pathlib import Path

from radar_lk import CLEAN_DIR, CONFIG_PATH, DATA_DIR, RAW_DIR

LOGS = DATA_DIR / "logs"
STATE = LOGS / "pipeline_state.json"
STEPS = ["download", "weather", "parse", "radar", "outlook", "briefs"]


def _fingerprint(paths: list[Path]) -> str:
    h = hashlib.sha256()
    for p in paths:
        if p.is_dir():
            for f in sorted(p.rglob("*")):
                if f.is_file():
                    st = f.stat()
                    h.update(f"{f.relative_to(p)}|{st.st_size}".encode())
        elif p.exists():
            h.update(p.read_bytes())
        else:
            h.update(f"missing:{p}".encode())
    return h.hexdigest()[:16]


INPUTS = {
    "parse": lambda: [RAW_DIR / "wer", CONFIG_PATH],
    "radar": lambda: [CLEAN_DIR / "wer.parquet"],
    "outlook": lambda: [CLEAN_DIR / "wer.parquet", CLEAN_DIR / "weather.parquet"],
    "briefs": lambda: [
        CLEAN_DIR / "radar_signals.parquet",
        CLEAN_DIR / "outlook_forecasts.parquet",
    ],
}


def load_state() -> dict:
    """The recorded fingerprints; an unreadable state file counts as empty (everything reruns)."""
    try:
        return json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    except (OSError, ValueError):
        return {}


def save_state(state: dict) -> None:
    """Atomic write: a kill mid-write leaves the old file, never a truncated one."""
    STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    tmp.replace(STATE)


def commands(with_backtests: bool) -> dict[str, list[list[str]]]:
    y = date.today().year
    py = [sys.executable, "-m"]
    return {
        "download": [
            py + ["radar_lk.ingest.download", "--source", "wer", "--years", f"{y - 1}-{y}"],
            py + ["radar_lk.ingest.download", "--source", "ndcu_weekly"],
        ],
        "weather": [py + ["radar_lk.ingest.weather"]],
        "parse": [py + ["radar_lk.ingest.parse_wer"], py + ["radar_lk.ingest.publication_lag"]],
        "radar": [py + ["radar_lk.radar.run", "--reuse-fits"]]
        + ([py + ["radar_lk.radar.backtest", "--reuse"]] if with_backtests else []),
        "outlook": [py + ["radar_lk.outlook.backtest"]],
        "briefs": [py + ["radar_lk.brief.build"]],
    }


class Log:
    def __init__(self) -> None:
        LOGS.mkdir(parents=True, exist_ok=True)
        self.path = LOGS / f"pipeline_{datetime.now():%Y%m%d_%H%M%S}.log"
        self.f = open(self.path, "a", encoding="utf-8")

    def __call__(self, msg: str) -> None:
        line = f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}"
        print(line, flush=True)
        self.f.write(line + "\n")
        self.f.flush()


def run_cmd(cmd: list[str], log: Log) -> int:
    log(f"$ {' '.join(cmd[1:])}")
    p = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
        errors="replace",
    )  # fmt: skip
    for line in p.stdout:
        log.f.write("    " + line)
    log.f.flush()
    return p.wait()


def main(argv=None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--all", action="store_true", help="run every step")
    ap.add_argument("--steps", default="", help=f"comma-separated subset of {','.join(STEPS)}")
    ap.add_argument("--force", action="store_true", help="ignore fingerprints, rerun the steps")
    ap.add_argument("--with-backtests", action="store_true", help="also rebuild radar backtest")
    a = ap.parse_args(argv)
    steps = STEPS if a.all else [s for s in a.steps.split(",") if s]
    if not steps or any(s not in STEPS for s in steps):
        ap.error(f"choose --all or --steps from {STEPS}")
    log = Log()
    state = load_state()
    cmds = commands(a.with_backtests)
    failed = []
    log(f"pipeline start: steps {steps}{' (forced)' if a.force else ''}")
    for s in steps:
        fp = _fingerprint(INPUTS[s]()) if s in INPUTS else None
        if fp and not a.force and state.get(s) == fp:
            log(f"[{s}] inputs unchanged since the last successful run: skipped")
            continue
        if state.pop(s, None) is not None:
            save_state(state)  # not "done" again until this run of the step succeeds
        t0 = time.time()
        rc = 0
        for cmd in cmds[s]:
            rc = run_cmd(cmd, log)
            if rc != 0:
                break
        dt = time.time() - t0
        if rc != 0:
            log(f"[{s}] FAILED (exit {rc}, {dt:.0f}s); see the indented output above in the log")
            failed.append(s)
            if s in ("download", "weather"):
                continue  # source down: carry on with the data already on disk
            break
        if fp:
            state[s] = fp
            save_state(state)
        log(f"[{s}] ok ({dt:.0f}s)")
    status = "failed: " + ", ".join(failed) if failed else "all steps ok"
    log(f"pipeline end: {status}; log {log.path}")
    return 1 if any(s != "download" for s in failed) else 0


if __name__ == "__main__":
    sys.exit(main())
