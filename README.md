# The Living Internet

*Somewhere, something is being built.*

A scroll-driven data documentary about public human activity on GitHub. It updates itself from real data, costs nothing to run, and **refuses to say anything the data can't back up.**

It is not a GitHub dashboard. It has no leaderboard and no productivity score. It follows one repository at a time through silence, return, surge or branching, and lets you ask, under every sentence, *how do we know?*

## What is real, and what is not (read this first)

| | Status |
|---|---|
| Pipeline logic (ledger, detectors, claims, publish, pulse, store) | Built. **33 tests pass** on Python 3.10, 3.11, 3.12 and 3.13, on synthetic GH-Archive-shaped files, plus real GH-Archive-shaped free-text edge cases. Confirmed against one real hour of GH Archive on Windows. |
| Front-end (story, world, time, graveyard, archive, method) | Built. **33 tests pass** in jsdom. Production build ≈ 14 KB gzipped JS. |
| Workflow | Written and YAML-validated. **Never run on GitHub.** |
| **Against real GH Archive files** | **Never run.** The author's sandbox could not reach `data.gharchive.org`. The URL, file format and field names follow GH Archive's documentation. Expect first-contact surprises; the first backfill is the real test. |
| Visual design in a real browser | **Never seen by the author.** No browser was available. DOM behaviour is tested; how it *looks* and *feels*, especially the canvas, scroll pacing and mobile layout, needs your eyes. |
| Demo data | Produced by the real pipeline from invented input, and stamped `synthetic: true`. The UI shows a banner; CI refuses to deploy it. |

## Quick start (Windows PowerShell, VS Code)

Extract the zip into a **new, empty folder** (not over an older copy). Open that folder in VS Code; it must contain `setup.ps1`, `site` and `pipeline`. In the VS Code terminal:

```powershell
.\setup.ps1
.\.venv\Scripts\Activate.ps1
npm run dev
```

Open http://localhost:5173. `setup.ps1` picks the newest Python from 3.10 to 3.13 that you have installed, creates `.venv`, installs into it (never into your global Python), runs `npm ci` inside `site\`, and makes SYNTHETIC demo data.

Manual equivalent (use a version you actually have; `py --list` shows them):

```powershell
py -3.13 -m venv .venv ; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
npm run setup                    # = npm --prefix site ci   (there is no package.json to install at the repo root itself)
npm run demo                     # SYNTHETIC data into site\public\data
npm run dev
python -m pytest -q              # pipeline tests
npm test                         # site tests (regenerate their own demo data; needs the venv active)
```

Troubleshooting:

- **`.\setup.ps1 is not recognized`**: you are in the wrong folder or have an old copy. `dir` should list `setup.ps1`.
- **`No suitable Python runtime found` for `py -3.12`**: you do not have 3.12. Use `setup.ps1`, or a version from `py --list`.
- **`Cannot find type definition file for 'node'`**: `npm ci` was never run inside `site\`. Run `npm run setup`, then in VS Code run *TypeScript: Restart TS Server*.
- **`ModuleNotFoundError: duckdb`** during `npm run demo` or `npm test`: activate the venv in that terminal first.

## Trying it on REAL GitHub data (do these in order)

The pipeline has never touched a real GH Archive file, so start small. All commands run in the repo root with the venv active.

**1. One hourly file, about a minute. Writes nothing to the site.**

```powershell
python -m pipeline.check
```

It downloads one hour from two days ago, then prints what it sees: file size, parse accounting, event types (flagging any we don't know), whether repository-creation events still exist, bot-like share, the busiest repositories, and how concentrated they are by owner. It saves `work\check-<date>-12.json`. If anything looks wrong, that file is what I need. The size it prints tells you roughly what a full day costs (about 24 times that).

**2. One full real day.**

```powershell
python -m pipeline.run --date 2026-09-22      # use a date at least 2 days ago
```

This REPLACES the demo data in `site\public\data` with real data (`synthetic: false`) and builds your local ledger in `state\`. With one day of record the site will say "Still learning what normal looks like". That is correct, not a bug. Restore the demo any time with `npm run demo`.

**3. Enough history for stories to begin (14 days minimum).**

```powershell
python -m pipeline.run --backfill 13          # yesterday plus 13 earlier days; days already in state\ are skipped
```

Each day is 24 downloads, so this takes a while. A day with a missing hour is held and reported, never half-published. Re-run the same command to retry.

Your local ledger (`state\`) is not shared with GitHub Actions. For the live site, let the workflow do its own backfill (`backfill_days = 30`) rather than uploading yours.

## Going live (free)

1. Push to a **public** GitHub repo (Actions and Pages are free for public repos).
2. **Settings → Pages → Source: GitHub Actions.**
3. **Actions → update-and-deploy → Run workflow**, with `backfill_days = 30`. This seeds the ledger so stories can begin. Until the ledger holds `ledger_min_coverage_days` (14) days the site says *"Still learning what normal looks like"* instead of guessing. The first backfill downloads 30 days × 24 hourly files and may take hours; the job allows ~5.5.
4. From then on it runs itself: the daily story at 05:17 UTC (retrying at later slots if an hour was missing) and a pulse roughly every 6 hours.

**Check before trusting:** the action versions in the workflow (`checkout@v4`, `cache@v4`, `deploy-pages@v4`…) were the ones I knew; Dependabot is configured to keep them current. Verify the exact current majors.

## How it stays honest

- **One immutable chain:** GH Archive file → SHA-256 → DuckDB → ledger → detector → **claim** → story → browser. The UI cannot invent a fact. It has no hard-coded metrics, and `Math.random` is never used for anything semantic.
- **Claims:** every sentence is a typed claim (`observed`, `derived`, `interpretation`, `unknown`) with evidence attached. The compiler *rejects* wording the stream cannot support: "commits", "merged", "decided", "abandoned", "collaborated", place names, "midnight". These are tested.
- **Receipts:** each story ships real GitHub event ids with the archive file and hash each lives in, so a sceptic can `zcat | grep` them. Account names are not published.
- **Fail closed:** a day publishes only if all 24 hourly files are present, gzip-valid and >99% parseable. Otherwise the previous state stays live and says so. Failed updates never replace good ones.
- **Silence is measured:** the ledger keeps every repo-day, so "N observed-silent days" is a query. Days before our record began are *unknown*, never zero, and the baseline divides by observed days only.
- **Automation is not a human moment:** repos dominated by one account, or where every name looks like a bot, are recorded but never chosen as the day's story.
- **No fake liveness:** the pulse reports missing hours as `partial`; if there is nothing, it says `unavailable`. GH Archive lags by hours, and the UI says "a few hours ago".

## What "automatic" actually means right now

Nothing updates on its own until this repository is pushed to GitHub with the included workflow enabled (see "Going live" above). Running `pipeline.run` locally, on your own machine, is always manual: you type the command, it processes one day, and it stops. The site's closing screen states the scheduled time (05:17 UTC, converted to your local clock) only as a description of when the *deployed* workflow runs, and it says outright that a local checkout with no workflow running updates only when you run the pipeline yourself.

`python -m pipeline.check` always defaults to two days ago unless you pass `--date`, and now prints which date it is actually using, since running `check` and `run` with different (or default) dates is not a bug, each command does exactly what you told it to.

## Known limits (deliberate honesty)

- **GitHub trimmed public event payloads on 2025-10-07** (commit summaries, PR merge details). The pipeline counts *events*, not commits. Whether repository-creation events are still emitted is **measured every day** (`status.json → birth_signal`); if absent, stories say "first seen in our record", not "created".
- **The record starts the day the pipeline first ran.** There is no 2011 here. The Graveyard needs ≥90 quiet days and opens ~3 months in; the Time Machine keeps 14 days of worlds. Depth grows daily, which is the point.
- **Storage:** measured on synthetic data with a realistic skew, the slim ledger is ≈1.5 MB/day (≈0.5 GB/yr) at ~500k active repos/day, *if* real GitHub looks like my model. It lives in a GitHub Release (durable) plus Actions cache (fast). Real numbers will differ; check the first week.
- **Actions cache** is evictable; on a miss the runner re-pulls the ledger from the Release. Push failure is fatal by design.
- **Statistics:** the percentile is against similar-size repositories *that day*; this searches hundreds of thousands of candidates, so "unusual" is an editorial threshold, not a p-value. The methodology page says so.
- **Not built:** per-actor trajectories ("Show me someone"), topic classification, and a real-browser visual regression suite. I removed rather than faked them; a re-identification risk in trajectories needs a privacy design first.
- **Accessibility:** DOM story is real text; canvas is `aria-hidden` with every loudest repo also a button; native `<details>`, sliders, focus rings, `prefers-reduced-motion`, text labels on every state. Not audited with a screen reader.

## Layout

```
pipeline/   source.py ingest.py ledger.py detect.py claims.py stories.py
            world.py publish.py pulse.py store.py run.py demo.py synth.py
tests/      offline pipeline tests
site/       Vite + strict TypeScript, D3-free (canvas + SVG), ~14 KB JS
  src/lib/  world.ts (persistent canvas) storyview.ts chart.ts series.ts
            data.ts dom.ts audio.ts session.ts
.github/    update-and-deploy.yml  dependabot.yml
```

Data is the evidence. The story is what the visitor discovers.
