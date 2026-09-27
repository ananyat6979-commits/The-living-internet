"""Durable ledger store on GitHub Releases.

Why: the ledger (per-repo daily rows) is the project's memory of silence. CI runners are ephemeral,
and Actions caches are evictable. A release asset per day is free, durable, and independent of git
history. `gh` is preinstalled on GitHub-hosted runners and authenticates with GITHUB_TOKEN.

All process calls go through `runner` so tests can assert the exact commands without a network."""
from __future__ import annotations
import re, shutil, subprocess, tempfile
from pathlib import Path

from . import ledger

TAG = "ledger-store"
_NAME = re.compile(r"^repo_day-(\d{4}-\d{2}-\d{2})\.parquet$")


def _run(args, runner=subprocess.run, check=True):
    return runner(args, capture_output=True, text=True, check=check)


def remote_days(runner=subprocess.run) -> list[str]:
    r = _run(["gh", "release", "view", TAG, "--json", "assets", "-q", ".assets[].name"], runner, check=False)
    if r.returncode != 0:
        return []
    return sorted(m.group(1) for n in r.stdout.split() if (m := _NAME.match(n)))


def pull_missing(runner=subprocess.run) -> list[str]:
    """Download every day the release has that we don't have locally."""
    have, got = set(ledger.ledger_days()), []
    for day in remote_days(runner):
        if day in have:
            continue
        tmp = Path(tempfile.mkdtemp())
        _run(["gh", "release", "download", TAG, "-p", f"repo_day-{day}.parquet", "-D", str(tmp), "--clobber"], runner)
        dst = ledger.ledger_path(day)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(tmp / f"repo_day-{day}.parquet"), dst)
        shutil.rmtree(tmp, ignore_errors=True)
        got.append(day)
    return got


def push(day: str, runner=subprocess.run):
    """Upload one day's ledger. Creates the release on first use. A failure here is FATAL by design:
    a ledger day that exists only on a disposable runner is a hole in the project's memory."""
    if _run(["gh", "release", "view", TAG], runner, check=False).returncode != 0:
        _run(["gh", "release", "create", TAG, "--title", "Ledger store", "--notes",
              "Per-repository daily activity ledger (Parquet). Machine-managed; do not edit."], runner)
    src = ledger.ledger_path(day)
    named = src.with_name(f"repo_day-{day}.parquet")
    shutil.copyfile(src, named)
    try:
        _run(["gh", "release", "upload", TAG, str(named), "--clobber"], runner)
    finally:
        named.unlink(missing_ok=True)
