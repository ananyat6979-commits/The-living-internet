"""Write the browser-facing artefacts, atomically, into a candidate dir, validate, then promote.

The site only ever sees a directory that fully validated. A failed run leaves the previous
`src/data` untouched (additive, not destructive)."""
from __future__ import annotations
import json, os, shutil, hashlib
from datetime import datetime, timezone
from pathlib import Path

from . import PIPELINE_VERSION, ENGINE_VERSION
from .config import OUT, method_dict


def _dump(p: Path, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True), encoding="utf-8")


def _sha(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:16]


class ValidationError(RuntimeError):
    pass


def validate_story(s: dict):
    ids = {c["id"] for c in s["claims"]}
    for b in s["beats"]:
        for cid in b["claims"]:
            if cid not in ids:
                raise ValidationError(f"{s['id']}: beat references unknown claim {cid}")
    for c in s["claims"]:
        if c["cls"] in ("observed", "derived") and not c.get("evidence"):
            raise ValidationError(f"{s['id']}: claim {c['id']} lacks evidence")


def build_artifacts(*, day, source, accounting, day_totals, hourly, top_repos, chosen, candidates,
                    held_reason, birth_health, ledger_days, graveyard_rows, history_rows,
                    prior_stories, world, generated_at=None, extras=None):
    generated_at = generated_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    for s in candidates:
        validate_story(s)
    reject_rate = accounting["rejected"] / max(1, accounting["lines_read"])
    if reject_rate > 0.01:
        raise ValidationError(f"reject rate {reject_rate:.3%} exceeds 1%, refusing to publish")

    provenance = {
        "source": "GH Archive (data.gharchive.org)", "source_date": day, "source_hours": 24,
        "files": source.manifest, "accounting": accounting,
        "pipeline_version": PIPELINE_VERSION, "engine_version": ENGINE_VERSION,
        "generated_at": generated_at, "git_sha": os.environ.get("GITHUB_SHA", "local"),
    }
    latest = {
        "date": day, "generated_at": generated_at, "events": day_totals["events"],
        "actors": day_totals["actors"], "repositories": day_totals["repos"],
        "status": "current", "held_reason": held_reason,
        "story_id": chosen["id"] if chosen else None,
        "candidates": len(candidates), "ledger_days": ledger_days, "synthetic": False,
    }
    day_story = None
    if chosen:
        # Identity of the DATA this story derives from: source hashes + versions + accounting.
        # Deliberately excludes generated_at/git_sha so re-running an unchanged day is byte-identical.
        data_identity = {k: provenance[k] for k in ("source_date", "files", "accounting", "pipeline_version", "engine_version")}
        day_story = {**chosen, **(extras or {}), "date": day, "provenance_sha": _sha(data_identity)}

    stories_index = [x for x in prior_stories if x["date"] != day]
    if day_story:
        stories_index.append({"date": day, "id": day_story["id"], "archetype": day_story["archetype"],
                              "title": day_story["title"], "repo": day_story["repo"], "held_reason": None})
    else:   # a day with no story is still a day: say so, and say why. That is also data.
        warming = (held_reason or "").startswith("warming_up")
        stories_index.append({"date": day, "id": None, "archetype": "none", "repo": "",
                              "title": "Still learning what normal looks like" if warming else "Nothing crossed the line",
                              "held_reason": held_reason})
    stories_index.sort(key=lambda x: x["date"], reverse=True)

    status = {
        "status": "current", "last_success": generated_at, "source_date": day,
        "hours": "24/24", "events": day_totals["events"], "rejected_lines": accounting["rejected"],
        "reject_rate": round(reject_rate, 6), "candidates": len(candidates),
        "birth_signal": birth_health, "ledger_days": ledger_days,
        "pipeline_version": PIPELINE_VERSION, "engine_version": ENGINE_VERSION,
    }
    return {
        "latest.json": latest, "status.json": status, "provenance.json": provenance,
        "method.json": method_dict(), "hourly.json": {"date": day, "hours": hourly},
        f"worlds/{day}.json": world, "graveyard.json": {"date": day, "rows": graveyard_rows},
        "history.json": {"days": history_rows},
        "stories/index.json": {"stories": stories_index},
        **({f"stories/{day}.json": day_story} if day_story else {}),
        "candidates.json": {"date": day, "held_reason": held_reason,
                            "items": [{k: c[k] for k in ("id", "archetype", "repo", "automation_shaped", "automation_reason")} for c in candidates]},
    }


WORLD_DAYS_KEPT = 14


def _prune_worlds(stage: Path):
    wd = stage / "worlds"
    if not wd.exists():
        return
    files = sorted(p for p in wd.glob("*.json") if p.name != "index.json")
    for p in files[:-WORLD_DAYS_KEPT]:
        p.unlink()
    keep = sorted(p.stem for p in wd.glob("*.json") if p.name != "index.json")
    _dump(wd / "index.json", {"days": keep})


def promote(artifacts: dict, out: Path = OUT):
    """Atomic-ish: write to a sibling dir, then swap. Old files not present in the new set are kept
    if they are story archives (memory); everything else is replaced."""
    stage = out.parent / (out.name + ".stage")
    if stage.exists():
        shutil.rmtree(stage)
    if out.exists():
        shutil.copytree(out, stage)          # start from current state (additive)
    else:
        stage.mkdir(parents=True)
    for rel, obj in artifacts.items():
        _dump(stage / rel, obj)
    _prune_worlds(stage)
    # JSON sanity: everything we wrote must parse.
    for p in stage.rglob("*.json"):
        json.loads(p.read_text(encoding="utf-8"))
    backup = out.parent / (out.name + ".prev")
    if backup.exists():
        shutil.rmtree(backup)
    if out.exists():
        out.rename(backup)
    stage.rename(out)
    if backup.exists():
        shutil.rmtree(backup)
