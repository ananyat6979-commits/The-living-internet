import json, pytest
from conftest import TARGET, fake_source, backfill
from pipeline import run, publish, source, ingest, ledger

T = TARGET.isoformat()


def test_end_to_end_publishes_a_real_story(env):
    backfill(env)
    src = fake_source(env, T)
    res = run.process_day(T, src, out=env["out"])
    assert res["status"] == "published" and res["story"]
    story = json.loads((env["out"] / "stories" / f"{T}.json").read_text())
    assert story["archetype"] in ("resurrection", "growth")
    assert story["repo"] in ("ghost/oldtool", "spike/proj")           # discovered, not hard-coded
    assert story["repo"] not in ("botfarm/x", "botmix/y")              # automation never becomes the human story


def test_bot_shaped_repo_is_reported_but_never_chosen(env):
    backfill(env)
    run.process_day(T, fake_source(env, T), out=env["out"])
    cands = json.loads((env["out"] / "candidates.json").read_text())["items"]
    bot = [c for c in cands if c["repo"] == "botmix/y"]
    assert bot and bot[0]["automation_shaped"] is True
    assert bot[0]["automation_reason"]
    # a lone-account repo is below the actor floor by design: it is not a "scene"
    assert not [c for c in cands if c["repo"] == "botfarm/x"]


def test_missing_hour_fails_closed_and_leaves_previous_state_untouched(env):
    backfill(env)
    run.process_day(T, fake_source(env, T), out=env["out"])
    before = (env["out"] / "latest.json").read_text()
    from datetime import date, timedelta
    nxt = (date.fromisoformat(T) + timedelta(days=1)).isoformat()
    from pipeline import synth
    from conftest import spec_for
    synth.write_day(env["raw"], nxt, spec_for(nxt), background_repos=10, drop_hours=(7,))
    with pytest.raises(source.IncompleteDay) as e:
        source.acquire_day(nxt, fetch=lambda d, h: source.path_for(d, h) if source.path_for(d, h).exists() else None)
    assert e.value.missing == [7]
    assert (env["out"] / "latest.json").read_text() == before          # previous good state intact


def test_corrupt_lines_are_counted_not_swallowed(env):
    backfill(env)
    src = fake_source(env, T, corrupt_lines=4)
    run.process_day(T, src, out=env["out"])
    prov = json.loads((env["out"] / "provenance.json").read_text())
    assert prov["accounting"]["rejected"] == 4


def test_high_reject_rate_refuses_to_publish(env):
    backfill(env)
    src = fake_source(env, T, corrupt_lines=5000)
    with pytest.raises(publish.ValidationError):
        run.process_day(T, src, out=env["out"])
    assert not (env["out"] / "latest.json").exists()


def test_rerun_is_idempotent_and_deterministic(env):
    backfill(env)
    run.process_day(T, fake_source(env, T), out=env["out"])
    snap = lambda: {str(p.relative_to(env["out"])): p.read_bytes() for p in env["out"].rglob("*.json")
                    if p.name not in ("latest.json", "status.json", "provenance.json")}   # keyed by full path: stories/ and worlds/ share filenames
    first = snap()
    run.process_day(T, fake_source(env, T), out=env["out"])
    second = snap()
    assert first.keys() == second.keys() and len(first) > 8
    assert first == second
    idx = json.loads((env["out"] / "stories" / "index.json").read_text())["stories"]
    assert len([s for s in idx if s["date"] == T]) == 1                # no duplicate archive entry


def test_warming_up_holds_the_story_instead_of_inventing_a_baseline(env):
    from datetime import date, timedelta
    backfill(env, upto=TARGET, start=TARGET - timedelta(days=3))       # only 3 days of ledger
    res = run.process_day(T, fake_source(env, T), out=env["out"])
    assert res["story"] is None and res["held"].startswith("warming_up")


def test_url_uses_unpadded_hour_as_documented_by_gharchive():
    assert source.url_for("2026-09-22", 5).endswith("/2026-09-22-5.json.gz")
    assert source.url_for("2026-09-22", 15).endswith("/2026-09-22-15.json.gz")


# ---------------- receipts, series, worlds, baseline coverage ----------------

def _events_in_file(day, hour):
    import gzip
    ids = set()
    with gzip.open(source.path_for(day, hour), "rt") as fh:
        for line in fh:
            ids.add(json.loads(line)["id"])
    return ids


def test_every_evidence_event_id_really_exists_in_the_archive_file_it_cites(env):
    backfill(env)
    src = fake_source(env, T)
    run.process_day(T, src, out=env["out"])
    story = json.loads((env["out"] / "stories" / f"{T}.json").read_text())
    ev = story["evidence"]
    assert ev["shown"] > 0 and ev["total"] >= ev["shown"]
    cache = {}
    for e in ev["events"]:
        hour = int(e["file"].split("-")[-1].split(".")[0])
        cache.setdefault(hour, _events_in_file(T, hour))
        assert e["id"] in cache[hour], f"cited event {e['id']} not in {e['file']}"
        assert e["sha256"] == next(f.sha256 for f in src.files if f.hour == hour)
    assert "actor" not in json.dumps(ev).lower()                       # receipts carry no account names


def test_series_marks_unobserved_days_null_not_zero(env):
    from datetime import timedelta
    backfill(env, upto=TARGET, start=TARGET - timedelta(days=40))       # ledger is only 40 days deep
    run.process_day(T, fake_source(env, T), out=env["out"])
    series = json.loads((env["out"] / "stories" / f"{T}.json").read_text())["series"]
    assert len(series) == 120
    assert series[0]["e"] is None                                       # before our record: unknown
    assert series[-1]["e"] > 0                                          # today
    kinds = [p["e"] is None for p in series]
    first_obs = kinds.index(False)
    assert all(kinds[:first_obs]) and not any(kinds[first_obs:])        # unknowns are one prefix, never scattered
    assert 60 <= first_obs <= 100                                       # ~120 window minus ~40 observed days


def test_resurrection_series_gap_equals_the_published_silent_days_claim(env):
    backfill(env)
    run.process_day(T, fake_source(env, T), out=env["out"])
    story = json.loads((env["out"] / "stories" / f"{T}.json").read_text())
    if story["archetype"] != "resurrection":
        pytest.skip("day chose a non-resurrection story")
    claim = next(c for c in story["claims"] if c["metric"] == "silent_days")
    s = story["series"]; n = 0
    for p in reversed(s[:-1]):
        if p["e"] == 0: n += 1
        else: break
    assert n == claim["value"]


def test_baseline_divides_by_observed_days_not_a_fixed_28(env):
    from datetime import timedelta
    backfill(env, upto=TARGET, start=TARGET - timedelta(days=16))       # only 16 observed days
    src = fake_source(env, T)
    con = ingest.connect()
    ingest.load_day(con, src.glob(), T); ledger.build_repo_day(con, T); ledger.attach(con)
    from pipeline import detect
    assert detect.baseline_divisor(con, T) == 16
    row = next(r for r in detect.growth(con, T) if r["repo_name"] == "spike/proj")
    assert 9.0 < row["baseline_mean"] < 11.0                            # ~10/day, NOT ~5.7 (=160/28)
    assert row["baseline_days_used"] == 16


def test_time_machine_worlds_are_kept_pruned_and_indexed(env):
    from datetime import timedelta
    backfill(env, upto=TARGET, start=TARGET - timedelta(days=60))
    for i in range(16, 0, -1):                                          # publish 16 consecutive days
        d = (TARGET - timedelta(days=i - 1)).isoformat()
        from pipeline import synth
        from conftest import spec_for
        synth.write_day(env["raw"], d, spec_for(d), background_repos=10)
        src = source.acquire_day(d, fetch=lambda dd, h: source.path_for(dd, h))
        run.process_day(d, src, out=env["out"])
    idx = json.loads((env["out"] / "worlds" / "index.json").read_text())["days"]
    assert len(idx) == 14 and idx[-1] == T
    assert not (env["out"] / "worlds" / f"{(TARGET - timedelta(days=15)).isoformat()}.json").exists()


def test_a_quiet_day_is_recorded_in_the_archive_not_hidden(env):
    from datetime import timedelta
    backfill(env, upto=TARGET, start=TARGET - timedelta(days=3))
    run.process_day(T, fake_source(env, T), out=env["out"])
    row = json.loads((env["out"] / "stories" / "index.json").read_text())["stories"][0]
    assert row["archetype"] == "none" and row["held_reason"].startswith("warming_up")


def test_story_repo_is_always_on_the_world_map(env):
    backfill(env)
    run.process_day(T, fake_source(env, T), out=env["out"])
    story = json.loads((env["out"] / "stories" / f"{T}.json").read_text())
    world = json.loads((env["out"] / "worlds" / f"{T}.json").read_text())
    assert story["repo_id"] in {n["id"] for n in world["nodes"]}


def test_names_are_stored_only_where_they_can_matter_and_graveyard_still_names_repos(env):
    import duckdb
    backfill(env)
    run.process_day(T, fake_source(env, T), out=env["out"])
    con = duckdb.connect()
    ledger.attach(con)
    tiny = con.execute("SELECT count(*), count(repo_name) FROM ledger WHERE events < 5").fetchone()
    big = con.execute("SELECT count(*), count(repo_name) FROM ledger WHERE events >= 5").fetchone()
    assert tiny[1] == 0 and big[1] == big[0]                            # size policy holds
    gy = json.loads((env["out"] / "graveyard.json").read_text())["rows"]
    assert gy and all(r["repo"] for r in gy)                            # every published repo has a name
    world = json.loads((env["out"] / "worlds" / f"{T}.json").read_text())
    assert all(n["n"] for n in world["nodes"])


def test_ties_never_depend_on_thread_scheduling(env):
    """Regression: arg_max(day, events) returned an arbitrary day among tied peaks, so identical input
    could publish different bytes. dead/proj has the SAME 80 events on 8 days: the peak must be the earliest."""
    import duckdb
    from pipeline import detect
    backfill(env)
    seen = set()
    for threads in (1, 2, 8, 1, 8):
        con = duckdb.connect(); con.execute(f"PRAGMA threads={threads}")
        ledger.attach(con)
        rows = detect.graveyard(con, T)
        seen.add(tuple((r["repo_name"], str(r["peak_day"]), r["silent_days"]) for r in rows))
    assert len(seen) == 1
    (only,) = seen
    dead = next(r for r in only if r[0] == "dead/proj")
    assert dead[1] == "2026-06-01"                                         # earliest of the 8 tied days, every time


def test_a_shared_login_across_repos_produces_a_shared_actor_id_so_edges_can_exist(env):
    """Regression: synth.py used to derive actor_id from (repo_name, actor_slot), so even a repeated
    explicit login got a different id per repo, and the World's shared-actor edges could never appear
    in any synthetic/demo data (reported: 'clusters don't represent anything, nothing is connected')."""
    import duckdb
    from pipeline import synth
    spec = {
        "a/one": {"id": 501, "events": 20, "actors": 2, "types": {"PushEvent": 1}, "logins": ["shared-person", None]},
        "b/two": {"id": 502, "events": 20, "actors": 2, "types": {"PushEvent": 1}, "logins": ["shared-person", None]},
    }
    synth.write_day(env["raw"], T, spec, background_repos=5)
    con = ingest.connect()
    ingest.load_day(con, str(env["raw"] / f"{T}-*.json.gz"), T)
    ids = con.execute("SELECT DISTINCT actor_id FROM events WHERE actor_login = 'shared-person'").fetchall()
    assert len(ids) == 1, f"'shared-person' got {len(ids)} different actor_ids across repos, expected 1"


def test_singular_counts_read_grammatically_in_every_published_claim(env):
    """Regression: story claims said 'from 1 accounts that day.' A single-account repo can never
    reach a story (the floor requires >=2 accounts), so this exercises the real risk: a fork-burst
    or growth repo whose secondary counts (forks, pushes, pull requests) land on exactly 1."""
    from pipeline import claims as claims_mod
    for n, singular, plural_word in [(1, "account", "accounts"), (1, "push", "pushes"), (1, "fork event", "fork events")]:
        assert claims_mod.plural(n, singular, plural_word if plural_word != singular + "s" else None) == f"1 {singular}"
    for n, singular in [(2, "account"), (0, "account"), (5, "push")]:
        assert claims_mod.plural(n, singular).endswith("s")

    backfill(env)
    run.process_day(T, fake_source(env, T), out=env["out"])
    story = json.loads((env["out"] / "stories" / f"{T}.json").read_text())
    text = " ".join(c["text"] for c in story["claims"])
    for bad in ("1 accounts", "1 events", "1 public events", "1 forks", "1 pushes", "1 pull-request events", "1 issue events", "1 comments"):
        assert bad not in text, f"{bad!r} found in: {text}"
