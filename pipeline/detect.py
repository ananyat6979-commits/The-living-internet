"""Candidate generation. Pure SQL over the ledger; returns plain dict rows.

Every detector answers ONE question and returns the *measurements*, not prose.
Prose is produced later by the claim compiler, and only from these measurements.

Key correctness properties
--------------------------
* Silence is real: the baseline is computed over every calendar day in the window with
  missing repo-days counted as 0 (not skipped).
* A repo needs enough ledger COVERAGE before we judge it (warm-up guard). Without
  history we say so; we never invent a baseline.
* Percentile is computed against repo-days of comparable scale (same log10 event band),
  not against all repos. "Unusual for a repo like this", not "bigger than a tiny repo".
"""
from __future__ import annotations
import duckdb
from .config import METHOD as M


def cov_expr(day: str) -> str:
    """Number of distinct ledger days actually observed inside the baseline window.
    The baseline mean divides by THIS, never by a fixed window length: days we never
    observed are unknown, not zero. (Days we observed with no rows for a repo ARE zero.)"""
    return (f"(SELECT count(DISTINCT day) FROM ledger WHERE day < CAST('{day}' AS DATE) "
            f"AND day >= CAST('{day}' AS DATE) - {M.baseline_days})")


def baseline_divisor(con, day: str) -> int:
    return int(con.execute(f"SELECT {cov_expr(day)}").fetchone()[0])


def _base_cte(day: str) -> str:
    """window stats per repo over the baseline window BEFORE `day`, silence counted as zero."""
    return f"""
    WITH today AS (
        SELECT * FROM ledger WHERE day = CAST('{day}' AS DATE)
    ),
    win AS (
        SELECT repo_id,
               sum(events)                                  AS win_events,
               count(*)                                     AS active_days,
               max(events)                                  AS peak_events,
               max(day)                                     AS last_active_day
        FROM ledger
        WHERE day <  CAST('{day}' AS DATE)
          AND day >= CAST('{day}' AS DATE) - {M.baseline_days}
        GROUP BY repo_id
    )
    """


def growth(con, day: str) -> list[dict]:
    """Repo is far above its own 28-day norm (silent days = 0), and above its size-peers."""
    q = _base_cte(day) + f"""
    , scored AS (
        SELECT t.repo_id, t.repo_name, t.events, t.actors, t.human_like_actors, t.top_actor_share,
               t.pushes, t.pull_requests, t.issues, t.comments, t.forks, t.stars, t.releases,
               COALESCE(w.win_events, 0) * 1.0 / {cov_expr(day)}       AS baseline_mean,
               {cov_expr(day)}                                         AS baseline_days_used,
               COALESCE(w.active_days, 0)                                AS active_days,
               floor(log10(greatest(t.events,1)))                        AS band
        FROM today t LEFT JOIN win w USING (repo_id)
        WHERE t.events >= {M.min_events_today} AND t.actors >= {M.min_distinct_actors_today}
          AND {cov_expr(day)} >= {M.min_baseline_days_observed}
    ), peers AS (
        SELECT band, count(*) AS n, quantile_cont(events, {M.min_percentile}) AS p_cut
        FROM scored GROUP BY band
    )
    SELECT s.*, p.n AS peer_n, p.p_cut,
           s.events / greatest(s.baseline_mean, 0.5)                    AS fold,
           s.events - s.baseline_mean                                   AS excess,
           (SELECT count(*) FROM scored x WHERE x.band = s.band AND x.events <= s.events) * 1.0
               / p.n                                                    AS peer_percentile
    FROM scored s JOIN peers p USING (band)
    WHERE s.active_days >= 3
      AND s.events / greatest(s.baseline_mean, 0.5) >= {M.min_fold}
      AND s.events - s.baseline_mean >= {M.min_absolute_excess}
    ORDER BY excess DESC, s.repo_id LIMIT 60
    """
    return _rows(con, q)


def resurrection(con, day: str) -> list[dict]:
    """Active in the past, observed-silent for a long gap, active again today."""
    q = f"""
    WITH today AS (SELECT * FROM ledger WHERE day = CAST('{day}' AS DATE)),
    hist AS (
        SELECT repo_id,
               max(day) FILTER (WHERE day < CAST('{day}' AS DATE))              AS last_prior_day,
               count(*) FILTER (WHERE day < CAST('{day}' AS DATE))              AS prior_active_days,
               max(events) FILTER (WHERE day < CAST('{day}' AS DATE))           AS prior_peak,
               sum(events) FILTER (WHERE day < CAST('{day}' AS DATE))           AS prior_events,
               min(day)                                                         AS first_seen_day
        FROM ledger GROUP BY repo_id
    )
    SELECT t.repo_id, t.repo_name, t.events, t.actors, t.human_like_actors, t.top_actor_share,
           t.pushes, t.pull_requests, t.issues, t.comments, t.forks, t.stars, t.releases,
           h.last_prior_day, h.prior_active_days, h.prior_peak, h.prior_events, h.first_seen_day,
           date_diff('day', h.last_prior_day, CAST('{day}' AS DATE)) - 1 AS silent_days
    FROM today t JOIN hist h USING (repo_id)
    WHERE h.last_prior_day IS NOT NULL
      AND date_diff('day', h.last_prior_day, CAST('{day}' AS DATE)) - 1 >= {M.resurrection_min_silent_days}
      AND h.prior_active_days >= {M.resurrection_min_prior_active_days}
      AND t.events >= {M.resurrection_min_events_today}
    ORDER BY silent_days DESC, t.events DESC, t.repo_id LIMIT 40
    """
    return _rows(con, q)


def graveyard(con, day: str) -> list[dict]:
    """Once meaningfully active, now observed-silent for a long time. (Shown in the Graveyard, never the daily story.)"""
    q = f"""
    WITH hist AS (
        SELECT repo_id, arg_max(repo_name, day) FILTER (WHERE repo_name IS NOT NULL) AS repo_name,   -- latest known name
               max(day) AS last_day, min(day) AS first_day,
               count(*) AS active_days, max(events) AS peak_events, sum(events) AS total_events,
               arg_max(day, events * 1000000 - CAST(epoch(day) / 86400 AS BIGINT)) AS peak_day,   -- ties: EARLIEST day, never arbitrary
               max(actors) AS peak_actors
        FROM ledger WHERE day <= CAST('{day}' AS DATE) GROUP BY repo_id
    )
    SELECT *, date_diff('day', last_day, CAST('{day}' AS DATE)) AS silent_days
    FROM hist
    WHERE peak_events >= {M.graveyard_min_peak_events}
      AND date_diff('day', last_day, CAST('{day}' AS DATE)) >= {M.graveyard_min_silent_days}
      AND active_days >= 5
    ORDER BY total_events DESC, repo_id LIMIT 40
    """
    return _rows(con, q)


def fork_burst(con, day: str) -> list[dict]:
    q = _base_cte(day) + f"""
    , base AS (
        SELECT repo_id, sum(forks) * 1.0 / {cov_expr(day)} AS fork_mean
        FROM ledger WHERE day < CAST('{day}' AS DATE) AND day >= CAST('{day}' AS DATE) - {M.baseline_days}
        GROUP BY repo_id
    )
    SELECT t.repo_id, t.repo_name, t.events, t.actors, t.forks, t.top_actor_share, t.human_like_actors,
           COALESCE(b.fork_mean, 0) AS fork_mean,
           t.forks / greatest(COALESCE(b.fork_mean, 0), 0.5) AS fold
    FROM today t LEFT JOIN base b USING (repo_id)
    WHERE {cov_expr(day)} >= {M.min_baseline_days_observed}
      AND t.forks >= {M.fork_min_forks}
      AND t.forks / greatest(COALESCE(b.fork_mean, 0), 0.5) >= {M.fork_min_fold}
    ORDER BY t.forks DESC, t.repo_id LIMIT 30
    """
    return _rows(con, q)


def newcomers(con, day: str) -> list[dict]:
    """Repos whose FIRST-ever ledger appearance is today AND show real activity.

    We deliberately do NOT call these "births" unless the repo-creation event is
    actually present (repo_creates>0). See `birth_signal_health` for why."""
    q = f"""
    WITH first_seen AS (SELECT repo_id, min(day) AS first_day FROM ledger GROUP BY repo_id)
    SELECT t.repo_id, t.repo_name, t.events, t.actors, t.human_like_actors, t.top_actor_share,
           t.pushes, t.pull_requests, t.issues, t.comments, t.forks, t.stars, t.repo_creates,
           (SELECT count(DISTINCT day) FROM ledger) AS ledger_days
    FROM ledger t JOIN first_seen f USING (repo_id)
    WHERE t.day = CAST('{day}' AS DATE) AND f.first_day = t.day
      AND t.events >= {M.min_events_today} AND t.actors >= {M.min_distinct_actors_today}
    ORDER BY t.events DESC, t.repo_id LIMIT 40
    """
    return _rows(con, q)


def birth_signal_health(con, day: str) -> dict:
    """MEASURE whether repository-creation events are present in the data.

    A third-party source claims GitHub stopped emitting them after 2025-10-07; GitHub's own
    changelog does not say so. Rather than assume either, we measure it every day and the
    story engine adapts. This number is published in status.json."""
    r = con.execute(f"SELECT coalesce(sum(repo_creates),0), coalesce(sum(branch_creates),0), count(*) FROM ledger WHERE day = CAST('{day}' AS DATE)").fetchone()
    return {"repo_create_events": int(r[0]), "branch_create_events": int(r[1]), "repos_active": int(r[2]),
            "birth_signal_present": bool(r[0] > 0)}


def _rows(con, q):
    cur = con.execute(q)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]
