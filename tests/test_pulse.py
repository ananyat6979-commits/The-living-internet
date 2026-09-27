from datetime import datetime, timezone
from conftest import TARGET, spec_for, backfill
from pipeline import pulse, source, synth

NOW = datetime(2026, 9, 23, 9, 30, tzinfo=timezone.utc)


def _write(env):
    synth.write_day(env["raw"], "2026-09-23", spec_for(TARGET.isoformat()), background_repos=20)


def test_pulse_ignores_the_still_open_hours():
    hrs = pulse.latest_complete_hours(NOW, 6)
    assert [h.hour for h in hrs] == [2, 3, 4, 5, 6, 7] and all(h < NOW.replace(minute=0) for h in hrs)


def test_pulse_reports_a_missing_hour_as_partial_and_never_fills_it_in(env):
    backfill(env); _write(env)
    p = pulse.build_pulse(NOW, fetch=lambda d, h: source.path_for(d, h) if h != 5 else None, out=env["out"])
    assert p["status"] == "partial" and p["available_hours"] == 5 and p["missing"] == ["2026-09-23 05:00Z"]
    assert len(p["hours"]) == 5 and p["window"]["events"] == sum(h["e"] for h in p["hours"])


def test_pulse_with_nothing_is_unavailable_not_invented(env):
    backfill(env)
    p = pulse.build_pulse(NOW, fetch=lambda d, h: None, out=env["out"])
    assert p["status"] == "unavailable" and p["hours"] == [] and p["loudest"] == []


def test_pulse_never_features_automation_and_judges_against_ledger_baseline(env):
    backfill(env); _write(env)
    p = pulse.build_pulse(NOW, fetch=lambda d, h: source.path_for(d, h), out=env["out"])
    names = [r["repo"] for r in p["loudest"]]
    assert "botmix/y" not in names and "spike/proj" in names
    spike = next(r for r in p["loudest"] if r["repo"] == "spike/proj")
    assert 9 < spike["usual_per_day"] < 11                            # its ledger mean (~10/day), not zero, not inflated
