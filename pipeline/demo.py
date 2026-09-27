"""Offline demo: runs the REAL pipeline on clearly-labelled SYNTHETIC input.

Purpose: let anyone `npm run dev` the site without network access, and let the front-end be
developed against genuine pipeline output. Everything it publishes is stamped synthetic=true and
the UI shows a persistent 'SYNTHETIC DEMO DATA' banner. It is never run in CI's production job.
"""
from __future__ import annotations
import json, shutil, sys, tempfile
from datetime import date, timedelta
from pathlib import Path

from . import config, ingest, ledger, source, run, synth

TARGET = date(2026, 9, 22)
START = date(2026, 6, 1)


def spec_for(day: str) -> dict:
    d, T = date.fromisoformat(day), TARGET.isoformat()
    s = {"steady/lib": {"id": 11, "events": 30, "actors": 4, "types": {"PushEvent": 5, "IssuesEvent": 2, "WatchEvent": 3}},
         "hum/notes": {"id": 12, "events": 14, "actors": 3, "types": {"PushEvent": 4, "IssueCommentEvent": 3}}}
    if d < START + timedelta(20):
        s["ghost/oldtool"] = {"id": 22, "events": 60, "actors": 4, "types": {"PushEvent": 5, "IssuesEvent": 1, "IssueCommentEvent": 2}}
    if day == T:
        s["ghost/oldtool"] = {"id": 22, "events": 96, "actors": 6, "types": {"PushEvent": 5, "PullRequestEvent": 2, "IssueCommentEvent": 2}}
        s["botmix/y"] = {"id": 66, "events": 300, "actors": 3, "types": {"PushEvent": 1}, "logins": ["dependabot[bot]"] * 3}
        # Two shared contributors so the World shows a real edge (>=2 shared non-bot actors that day):
        # this is what makes a "cluster" visible at all. Without it, every synthetic repo has its own
        # actor namespace and the map is correct but empty, which is what shipped before this fix.
        shared = ["maya-k", "devrim"]
        s["ghost/oldtool"] = {**s["ghost/oldtool"], "actors": 6, "logins": shared + [None] * 4}
        s["orbit/kit"] = {"id": 99, "events": 40, "actors": 5, "types": {"PushEvent": 5, "IssueCommentEvent": 2}, "logins": shared + [None] * 3}
    s["pulse/tool"] = {"id": 77, "events": 90 if day == (TARGET - timedelta(days=1)).isoformat() else 8, "actors": 7 if day == (TARGET - timedelta(days=1)).isoformat() else 2,
                       "types": {"PushEvent": 4, "IssueCommentEvent": 2, "IssuesEvent": 1}}
    if day == (TARGET - timedelta(days=2)).isoformat():
        s["forky/lib"] = {"id": 88, "events": 70, "actors": 30, "types": {"ForkEvent": 6, "WatchEvent": 2, "PushEvent": 1}}
    s["spike/proj"] = {"id": 33, "events": 160 if day == T else 10, "actors": 9 if day == T else 2,
                       "types": {"PushEvent": 4, "ForkEvent": 1, "IssuesEvent": 1}}
    if d < START + timedelta(8):
        s["dead/proj"] = {"id": 44, "events": 80, "actors": 5, "types": {"PushEvent": 5}}
    if d < START + timedelta(35):
        s["quiet/atlas"] = {"id": 45, "events": 55, "actors": 4, "types": {"PushEvent": 5, "IssuesEvent": 1}}
    return s


def build(out: Path):
    tmp = Path(tempfile.mkdtemp())
    st, raw = tmp / "state", tmp / "raw"
    config.STATE = st; ledger.STATE = st; ledger.LEDGER_DIR = st / "ledger"; source.RAW = raw
    con = ingest.connect()
    d = START
    while d < TARGET - timedelta(days=3):
        day = d.isoformat()
        synth.write_day(raw, day, spec_for(day), background_repos=120)
        ingest.load_day(con, str(raw / f"{day}-*.json.gz"), day)
        ledger.build_repo_day(con, day)
        for f in raw.glob(f"{day}-*.json.gz"): f.unlink()
        d += timedelta(days=1)
    res = None
    for back in (3, 2, 1, 0):                                   # publish the last 4 days for real, oldest first
        day = (TARGET - timedelta(days=back)).isoformat()
        synth.write_day(raw, day, spec_for(day), background_repos=120)
        src = source.acquire_day(day, fetch=lambda dd, h: source.path_for(dd, h))
        res = run.process_day(day, src, out=out)
    # stamp everything synthetic
    for name in ("latest.json", "status.json"):
        p = out / name; j = json.loads(p.read_text()); j["synthetic"] = True; p.write_text(json.dumps(j, separators=(",", ":"), sort_keys=True))
    shutil.rmtree(tmp, ignore_errors=True)
    return res


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else config.OUT
    print(json.dumps(build(out)))
