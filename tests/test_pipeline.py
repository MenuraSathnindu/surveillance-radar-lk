"""Pipeline bookkeeping: a failed or killed step is never recorded as done."""

import json
import sys

import pytest

from radar_lk import pipeline as pl


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """Two fake fingerprinted steps whose commands we control; state and logs in tmp_path."""
    inp = tmp_path / "input.txt"
    inp.write_text("v1")
    monkeypatch.setattr(pl, "LOGS", tmp_path / "logs")
    monkeypatch.setattr(pl, "STATE", tmp_path / "logs" / "pipeline_state.json")
    monkeypatch.setattr(pl, "STEPS", ["radar", "briefs"])
    monkeypatch.setattr(pl, "INPUTS", {"radar": lambda: [inp], "briefs": lambda: [inp]})
    behaviour = {"radar": 0, "briefs": 0}

    def cmd(code):
        return [sys.executable, "-c", f"import sys; sys.exit({code})"]

    monkeypatch.setattr(
        pl,
        "commands",
        lambda with_backtests: {s: [cmd(behaviour[s])] for s in ("radar", "briefs")},
    )
    return tmp_path, behaviour


def _state(tmp):
    p = tmp / "logs" / "pipeline_state.json"
    return json.loads(p.read_text()) if p.exists() else {}


def test_success_is_recorded_and_the_rerun_skips(sandbox):
    tmp, _ = sandbox
    assert pl.main(["--all"]) == 0
    assert set(_state(tmp)) == {"radar", "briefs"}
    assert pl.main(["--all"]) == 0
    log = sorted((tmp / "logs").glob("pipeline_*.log"))[-1].read_text(encoding="utf-8")
    assert log.count("skipped") == 2


def test_failed_step_is_not_recorded_and_reruns(sandbox):
    tmp, behaviour = sandbox
    assert pl.main(["--all"]) == 0  # both recorded
    behaviour["radar"] = 3
    assert pl.main(["--all", "--force"]) == 1  # radar fails, run stops
    assert "radar" not in _state(tmp)  # the old "done" entry was dropped, not kept
    behaviour["radar"] = 0
    assert pl.main(["--all"]) == 0  # inputs unchanged, but radar is redone
    log = sorted((tmp / "logs").glob("pipeline_*.log"))[-1].read_text(encoding="utf-8")
    assert "[radar] ok" in log and "radar" in _state(tmp)


def test_killed_step_is_not_recorded(sandbox, monkeypatch):
    tmp, _ = sandbox
    assert pl.main(["--all"]) == 0
    real = pl.run_cmd

    def killed(cmd, log):  # the process dies while the step runs (Ctrl+C, closed terminal)
        raise KeyboardInterrupt

    monkeypatch.setattr(pl, "run_cmd", killed)
    with pytest.raises(KeyboardInterrupt):
        pl.main(["--all", "--force"])
    assert "radar" not in _state(tmp)  # half-done step must not look done
    monkeypatch.setattr(pl, "run_cmd", real)
    assert pl.main(["--all"]) == 0
    log = sorted((tmp / "logs").glob("pipeline_*.log"))[-1].read_text(encoding="utf-8")
    assert "[radar] ok" in log  # redone without --force


def test_corrupt_state_file_means_rerun_everything(sandbox):
    tmp, _ = sandbox
    (tmp / "logs").mkdir(parents=True, exist_ok=True)
    (tmp / "logs" / "pipeline_state.json").write_text('{"radar": "abc"')  # truncated write
    assert pl.main(["--all"]) == 0
    assert set(_state(tmp)) == {"radar", "briefs"}


def test_download_failure_continues_with_exit_0_weather_failure_exits_1(tmp_path, monkeypatch):
    monkeypatch.setattr(pl, "LOGS", tmp_path / "logs")
    monkeypatch.setattr(pl, "STATE", tmp_path / "logs" / "pipeline_state.json")
    monkeypatch.setattr(pl, "STEPS", ["download", "weather"])
    monkeypatch.setattr(pl, "INPUTS", {})
    fail = [sys.executable, "-c", "import sys; sys.exit(1)"]
    ok = [sys.executable, "-c", "pass"]
    monkeypatch.setattr(pl, "commands", lambda w: {"download": [fail], "weather": [ok]})
    assert pl.main(["--all"]) == 0  # source site down: carry on, stale banner shows it
    monkeypatch.setattr(pl, "commands", lambda w: {"download": [ok], "weather": [fail]})
    assert pl.main(["--all"]) == 1  # incomplete weather is a real failure
