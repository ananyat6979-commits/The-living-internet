"""World snapshot: what the browser draws. Deterministic, and every visual element is backed by data.

* Position  = pure function of repo_id (stable across days and reloads). NO randomness.
* Brightness/pulse = that day's activity for the repo (log-scaled).
* Edges     = ONLY real relationships: two repos that shared >=2 distinct (non-bot) actors today.
              An edge without a `reason` is not emitted.
"""
from __future__ import annotations
import hashlib, math


def stable_xy(repo_id: int):
    h = hashlib.blake2b(str(repo_id).encode(), digest_size=8).digest()
    a = int.from_bytes(h[:4], "little") / 2**32 * math.tau
    r = math.sqrt(int.from_bytes(h[4:], "little") / 2**32)   # uniform over the disc
    return round(math.cos(a) * r, 4), round(math.sin(a) * r, 4)


def build_world(con, day: str, *, max_nodes=700, max_edges=160, include_ids=()):
    rows = con.execute(f"""
        SELECT repo_id, repo_name, events, actors, human_like_actors, forks, pull_requests, releases
        FROM ledger WHERE day = CAST('{day}' AS DATE) AND repo_name IS NOT NULL
        ORDER BY events DESC, repo_id LIMIT {max_nodes}""").fetchall()
    have = {r[0] for r in rows}
    for rid in include_ids:                      # the story's repo must always be on the map
        if rid not in have:
            extra = con.execute(f"""SELECT repo_id, repo_name, events, actors, human_like_actors, forks, pull_requests, releases
                                    FROM ledger WHERE day = CAST('{day}' AS DATE) AND repo_id = {int(rid)}""").fetchall()
            rows += extra
    ids = [r[0] for r in rows]
    nodes = []
    for rid, name, ev, act, hla, forks, prs, rel in rows:
        x, y = stable_xy(rid)
        nodes.append({"id": int(rid), "n": name, "x": x, "y": y, "e": int(ev), "a": int(act),
                      "f": int(forks), "p": int(prs), "r": int(rel)})
    edges = []
    if ids:
        idlist = ",".join(str(i) for i in ids)
        edges = con.execute(f"""
            WITH ap AS (
                SELECT repo_id, actor_id FROM events
                WHERE repo_id IN ({idlist}) AND NOT ({_bot()})
                GROUP BY 1, 2
            )
            SELECT a.repo_id, b.repo_id, count(*) AS shared
            FROM ap a JOIN ap b ON a.actor_id = b.actor_id AND a.repo_id < b.repo_id
            GROUP BY 1, 2 HAVING count(*) >= 2
            ORDER BY shared DESC, a.repo_id, b.repo_id LIMIT {max_edges}""").fetchall()
    return {"date": day, "nodes": nodes,
            "edges": [{"s": int(s), "t": int(t), "w": int(w), "reason": "shared_actor"} for s, t, w in edges],
            "encoding": {"position": "hash(repo_id): stable, carries no meaning",
                         "brightness": "events that day (log scale)",
                         "edge": "two repositories with ≥2 shared non-automated accounts that day"}}


def _bot():
    from .ledger import is_bot_expr
    return is_bot_expr()
