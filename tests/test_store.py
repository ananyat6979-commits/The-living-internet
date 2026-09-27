from types import SimpleNamespace
import pytest
from pipeline import ledger, store


class FakeGH:
    def __init__(self, assets=(), release_exists=True, fail_upload=False):
        self.calls, self.assets, self.exists, self.fail_upload = [], list(assets), release_exists, fail_upload

    def __call__(self, args, capture_output, text, check):
        self.calls.append(args)
        if args[:3] == ["gh", "release", "view"] and "--json" in args:
            return SimpleNamespace(returncode=0 if self.exists else 1, stdout="\n".join(self.assets))
        if args[:3] == ["gh", "release", "view"]:
            return SimpleNamespace(returncode=0 if self.exists else 1, stdout="")
        if args[:3] == ["gh", "release", "create"]:
            self.exists = True
        if args[:3] == ["gh", "release", "download"]:
            d = args[args.index("-D") + 1]; name = args[args.index("-p") + 1]
            (__import__("pathlib").Path(d) / name).write_bytes(b"PAR1")
        if args[:3] == ["gh", "release", "upload"] and self.fail_upload:
            raise RuntimeError("upload failed")
        return SimpleNamespace(returncode=0, stdout="")


def test_remote_days_parses_only_ledger_asset_names(env):
    gh = FakeGH(["repo_day-2026-09-20.parquet", "notes.txt", "repo_day-2026-09-21.parquet"])
    assert store.remote_days(gh) == ["2026-09-20", "2026-09-21"]


def test_pull_missing_downloads_only_what_we_do_not_have(env):
    have = ledger.ledger_path("2026-09-20"); have.parent.mkdir(parents=True); have.write_bytes(b"x")
    gh = FakeGH(["repo_day-2026-09-20.parquet", "repo_day-2026-09-21.parquet"])
    assert store.pull_missing(gh) == ["2026-09-21"]
    assert ledger.ledger_path("2026-09-21").exists()


def test_push_creates_release_once_and_uploads(env):
    p = ledger.ledger_path("2026-09-22"); p.parent.mkdir(parents=True); p.write_bytes(b"PAR1")
    gh = FakeGH(release_exists=False)
    store.push("2026-09-22", gh)
    verbs = [c[2] for c in gh.calls]
    assert "create" in verbs and "upload" in verbs
    assert not p.with_name("repo_day-2026-09-22.parquet").exists()      # temp copy cleaned up


def test_push_failure_is_fatal_not_swallowed(env):
    p = ledger.ledger_path("2026-09-22"); p.parent.mkdir(parents=True); p.write_bytes(b"PAR1")
    with pytest.raises(RuntimeError):
        store.push("2026-09-22", FakeGH(fail_upload=True))
