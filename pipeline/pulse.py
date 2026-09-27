"""The Pulse: the fast clock.

Every run (every ~4h) we read the latest COMPLETE hourly archives (GH Archive publishes with a lag,
so 'latest complete' = a few hours old, honestly labelled). We publish:
  * events per hour for the last 24h (the heartbeat the front-end animates)
  * which repos were loudest in that window relative to their own ledger baseline
No second data source; the same GH Archive files, so numbers reconcile with the daily story.
"""
from __future__ import annotations
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import ingest, ledger
from .config import METHOD
from .config import OUT, RAW
from .source import fetch_hour, path_for


def latest_complete_hours(now: datetime, n: int = 6, lag_hours: int = 2):
    """GH Archive files for the current hour are incomplete until the hour closes and is published.
    We ignore the last `lag_hours` hours; anything still unavailable is reported, not faked."""
    anchor = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=lag_hours)
    return [anchor - timedelta(hours=i) for i in reversed(range(n))]


def build_pulse(now: datetime | None = None, n: int = 6, *, fetch=fetch_hour, out: Path = OUT) -> dict:
    now = now or datetime.now(timezone.utc)
    slots = latest_complete_hours(now, n)
    got, missing = [], []
    for dt in slots:
        d, h = dt.date().isoformat(), dt.hour
        p = fetch(d, h)
        (got if p else missing).append((d, h, p))
    result = {"generated_at": now.isoformat(timespec="seconds"), "requested_hours": n,
              "available_hours": len(got), "missing": [f"{d} {h:02d}:00Z" for d, h, _ in missing],
              "status": "current" if not missing else ("partial" if got else "unavailable"),
              "hours": [], "loudest": [], "window": None}
    if not got:
        return result
    con = ingest.connect()
    files = ",".join(f"'{p}'" for _, _, p in got)
    con.execute(f"""CREATE TABLE ev AS SELECT CAST(created_at AS TIMESTAMP) ts, actor.id actor_id, actor.login actor_login, repo.id repo_id, repo.name repo_name, type
        FROM read_ndjson([{files}], columns={{'created_at':'VARCHAR','type':'VARCHAR','actor':'STRUCT(id BIGINT, login VARCHAR)','repo':'STRUCT(id BIGINT, name VARCHAR)'}},
        ignore_errors=true, compression='gzip') WHERE repo.id IS NOT NULL""")
    result["hours"] = [{"t": t.isoformat(timespec="minutes"), "e": int(e), "a": int(a)} for t, e, a in con.execute(
        "SELECT date_trunc('hour', ts), count(*), count(DISTINCT actor_id) FROM ev GROUP BY 1 ORDER BY 1").fetchall()]
    result["window"] = {"from": result["hours"][0]["t"], "to": result["hours"][-1]["t"],
                        "events": int(sum(h["e"] for h in result["hours"]))}
    ledger.attach(con)
    BOT = ledger.is_bot_expr()
    # Loudest in-window repos, judged against their own ledger mean (silence = 0), floor to avoid noise.
    rows = con.execute(f"""
        WITH pa AS (SELECT repo_id, actor_id, count(*) c FROM ev GROUP BY 1,2),
        ta AS (SELECT repo_id, max(c) top_c FROM pa GROUP BY 1),
        w AS (SELECT ev.repo_id, arg_max(repo_name, CAST(ts AS VARCHAR)) n, count(*) e, count(DISTINCT actor_id) a,
                     count(DISTINCT actor_id) FILTER (WHERE NOT ({BOT})) human_a,
                     any_value(ta.top_c) * 1.0 / count(*) AS top_share
              FROM ev JOIN ta USING (repo_id) GROUP BY 1
              HAVING count(*) >= 15 AND count(DISTINCT actor_id) >= 2
                 AND any_value(ta.top_c) * 1.0 / count(*) < {METHOD.max_top_actor_share}
                 AND count(DISTINCT actor_id) FILTER (WHERE NOT ({BOT})) >= 1),
        b AS (SELECT repo_id, sum(events) * 1.0 / (SELECT greatest(1, count(DISTINCT day)) FROM ledger WHERE day >= CAST('{slots[0].date().isoformat()}' AS DATE) - 28 AND day < CAST('{slots[0].date().isoformat()}' AS DATE)) AS mean_day FROM ledger
              WHERE day >= CAST('{slots[0].date().isoformat()}' AS DATE) - 28 AND day < CAST('{slots[0].date().isoformat()}' AS DATE) GROUP BY 1)
        SELECT w.n, w.e, w.a, coalesce(b.mean_day,0) FROM w LEFT JOIN b USING (repo_id)
        ORDER BY (w.e / greatest(coalesce(b.mean_day,0) * {len(got)}/24.0, 1.0)) DESC, w.repo_id LIMIT 8""").fetchall()
    result["loudest"] = [{"repo": n, "events": int(e), "actors": int(a), "usual_per_day": round(float(m), 1)} for n, e, a, m in rows]
    for _, _, p in got:
        Path(p).unlink(missing_ok=True)          # runners have finite disk; the archive is re-fetchable
    return result


def write_pulse(pulse: dict, out: Path = OUT):
    out.mkdir(parents=True, exist_ok=True)
    (out / "pulse.json").write_text(json.dumps(pulse, ensure_ascii=False, separators=(",", ":"), sort_keys=True), encoding="utf-8")


if __name__ == "__main__":
    p = build_pulse()
    write_pulse(p)
    print(json.dumps({k: p[k] for k in ("status", "available_hours", "requested_hours", "missing")}))
