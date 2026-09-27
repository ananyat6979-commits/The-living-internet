"""Turn detector rows into stories made ONLY of compiled claims, then choose today's story.

A story is a *sequence of beats*. Each beat has a `visual` key the front-end animates and the
`claims` that justify it. The front-end never receives free prose it cannot trace to a claim.
"""
from __future__ import annotations
import hashlib, math
from .claims import Claim, fmt_int, fmt_fold, plural
from .config import METHOD as M

ARCHETYPES = {
    "resurrection": {"title": "Something came back", "hook": "A long silence ended."},
    "growth":       {"title": "Something got louder", "hook": "One project stepped far outside its own rhythm."},
    "fork":         {"title": "The branches multiplied", "hook": "Many people took a copy of the same project on the same day."},
    "newcomer":     {"title": "Something showed up", "hook": "A repository appeared in the public record for the first time."},
}


def _ev(table_filter: str, day: str, repo_id: int) -> dict:
    return {"source": "gharchive", "table": "ledger", "repo_id": int(repo_id), "day": day, "filter": table_filter}


def automation_shaped(r: dict) -> tuple[bool, str]:
    """A story about a bot is a different story. We do not present it as a human moment."""
    if r.get("top_actor_share") is not None and r["top_actor_share"] >= M.max_top_actor_share and r.get("events", 0) >= 20:
        return True, f"one account produced {r['top_actor_share']*100:.0f}% of the repository's events"
    if r.get("human_like_actors") is not None and r.get("actors", 0) > 0 and r["human_like_actors"] == 0:
        return True, "every observed account name looks automated"
    return False, ""


# ---------- per-archetype builders -> (claims, beats, raw_signals) ----------

def build_resurrection(r, day):
    rid, name = r["repo_id"], r["repo_name"]
    c = {}
    c["silent"] = Claim(f"res:{rid}:silent", "observed",
        f"We observed no public events for {name} for {fmt_int(r['silent_days'])} days, until {day}.",
        "silent_days", int(r["silent_days"]), "days", _ev("last_prior_day → day", day, rid))
    c["before"] = Claim(f"res:{rid}:before", "observed",
        f"Before that gap it appeared on {fmt_int(r['prior_active_days'])} different days in our ledger, with a peak of {fmt_int(r['prior_peak'])} events in one day.",
        "prior_active_days", int(r["prior_active_days"]), "days", _ev("day < target", day, rid))
    c["today"] = Claim(f"res:{rid}:today", "observed",
        f"On {day} we recorded {plural(r['events'], 'public event')} from {plural(r['actors'], 'account')}.",
        "events_today", int(r["events"]), "events", _ev("day = target", day, rid))
    c["shape"] = Claim(f"res:{rid}:shape", "observed",
        f"{plural(r['pushes'], 'push')} were pushes, {plural(r['pull_requests'], 'pull-request event')}, {plural(r['issues'], 'issue event')}, {plural(r['comments'], 'comment')}.",
        "event_mix", f"{r['pushes']}/{r['pull_requests']}/{r['issues']}/{r['comments']}", "events", _ev("day = target", day, rid))
    c["interp"] = Claim(f"res:{rid}:interp", "interpretation",
        "That is a return of public activity after a long stretch of none.")
    c["unknown"] = Claim(f"res:{rid}:unk", "unknown",
        "We cannot tell who is behind this activity, whether it is a person or a script, or why it started. Private work is not shown.")
    beats = [
        {"beat": "hook", "visual": "silence_field", "text": "Nothing.", "claims": []},
        {"beat": "silence", "visual": "silence_stretch", "claims": [c["silent"].id]},
        {"beat": "before", "visual": "past_activity", "claims": [c["before"].id]},
        {"beat": "return", "visual": "reignite", "claims": [c["today"].id, c["shape"].id]},
        {"beat": "read", "visual": "hold", "claims": [c["interp"].id]},
        {"beat": "unknown", "visual": "fade_to_blank", "claims": [c["unknown"].id]},
    ]
    return list(c.values()), beats


def build_growth(r, day):
    rid, name = r["repo_id"], r["repo_name"]
    c = {}
    c["today"] = Claim(f"gro:{rid}:today", "observed",
        f"On {day} we recorded {plural(r['events'], 'public event')} for {name}, from {plural(r['actors'], 'account')}.",
        "events_today", int(r["events"]), "events", _ev("day = target", day, rid))
    c["base"] = Claim(f"gro:{rid}:base", "observed",
        f"Across the {fmt_int(r['baseline_days_used'])} previous days we have on record, it averaged {r['baseline_mean']:.1f} events a day (days it was silent count as zero).",
        "baseline_mean", round(float(r["baseline_mean"]), 2), "events/day", _ev(f"mean over {int(r['baseline_days_used'])} observed days, silent days = 0", day, rid))
    c["fold"] = Claim(f"gro:{rid}:fold", "derived",
        f"That is {fmt_fold(r['fold'])} its usual level, {fmt_int(r['excess'])} events above it.",
        "fold", round(float(r["fold"]), 2), "×", _ev("events / max(baseline_mean, 0.5)", day, rid))
    c["peer"] = Claim(f"gro:{rid}:peer", "derived",
        f"Among the {fmt_int(r['peer_n'])} repositories of similar size that day, it ranked above {r['peer_percentile']*100:.1f}%.",
        "peer_percentile", round(float(r["peer_percentile"]), 4), "fraction", _ev("same log10(events) band", day, rid))
    c["interp"] = Claim(f"gro:{rid}:interp", "interpretation", "This looks unusual for this repository, and for repositories its size.")
    c["unknown"] = Claim(f"gro:{rid}:unk", "unknown",
        "We cannot tell what caused the increase. A release, a mention elsewhere, a script, or ordinary work are all possible; the public stream does not show which.")
    beats = [
        {"beat": "hook", "visual": "baseline_line", "claims": [c["base"].id]},
        {"beat": "spike", "visual": "spike_rise", "claims": [c["today"].id, c["fold"].id]},
        {"beat": "peers", "visual": "peer_strip", "claims": [c["peer"].id]},
        {"beat": "read", "visual": "hold", "claims": [c["interp"].id]},
        {"beat": "unknown", "visual": "fade_to_blank", "claims": [c["unknown"].id]},
    ]
    return list(c.values()), beats


def build_fork(r, day):
    rid, name = r["repo_id"], r["repo_name"]
    c = {}
    c["forks"] = Claim(f"frk:{rid}:n", "observed",
        f"On {day} we recorded {plural(r['forks'], 'fork event')} on {name}.", "forks_today", int(r["forks"]), "forks", _ev("event_type=ForkEvent", day, rid))
    c["fold"] = Claim(f"frk:{rid}:fold", "derived",
        f"Its usual is {r['fork_mean']:.1f} a day, so today was {fmt_fold(r['fold'])} that.", "fold", round(float(r["fold"]), 2), "×", _ev("forks / max(mean,0.5)", day, rid))
    c["unknown"] = Claim(f"frk:{rid}:unk", "unknown",
        "A fork is a copy. We cannot tell why anyone made one, or whether any of them went on to change anything.")
    beats = [
        {"beat": "hook", "visual": "single_node", "claims": []},
        {"beat": "branch", "visual": "fork_burst", "claims": [c["forks"].id, c["fold"].id]},
        {"beat": "unknown", "visual": "fade_to_blank", "claims": [c["unknown"].id]},
    ]
    return list(c.values()), beats


def build_newcomer(r, day, birth_signal_present):
    rid, name = r["repo_id"], r["repo_name"]
    c = {}
    if birth_signal_present and r.get("repo_creates", 0) > 0:
        first = Claim(f"new:{rid}:first", "observed", f"{name} was created on {day}: we recorded its repository-creation event.",
                      "repo_creates", int(r["repo_creates"]), "events", _ev("CreateEvent ref_type=repository", day, rid))
        kind_text = "A repository was created."
    else:
        first = Claim(f"new:{rid}:first", "observed",
            f"{name} appeared in our record for the first time on {day}. We did not see a creation event, so we cannot say it is new to GitHub.",
            "first_seen_day", day, "date", _ev("min(day) over ledger", day, rid))
        kind_text = "A repository showed up in the record."
    c["first"] = first
    c["today"] = Claim(f"new:{rid}:today", "observed",
        f"That day: {plural(r['events'], 'public event')} from {plural(r['actors'], 'account')}.", "events_today", int(r["events"]), "events", _ev("day = target", day, rid))
    c["unknown"] = Claim(f"new:{rid}:unk", "unknown", "We cannot tell who is behind it or where it is headed.")
    beats = [
        {"beat": "hook", "visual": "single_node", "text": kind_text, "claims": []},
        {"beat": "first", "visual": "birth_point", "claims": [c["first"].id, c["today"].id]},
        {"beat": "unknown", "visual": "fade_to_blank", "claims": [c["unknown"].id]},
    ]
    return list(c.values()), beats


# ---------- scoring & selection ----------

def _clip(x): return max(0.0, min(1.0, x))


def signals(kind, r) -> dict:
    """Editorial-priority signals in [0,1]. Internal only; never shown to visitors."""
    if kind == "resurrection":
        return {"novelty": _clip(math.log10(max(1, r["silent_days"])) / 3.0),
                "magnitude": _clip(math.log10(max(1, r["events"])) / 3.0),
                "evidence": _clip(r["prior_active_days"] / 30.0),
                "humanness": _clip(r["human_like_actors"] / max(1, r["actors"]))}
    if kind == "growth":
        return {"novelty": _clip((r["peer_percentile"] - 0.9) / 0.1),
                "magnitude": _clip(math.log10(max(1, r["fold"])) / 2.0),
                "evidence": _clip(r["active_days"] / 28.0),
                "humanness": _clip(r["human_like_actors"] / max(1, r["actors"]))}
    if kind == "fork":
        return {"novelty": _clip(math.log10(max(1, r["fold"])) / 2.0),
                "magnitude": _clip(math.log10(max(1, r["forks"])) / 3.0),
                "evidence": 0.7, "humanness": _clip(r["human_like_actors"] / max(1, r["actors"]))}
    return {"novelty": 0.5, "magnitude": _clip(math.log10(max(1, r["events"])) / 3.0), "evidence": 0.5,
            "humanness": _clip(r["human_like_actors"] / max(1, r["actors"]))}


def editorial_priority(sig: dict) -> float:
    return 0.35 * sig["novelty"] + 0.25 * sig["magnitude"] + 0.20 * sig["evidence"] + 0.20 * sig["humanness"]


def make_stories(day, det, birth_health, recent_archetypes, ledger_days):
    """det: dict(kind -> rows). Returns (all_candidates, chosen_or_None, held_reason_or_None)."""
    if ledger_days < M.ledger_min_coverage_days:
        return [], None, f"warming_up:{ledger_days}/{M.ledger_min_coverage_days}"
    cands = []
    for kind, rows in det.items():
        for r in rows:
            auto, why = automation_shaped(r)
            if kind == "resurrection":
                claims, beats = build_resurrection(r, day)
            elif kind == "growth":
                claims, beats = build_growth(r, day)
            elif kind == "fork":
                claims, beats = build_fork(r, day)
            elif kind == "newcomer":
                claims, beats = build_newcomer(r, day, birth_health["birth_signal_present"])
            else:
                continue
            sig = signals(kind, r)
            prio = editorial_priority(sig)
            prio -= M.diversity_penalty * recent_archetypes.count(kind)
            cands.append({
                "id": f"{day}:{kind}:{r['repo_id']}",
                "archetype": kind, "repo_id": int(r["repo_id"]), "repo": r["repo_name"],
                "title": ARCHETYPES[kind]["title"], "hook": ARCHETYPES[kind]["hook"],
                "automation_shaped": auto, "automation_reason": why,
                "priority": round(prio, 4),
                "claims": [c.to_dict() for c in claims], "beats": beats,
            })
    # Automation-shaped stories are kept (they are real) but never chosen as the human-moment daily story.
    cands.sort(key=lambda c: (c["automation_shaped"], -c["priority"], c["id"]))
    eligible = [c for c in cands if not c["automation_shaped"]]
    chosen = eligible[0] if eligible else None
    return cands, chosen, (None if chosen else "no_eligible_candidate")
