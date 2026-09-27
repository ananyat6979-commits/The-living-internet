"""Daily orchestrator.

    python -m pipeline.run                # yesterday UTC (+ backfills up to 2 previous unprocessed days)
    python -m pipeline.run --date 2026-09-22
    python -m pipeline.run --demo         # synthetic, clearly-labelled, offline

Exit codes: 0 published, 3 held (incomplete/invalid; previous state untouched), 1 error.
"""
from __future__ import annotations
import argparse, json, os, sys
from datetime import date as _date, datetime, timedelta, timezone
from pathlib import Path

from . import ingest, ledger, detect, stories, publish, store, world as worldmod
from .config import OUT, METHOD as M
from .source import acquire_day, IncompleteDay


def _read(p: Path, default):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def _history(con, day, n=120):
    rows = con.execute(f"""
        SELECT day::VARCHAR, sum(events), count(*), sum(forks), sum(pull_requests), sum(issues), sum(stars)
        FROM ledger WHERE day <= CAST('{day}' AS DATE) GROUP BY day ORDER BY day DESC LIMIT {n}""").fetchall()
    return [{"date": d, "events": int(e), "repos": int(r), "forks": int(f), "prs": int(p), "issues": int(i), "stars": int(s)}
            for d, e, r, f, p, i, s in reversed(rows)]


def repo_series(con, repo_id: int, day: str, n: int = 120) -> list[dict]:
    """Daily events for one repo over the last n days. Days before our ledger began are null
    (UNKNOWN to us), never zero: absence of our observation is not absence of activity."""
    first = con.execute("SELECT min(day) FROM ledger").fetchone()[0]
    got = dict(con.execute(
        "SELECT day, events FROM ledger WHERE repo_id = ? AND day <= CAST(? AS DATE) AND day > CAST(? AS DATE) - ?::INTEGER",
        [repo_id, day, day, n]).fetchall())
    d0 = _date.fromisoformat(day) - timedelta(days=n - 1)
    out = []
    for i in range(n):
        d = d0 + timedelta(days=i)
        out.append({"d": d.isoformat(), "e": None if d < first else int(got.get(d, 0))})
    return out


def evidence_sample(con, repo_id: int, day: str, source, limit: int = 40) -> dict:
    """The receipts: real GitHub event ids for the story's repo, with the exact archive file (and its
    sha256) each one lives in. No account names are published. Anyone can download the file and find the id."""
    total = con.execute("SELECT count(*) FROM events WHERE repo_id = ?", [repo_id]).fetchone()[0]
    rows = con.execute(
        "SELECT event_id, strftime(ts, '%Y-%m-%dT%H:%M:%SZ'), event_type, action, hour FROM events WHERE repo_id = ? ORDER BY ts, event_id LIMIT ?",
        [repo_id, limit]).fetchall()
    sha = {f.hour: f.sha256 for f in source.files}
    return {"repo_id": int(repo_id), "day": day, "total": int(total), "shown": len(rows),
            "events": [{"id": i, "t": t, "type": ty, "action": a, "file": f"{day}-{h}.json.gz", "sha256": sha.get(int(h))}
                       for i, t, ty, a, h in rows]}


def process_day(day: str, source, *, out: Path = OUT, con=None):
    con = con or ingest.connect()
    acct = ingest.load_day(con, source.glob(), day)
    if acct["accepted"] == 0:
        raise publish.ValidationError("zero accepted events")
    ledger.build_repo_day(con, day)
    n_days = ledger.attach(con)

    totals = con.execute("SELECT count(*), count(DISTINCT actor_id), count(DISTINCT repo_id) FROM events").fetchone()
    day_totals = {"events": int(totals[0]), "actors": int(totals[1]), "repos": int(totals[2])}
    hourly = [{"h": int(h), "e": int(e), "a": int(a), "r": int(r)} for h, e, a, r in con.execute(
        "SELECT hour, count(*), count(DISTINCT actor_id), count(DISTINCT repo_id) FROM events GROUP BY 1 ORDER BY 1").fetchall()]

    det = {"resurrection": detect.resurrection(con, day), "growth": detect.growth(con, day),
           "fork": detect.fork_burst(con, day), "newcomer": detect.newcomers(con, day)}
    health = detect.birth_signal_health(con, day)
    prior = _read(out / "stories" / "index.json", {"stories": []})["stories"]
    recent = [s["archetype"] for s in prior if s["date"] < day][:7]
    cands, chosen, held = stories.make_stories(day, det, health, recent, n_days)

    gy = [{"repo_id": int(r["repo_id"]), "repo": r["repo_name"], "silent_days": int(r["silent_days"]),
           "peak_events": int(r["peak_events"]), "peak_day": str(r["peak_day"]), "first_day": str(r["first_day"]),
           "last_day": str(r["last_day"]), "active_days": int(r["active_days"]), "total_events": int(r["total_events"])}
          for r in detect.graveyard(con, day)]
    wld = worldmod.build_world(con, day, include_ids=[chosen["repo_id"]] if chosen else [])
    extras = None
    if chosen:
        extras = {"series": repo_series(con, chosen["repo_id"], day), "evidence": evidence_sample(con, chosen["repo_id"], day, source)}
    arts = publish.build_artifacts(day=day, source=source, accounting=acct, day_totals=day_totals, hourly=hourly,
                                   top_repos=[], chosen=chosen, candidates=cands, held_reason=held, birth_health=health,
                                   ledger_days=n_days, graveyard_rows=gy, history_rows=_history(con, day),
                                   prior_stories=prior, world=wld, extras=extras)
    publish.promote(arts, out)
    return {"status": "published", "date": day, "events": day_totals["events"], "story": chosen["id"] if chosen else None, "held": held}


def _cleanup(day: str):
    from .source import RAW
    for f in RAW.glob(f"{day}-*.json.gz"):
        f.unlink(missing_ok=True)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--date"); ap.add_argument("--backfill", type=int, default=2)
    a = ap.parse_args(argv)
    use_store = os.environ.get("LI_STORE") == "1"
    if use_store:
        print(json.dumps({"store": "pulled", "days": store.pull_missing()}))
    target = a.date or (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()
    done = set(ledger.ledger_days())
    todo = [target] if a.date else [(datetime.fromisoformat(target) - timedelta(days=i)).date().isoformat() for i in reversed(range(a.backfill + 1))]
    todo = [d for d in todo if d not in done or d == target]
    rc = 0
    for d in todo:
        try:
            res = process_day(d, acquire_day(d))
            if use_store:
                store.push(d)                     # fatal on failure: a ledger day only on a disposable runner is a hole in memory
            print(json.dumps(res))
        except IncompleteDay as e:
            print(json.dumps({"status": "held", "date": d, "reason": str(e)})); rc = 3
        except publish.ValidationError as e:
            print(json.dumps({"status": "held", "date": d, "reason": f"validation: {e}"})); rc = 3
        finally:
            _cleanup(d)
    return rc


if __name__ == "__main__":
    sys.exit(main())
