"""Single place for every threshold. Methodology text is generated from these
values so the documentation cannot drift from the code."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "state"            # ledger + manifests (cached between runs, NOT committed)
RAW = ROOT / "work" / "raw"       # hourly archives (temporary, never committed)
OUT = ROOT / "site" / "public" / "data"   # compact, browser-facing artefacts (served as /data/*)
FIXTURES = ROOT / "fixtures"

BASE_URL = "https://data.gharchive.org"


@dataclass(frozen=True)
class Method:
    # --- eligibility: a repo must clear this to even be considered ---
    min_events_today: int = 12          # below this, a "spike" is noise
    min_distinct_actors_today: int = 2  # one actor alone is a script, not a scene
    # --- baseline ---
    baseline_days: int = 28             # window that defines "normal"
    min_baseline_days_observed: int = 14  # need this many days of ledger coverage for the repo's window
    # --- growth / spike ---
    min_fold: float = 4.0
    min_absolute_excess: int = 30
    min_percentile: float = 0.995       # vs comparable repo-days
    # --- resurrection ---
    resurrection_min_silent_days: int = 60   # observed-silent gap before today
    resurrection_min_prior_active_days: int = 5
    resurrection_min_events_today: int = 10
    # --- graveyard ---
    graveyard_min_silent_days: int = 90
    graveyard_min_peak_events: int = 40
    # --- fork burst ---
    fork_min_forks: int = 25
    fork_min_fold: float = 6.0
    # --- bot / automation suppression ---
    bot_login_suffixes: tuple = ("[bot]", "-bot", "bot")   # matched on login
    max_top_actor_share: float = 0.80   # one actor > 80% of a repo's events => automation-shaped
    # --- selection ---
    diversity_penalty: float = 0.35     # per already-featured archetype in the last 7 days
    ledger_min_coverage_days: int = 14  # below this we say "warming up" instead of finding resurrections

METHOD = Method()

# Which raw event types we count, and what they are called to a human.
EVENT_KINDS = {
    "PushEvent": "push",
    "PullRequestEvent": "pull_request",
    "IssuesEvent": "issue",
    "IssueCommentEvent": "comment",
    "PullRequestReviewEvent": "review",
    "PullRequestReviewCommentEvent": "review_comment",
    "CommitCommentEvent": "comment",
    "ForkEvent": "fork",
    "WatchEvent": "star",
    "ReleaseEvent": "release",
    "CreateEvent": "create",
    "DeleteEvent": "delete",
    "PublicEvent": "public",
    "MemberEvent": "member",
    "GollumEvent": "wiki",
    "DiscussionEvent": "discussion",
}

def method_dict() -> dict:
    d = asdict(METHOD)
    d["bot_login_suffixes"] = list(d["bot_login_suffixes"])
    return d
