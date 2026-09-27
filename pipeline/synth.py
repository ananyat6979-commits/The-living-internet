"""Deterministic synthetic GH-Archive-shaped data, for tests ONLY.

This module is imported by tests and by the `demo` command. It is never imported by
the production path, and everything it emits is stamped source='SYNTHETIC' so the UI
can refuse to present it as real."""
from __future__ import annotations
import gzip, hashlib, io, json, random
from datetime import date, timedelta
from pathlib import Path


def _h(*parts) -> int:
    """Process-independent hash (Python's hash() is salted per process)."""
    return int.from_bytes(hashlib.blake2b("|".join(map(str, parts)).encode(), digest_size=6).digest(), "little")


def _ev(i, typ, ts, actor, repo, **payload):
    return {"id": str(i), "type": typ, "created_at": ts,
            "actor": {"id": actor[0], "login": actor[1]},
            "repo": {"id": repo[0], "name": repo[1]}, "payload": payload}


def write_day(out_dir: Path, day: str, spec: dict, *, seed=0, corrupt_lines=0, drop_hours=(), background_repos=300):
    """spec: {repo_name: {'id':int,'events':int,'actors':int,'types':{type:weight}, 'action':..}}"""
    rng = random.Random(f"{seed}-{day}")
    out_dir.mkdir(parents=True, exist_ok=True)
    per_hour = {h: [] for h in range(24)}
    n = int(day.replace("-", "")) * 1000
    bg = {f"bg/repo{i}": {"id": 900000 + i, "events": rng.randint(1, 6), "actors": rng.randint(1, 3),
                          "types": {"PushEvent": 5, "IssuesEvent": 1, "WatchEvent": 2}} for i in range(background_repos)}
    for name, s in {**bg, **spec}.items():
        types, weights = zip(*s["types"].items())
        for k in range(s["events"]):
            n += 1
            actor_i = k % max(1, s["actors"])
            login = s.get("logins", [None] * 99)[actor_i]
            # An explicit login is a real identity: its id must be a function of the LOGIN alone so the
            # same person reused across repos (for shared-actor edges) gets the same actor_id. An
            # unnamed slot keeps the old per-repo id so unrelated repos never accidentally collide.
            actor = ((5_000_000 + _h(login) % 1_000_000) if login else (5_000_000 + _h(name, actor_i) % 1_000_000),
                     login or f"user{_h(name, actor_i) % 100000}")
            h = rng.randrange(24)
            ts = f"{day}T{h:02d}:{rng.randrange(60):02d}:{rng.randrange(60):02d}Z"
            t = rng.choices(types, weights)[0]
            pl = {}
            if t == "CreateEvent": pl = {"ref_type": s.get("ref_type", "repository")}
            if t == "PullRequestEvent": pl = {"action": "opened"}
            if t == "IssuesEvent": pl = {"action": "opened"}
            per_hour[h].append(_ev(n, t, ts, actor, (s["id"], name), **pl))
    for h in range(24):
        if h in drop_hours: continue
        p = out_dir / f"{day}-{h:02d}.json.gz"
        # mtime=0: reproducible bytes. (A gzip header otherwise embeds the wall clock, so "the same" fixture
        # would hash differently from one second to the next.)
        with open(p, "wb") as raw_fh, gzip.GzipFile(fileobj=raw_fh, mode="wb", mtime=0) as gz, io.TextIOWrapper(gz, encoding="utf-8") as fh:
            evs = per_hour[h]
            for e in evs: fh.write(json.dumps(e) + "\n")
            for _ in range(corrupt_lines if h == 3 else 0):
                fh.write('{"id": "BROKEN", "type": \n')
    return out_dir
