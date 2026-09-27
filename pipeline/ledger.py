"""The Ledger: one row per (repo_id, day) for EVERY repo that had any public event.

Why this exists
---------------
In GH Archive, "silence" is the absence of rows. A top-N history (what a naive
implementation keeps) can never represent silence, so resurrection/graveyard stories
are structurally undetectable. The ledger keeps every repo-day so that
"N days since last observed event" is a query, not a guess.

Storage: Parquet, partitioned by day, cached between CI runs (actions/cache) and
published as a release asset. It is NEVER committed to the website branch.
"""
from __future__ import annotations
from pathlib import Path
import duckdb

from .config import STATE, METHOD

LEDGER_DIR = STATE / "ledger"
NAME_MIN_EVENTS = 5


def ledger_path(day: str) -> Path:
    return LEDGER_DIR / f"day={day}" / "repo_day.parquet"


def is_bot_expr() -> str:
    conds = " OR ".join(f"lower(actor_login) LIKE '%{s.lower()}'" for s in METHOD.bot_login_suffixes)
    return f"({conds})"


def build_repo_day(con: duckdb.DuckDBPyConnection, day: str) -> int:
    """Aggregate today's `events` into the ledger row set and write it. Idempotent (overwrites the day)."""
    bot = is_bot_expr()
    con.execute(f"""
        CREATE OR REPLACE TABLE repo_day AS
        WITH per_actor AS (
            SELECT repo_id, actor_id, count(*) AS n
            FROM events GROUP BY 1, 2
        ), top_actor AS (
            SELECT repo_id, max(n) AS top_n FROM per_actor GROUP BY 1
        )
        SELECT
            e.repo_id,
            -- Size policy: a name is stored only on days it could matter (>=5 events). Names dominate
            -- Parquet size (~75% in measurement); tiny repo-days never surface in a story or the map.
            CASE WHEN count(*) >= {NAME_MIN_EVENTS} THEN arg_max(e.repo_name, CAST(e.ts AS VARCHAR) || e.event_id) END AS repo_name,
            CAST('{day}' AS DATE)                                      AS day,
            count(*)                                                   AS events,
            count(DISTINCT e.actor_id)                                 AS actors,
            count(DISTINCT e.actor_id) FILTER (WHERE NOT {bot})        AS human_like_actors,
            count(*) FILTER (WHERE {bot})                              AS bot_events,
            count(*) FILTER (WHERE event_type='PushEvent')             AS pushes,
            count(*) FILTER (WHERE event_type='PullRequestEvent')      AS pull_requests,
            count(*) FILTER (WHERE event_type='IssuesEvent')           AS issues,
            count(*) FILTER (WHERE event_type IN ('IssueCommentEvent','CommitCommentEvent',
                                                  'PullRequestReviewCommentEvent'))   AS comments,
            count(*) FILTER (WHERE event_type='PullRequestReviewEvent')AS reviews,
            count(*) FILTER (WHERE event_type='ForkEvent')             AS forks,
            count(*) FILTER (WHERE event_type='WatchEvent')            AS stars,
            count(*) FILTER (WHERE event_type='ReleaseEvent')          AS releases,
            count(*) FILTER (WHERE event_type='CreateEvent' AND ref_type='repository') AS repo_creates,
            count(*) FILTER (WHERE event_type='CreateEvent' AND ref_type='branch')     AS branch_creates,
            count(*) FILTER (WHERE event_type='CreateEvent' AND ref_type='tag')        AS tag_creates,
            CAST(max(t.top_n) AS DOUBLE) / count(*)                    AS top_actor_share,
            min(ts)                                                    AS first_ts,
            max(ts)                                                    AS last_ts
        FROM events e
        JOIN top_actor t USING (repo_id)
        GROUP BY e.repo_id
    """)
    p = ledger_path(day)
    p.parent.mkdir(parents=True, exist_ok=True)
    con.execute(f"COPY repo_day TO '{p}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    return con.execute("SELECT count(*) FROM repo_day").fetchone()[0]


def ledger_days() -> list[str]:
    if not LEDGER_DIR.exists():
        return []
    return sorted(p.name.split("=", 1)[1] for p in LEDGER_DIR.glob("day=*") if (p / "repo_day.parquet").exists())


def attach(con: duckdb.DuckDBPyConnection) -> int:
    """Expose every ledger day (including today's) as the `ledger` view. Returns #days."""
    days = ledger_days()
    if not days:
        con.execute("CREATE OR REPLACE VIEW ledger AS SELECT * FROM repo_day WHERE false")
        return 0
    glob = str(LEDGER_DIR / "day=*" / "repo_day.parquet")
    con.execute(f"CREATE OR REPLACE VIEW ledger AS SELECT * FROM read_parquet('{glob}', union_by_name=true)")
    return len(days)


def coverage_days(con, upto: str, window: int) -> int:
    """How many distinct ledger days exist in the `window` days before `upto`."""
    return con.execute(
        "SELECT count(DISTINCT day) FROM ledger WHERE day < CAST(? AS DATE) AND day >= CAST(? AS DATE) - ?::INTEGER",
        [upto, upto, window]).fetchone()[0]
