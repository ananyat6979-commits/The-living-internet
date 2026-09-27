import sys, shutil
from datetime import date, timedelta
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline import config, ledger, ingest, synth, source, run  # noqa: E402

TARGET = date(2026, 9, 22)
START = date(2026, 6, 1)


def spec_for(day: str) -> dict:
    d, T = date.fromisoformat(day), TARGET.isoformat()
    s = {"steady/lib": {"id": 11, "events": 30, "actors": 4, "types": {"PushEvent": 5, "IssuesEvent": 2}}}
    if d < START + timedelta(20):
        s["ghost/oldtool"] = {"id": 22, "events": 60, "actors": 4, "types": {"PushEvent": 5, "IssuesEvent": 1}}
    if day == T:
        s["ghost/oldtool"] = {"id": 22, "events": 90, "actors": 5, "types": {"PushEvent": 5, "PullRequestEvent": 2}}
        # one dominant automation account among a few humans: passes the actor floor, must be flagged automation-shaped
        s["botfarm/x"] = {"id": 55, "events": 400, "actors": 1, "types": {"PushEvent": 1}, "logins": ["renovate[bot]"]}
        # 3 distinct bot accounts (not the same login 3x): after the synth.py fix, an identical login
        # now correctly collapses to one shared actor_id, so this must use 3 different bot logins to
        # keep testing "actors=3, all of them bot-shaped" rather than accidentally testing actors=1.
        s["botmix/y"] = {"id": 66, "events": 300, "actors": 3, "types": {"PushEvent": 1},
                          "logins": ["dependabot[bot]", "renovate[bot]", "snyk-bot"]}
    s["spike/proj"] = {"id": 33, "events": 160 if day == T else 10, "actors": 9 if day == T else 2,
                       "types": {"PushEvent": 4, "ForkEvent": 1, "IssuesEvent": 1}}
    if d < START + timedelta(8):
        s["dead/proj"] = {"id": 44, "events": 80, "actors": 5, "types": {"PushEvent": 5}}
    return s


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """Isolated STATE/RAW/OUT so tests never touch real state."""
    st, raw, out = tmp_path / "state", tmp_path / "raw", tmp_path / "out"
    monkeypatch.setattr(config, "STATE", st)
    monkeypatch.setattr(ledger, "STATE", st); monkeypatch.setattr(ledger, "LEDGER_DIR", st / "ledger")
    monkeypatch.setattr(source, "RAW", raw)
    monkeypatch.setattr(run, "OUT", out)
    return {"state": st, "raw": raw, "out": out, "tmp": tmp_path}


def fake_source(env, day, **kw):
    """Materialise a synthetic day into RAW and return a SourceDay (as if downloaded)."""
    synth.write_day(env["raw"], day, spec_for(day), background_repos=40, **kw)
    return source.acquire_day(day, fetch=lambda d, h: source.path_for(d, h) if source.path_for(d, h).exists() else None)


def backfill(env, upto=TARGET, start=START):
    """Build the ledger for every day up to (not including) `upto`, fast, without publishing."""
    con = ingest.connect()
    d = start
    while d < upto:
        day = d.isoformat()
        synth.write_day(env["raw"], day, spec_for(day), background_repos=40)
        ingest.load_day(con, str(env["raw"] / f"{day}-*.json.gz"), day)
        ledger.build_repo_day(con, day)
        for f in env["raw"].glob(f"{day}-*.json.gz"): f.unlink()
        d += timedelta(days=1)
