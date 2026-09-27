"""First contact with REAL GH Archive data, using ONE hourly file. Writes nothing to the site or the ledger.

    python -m pipeline.check                          # two days ago, 12:00 UTC
    python -m pipeline.check --date 2026-09-22 --hour 5

Prints what the pipeline actually sees so problems show up in minutes, not after a 14-day backfill:
file size, parse accounting, event types, whether repository-creation events exist, bot-like share,
busiest repositories, and how concentrated the busiest repositories are by owner."""
from __future__ import annotations
import argparse, json, sys, time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import ingest, ledger
from .config import EVENT_KINDS, ROOT, RAW
from .source import fetch_hour, url_for, path_for


def run(date: str, hour: int, *, fetch=fetch_hour) -> dict:
    t0 = time.time()
    p = fetch(date, hour, retries=2)
    if p is None:
        return {"ok": False, "url": url_for(date, hour), "reason": "could not download or the file failed the gzip integrity check"}
    size_mb = Path(p).stat().st_size / 1e6
    con = ingest.connect()
    acc = ingest.load_day(con, str(p), date)
    q = lambda sql: con.execute(sql).fetchall()
    bot = ledger.is_bot_expr()
    types = q("SELECT event_type, count(*) FROM events GROUP BY 1 ORDER BY 2 DESC")
    unknown = [t for t, _ in types if t not in EVENT_KINDS]
    creates = dict(q("SELECT coalesce(ref_type,'(none)'), count(*) FROM events WHERE event_type='CreateEvent' GROUP BY 1"))
    actions = {t: dict(q(f"SELECT coalesce(action,'(none)'), count(*) FROM events WHERE event_type='{t}' GROUP BY 1")) for t in ("PullRequestEvent", "IssuesEvent")}
    tot, repos, actors, bots = q(f"SELECT count(*), count(DISTINCT repo_id), count(DISTINCT actor_id), count(DISTINCT actor_id) FILTER (WHERE {bot}) FROM events")[0]
    top = q(f"""SELECT repo_name, count(*) e, count(DISTINCT actor_id) a,
                       round(100.0 * count(*) FILTER (WHERE {bot}) / count(*), 0) bot_pct
                FROM events GROUP BY repo_id, repo_name ORDER BY e DESC, repo_id LIMIT 10""")
    owners = q("""WITH t AS (SELECT repo_id, any_value(repo_name) n, count(*) e FROM events GROUP BY 1 ORDER BY e DESC, repo_id LIMIT 700)
                  SELECT split_part(n, '/', 1) o, count(*) c FROM t GROUP BY 1 ORDER BY c DESC, o LIMIT 10""")
    distinct_owners = q("""WITH t AS (SELECT repo_id, any_value(repo_name) n, count(*) e FROM events GROUP BY 1 ORDER BY e DESC, repo_id LIMIT 700)
                           SELECT count(DISTINCT split_part(n, '/', 1)), count(*) FROM t""")[0]
    return {
        "ok": True, "url": url_for(date, hour), "file": str(path_for(date, hour)), "size_mb": round(size_mb, 1),
        "seconds": round(time.time() - t0, 1), "accounting": acc,
        "reject_rate_pct": round(100 * acc["rejected"] / max(1, acc["lines_read"]), 4),
        "events": int(tot), "repos": int(repos), "actors": int(actors), "bot_like_actors": int(bots),
        "event_types": {t: int(n) for t, n in types}, "unknown_event_types": unknown,
        "create_events_by_ref_type": {k: int(v) for k, v in creates.items()},
        "repo_creation_events_present": creates.get("repository", 0) > 0,
        "actions": actions, "top_repos": [{"repo": r, "events": int(e), "accounts": int(a), "bot_pct": int(b)} for r, e, a, b in top],
        "owner_concentration_top700": {"distinct_owners": int(distinct_owners[0]), "repos": int(distinct_owners[1]),
                                       "biggest_owners": [{"owner": o, "repos": int(c)} for o, c in owners]},
    }


def render(r: dict) -> str:
    if not r["ok"]:
        return (f"FAILED: {r['reason']}\n  url: {r['url']}\n"
                "  Try opening the URL in a browser. If it downloads there, this is a network/proxy problem on this machine.\n"
                "  If it 404s, that hour is not published yet: use a date at least 2 days ago.")
    a = r["accounting"]
    L = [f"OK  {r['url']}", f"    {r['size_mb']} MB compressed, processed in {r['seconds']}s  -> a full day is roughly 24x this download",
         "", f"lines read {a['lines_read']:,} | accepted {a['accepted']:,} | rejected {a['rejected']:,} ({r['reject_rate_pct']}%) | other-day {a['off_day']:,}",
         f"events {r['events']:,} | repositories {r['repos']:,} | accounts {r['actors']:,} | bot-like accounts {r['bot_like_actors']:,}", "", "event types:"]
    L += [f"    {t:34s}{n:>10,}{'   <- not in our EVENT_KINDS' if t in r['unknown_event_types'] else ''}" for t, n in r["event_types"].items()]
    L += ["", f"CreateEvent by ref_type: {r['create_events_by_ref_type']}",
          f"repository-creation events present: {r['repo_creation_events_present']}"
          + ("" if r["repo_creation_events_present"] else "   (so stories will say 'first seen in our record', never 'created')"),
          f"PullRequestEvent actions: {r['actions']['PullRequestEvent']}", f"IssuesEvent actions: {r['actions']['IssuesEvent']}", "", "busiest repositories in this hour:"]
    L += [f"    {t['repo']:52s}{t['events']:>7,} events {t['accounts']:>5,} accounts  {t['bot_pct']:>3}% bot-like" for t in r["top_repos"]]
    o = r["owner_concentration_top700"]
    L += ["", f"of the busiest {o['repos']} repositories there are {o['distinct_owners']} distinct owners. Biggest owners:"]
    L += [f"    {x['owner']:30s}{x['repos']:>4} repos" for x in o["biggest_owners"]]
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    d = (datetime.now(timezone.utc) - timedelta(days=2)).date().isoformat()
    ap.add_argument("--date", default=d); ap.add_argument("--hour", type=int, default=12); ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")     # Windows consoles default to a legacy codepage
    print(f"checking {a.date} hour {a.hour:02d} UTC" + ("  (no --date given, so this defaults to 2 days ago; pass --date to check a specific day, e.g. the one you are about to `pipeline.run`)" if "--date" not in (argv or sys.argv[1:]) else ""))
    r = run(a.date, a.hour)
    print(json.dumps(r, indent=2) if a.json else render(r))
    out = ROOT / "work" / f"check-{a.date}-{a.hour:02d}.json"
    out.parent.mkdir(parents=True, exist_ok=True); out.write_text(json.dumps(r, indent=2), encoding="utf-8")
    print(f"\n(full result saved as JSON to {out})")
    return 0 if r["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
