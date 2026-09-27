from conftest import TARGET, spec_for
from pipeline import check, source, synth

T = TARGET.isoformat()


def test_check_reports_what_the_pipeline_sees_on_one_file(env):
    synth.write_day(env["raw"], T, spec_for(T), background_repos=40, corrupt_lines=2)
    r = check.run(T, 3, fetch=lambda d, h, retries=2: source.path_for(d, h))
    assert r["ok"] and r["accounting"]["rejected"] == 2 and r["events"] > 10
    assert r["event_types"]["PushEvent"] > 0 and r["repo_creation_events_present"] is False
    assert r["owner_concentration_top700"]["distinct_owners"] >= 1
    text = check.render(r)
    assert "repository-creation events present: False" in text and "first seen in our record" in text


def test_check_says_how_to_recover_when_the_download_fails():
    r = check.run("2026-01-01", 1, fetch=lambda d, h, retries=2: None)
    assert r["ok"] is False and "data.gharchive.org/2026-01-01-1.json.gz" in r["url"]
    assert "network" in check.render(r) and "2 days ago" in check.render(r)
