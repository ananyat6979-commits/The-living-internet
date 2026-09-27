import "./styles.css";
import { h, $, fill } from "./lib/dom";
import { loadBundle, loadStory, loadWorld, fmt, ago, freshness, safeRepoUrl, DataUnavailable } from "./lib/data";
import { WorldView, type Mode } from "./lib/world";
import { renderStory } from "./lib/storyview";
import { barStrip, lineChart } from "./lib/chart";
import { Session, nextDailyUpdate } from "./lib/session";
import { Soundscape } from "./lib/audio";
import type { Bundle, Story, WorldNode, GraveRow, StoryIndexRow } from "./types";

const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
const session = new Session();
const sound = new Soundscape();

boot().catch((e) => fail(e));

function fail(e: unknown) {
  const app = document.getElementById("app")!;
  fill(app, h("main", { class: "unavailable" },
    h("h1", {}, "The Living Internet"),
    h("p", { class: "word" }, e instanceof DataUnavailable ? "Nothing has been published yet." : "We couldn't load today's record."),
    h("p", {}, "We would rather show you nothing than something we can't stand behind. The last good snapshot, if there is one, stays online; a failed update never replaces it."),
    h("p", { class: "fine" }, String(e instanceof Error ? e.message : e))));
}

async function boot() {
  const b = await loadBundle();
  const app = document.getElementById("app")!;
  const canvas = h("canvas", { id: "world-canvas", "aria-hidden": "true" });
  const world = new WorldView(canvas);
  world.reducedMotion = reduced;
  world.setWorld(b.world);
  sound.setHours(Array.from({ length: 24 }, (_, i) => b.hourly.hours.find((x) => x.h === i)?.e ?? 0));

  const fresh = freshness(b.latest.generated_at);
  const storyRoot = h("div", { id: "story-root" });

  fill(app, 
    b.latest.synthetic ? h("div", { class: "synthetic", role: "note" }, "SYNTHETIC DEMO DATA. Produced by the real pipeline from invented input. This is not GitHub.") : null,
    h("div", { class: "stage" }, canvas, h("div", { class: "veil" })),
    header(b, fresh, world),
    opening(b, fresh),
    worldSection(b, world),
    h("section", { id: "story", class: "chapter", "aria-label": "Today's story", "data-mode": "overview" }, storyRoot),
    timeSection(b, world),
    graveSection(b),
    archiveSection(b, (d) => openStory(d)),
    methodSection(b),
    epilogue(b),
  );

  // ---- the director: scroll position decides the World's mode; the words never move it ----
  let io: IntersectionObserver | null = null;
  let active: Element | null = null;
  const direct = (el: Element) => {
    if (active === el) return; active?.classList.remove("is-active"); active = el; el.classList.add("is-active");
    const d = (el as HTMLElement).dataset;
    const mode = (d.mode ?? "overview") as Mode;
    world.setMode(mode, { focusId: d.focus ? Number(d.focus) : null });
    el.querySelector<SVGElement>(".chart")?.setAttribute("data-highlight", d.highlight ?? "none");
    sound.setQuiet(mode === "silence" || mode === "graveyard");
    if (mode === "reignite") sound.swell();
    if (el.id) session.chaptersReached.add(el.id);
  };
  const observe = () => {
    io?.disconnect();
    io = new IntersectionObserver((entries) => { for (const e of entries) if (e.isIntersecting) direct(e.target); }, { threshold: 0.55 });
    document.querySelectorAll("[data-mode]").forEach((el) => io!.observe(el));
  };

  // ---- story loading & deep links ----
  async function openStory(date: string, scroll = true) {
    const s = date === b.latest.date ? b.story : await loadStory(date);
    const wDate = b.worldDays.includes(date) ? date : null;
    if (wDate) { const w = await loadWorld(wDate); if (w) world.setWorld(w); }
    fill(storyRoot, s ? storyIntro(s.date === b.latest.date) : null, s ? renderStory(s, { onEvidence: () => { session.evidenceOpened++; }, links: !b.latest.synthetic }) : quietDay(b, date), s ? exitStep(b, s) : null);
    if (s) session.storiesOpened.add(s.id);
    observe();
    history.replaceState(null, "", `#story=${date}`);
    if (scroll) $("#story").scrollIntoView({ behavior: reduced ? "auto" : "smooth" });
  }
  const hashDate = /^#story=(\d{4}-\d{2}-\d{2})$/.exec(location.hash)?.[1];
  await openStory(hashDate ?? b.latest.date, !!hashDate);
  if (!hashDate && b.story) session.storiesOpened.delete(b.story.id);   // not opened by the visitor yet

  // ---- clock, audio, session ----
  const tick = () => { const n = new Date(); const el = document.getElementById("clock"); if (el) el.textContent = `${n.toLocaleTimeString([], { hour12: false })} ${new Intl.DateTimeFormat([], { timeZoneName: "short" }).formatToParts(n).find((p) => p.type === "timeZoneName")?.value ?? ""}`; };
  tick(); setInterval(tick, 1000);
  document.getElementById("audio")?.addEventListener("click", async (e) => { const on = await sound.toggle(); (e.currentTarget as HTMLElement).setAttribute("aria-pressed", String(on)); (e.currentTarget as HTMLElement).textContent = on ? "Sound: on" : "Sound: off"; });
  new IntersectionObserver((es) => { for (const e of es) if (e.isIntersecting) renderEpilogue(b); }, { threshold: 0.4 }).observe($("#epilogue"));
  observe();
}

// ---------------------------------------------------------------- header / opening
function header(b: Bundle, fresh: ReturnType<typeof freshness>, world: WorldView): HTMLElement {
  void world;
  const link = (id: string, t: string) => h("a", { href: `#${id}` }, t);
  return h("header", { class: "top" },
    h("nav", { "aria-label": "Sections" }, link("world", "World"), link("story", "Story"), link("time", "Time"), link("graveyard", "Graveyard"), link("archive", "Archive"), link("method", "Method")),
    h("span", { class: `pill pill--${fresh.state}`, title: `Source day ${b.latest.date}` }, fresh.label),
    h("button", { id: "audio", class: "btn", "aria-pressed": "false", type: "button" }, "Sound: off"));
}

function opening(b: Bundle, fresh: ReturnType<typeof freshness>): HTMLElement {
  const n = h("span", { class: "big-number", "data-target": b.latest.events }, reduced ? fmt(b.latest.events) : "0");
  if (!reduced) countUp(n, b.latest.events);
  return h("section", { id: "opening", class: "chapter opening", "data-mode": "overview", "aria-label": "Opening" },
    h("div", { class: "opening-inner" },
      h("p", { class: "reveal r1 word" }, "The internet is alive."),
      h("p", { class: "reveal r2 lede" }, "Somewhere, something is being built."),
      h("p", { class: "reveal r3 mono" }, h("span", { id: "clock" }, "--:--:--"), " where you are"),
      h("p", { class: "reveal r4" }, n, " public GitHub events on ", h("time", { datetime: b.latest.date }, b.latest.date), " (UTC)."),
      h("p", { class: "reveal r5 fine" }, "None of these existed as pixels on this screen until someone did something. This is one window into the internet, not the whole of it. Public doesn't mean complete."),
      fresh.state === "stale" ? h("p", { class: "stale-note", role: "status" }, `${fresh.label}. The world below has not changed since then.`) : null,
      h("a", { class: "btn btn--go reveal r6", href: "#world" }, "Enter")));
}
function countUp(el: HTMLElement, target: number) {
  const t0 = performance.now(), dur = 1800;
  const f = (t: number) => { const k = Math.min(1, (t - t0) / dur); el.textContent = fmt(Math.round(target * (1 - Math.pow(1 - k, 3)))); if (k < 1) requestAnimationFrame(f); };
  requestAnimationFrame(f);
}

function edgeNote(edgeCount: number, ledgerDays: number): HTMLElement {
  // A line joins two repositories only when at least two of the SAME non-automated accounts
  // appeared in both, on the same day. With very little ledger history, one honest connection (or
  // zero) is the expected result, not a bug: a real person rarely touches two unrelated repos in
  // one day. This line makes that fact visible instead of leaving a lone edge unexplained.
  const young = ledgerDays < 14 ? ` We only have ${fmt(ledgerDays)} day${ledgerDays === 1 ? "" : "s"} of record so far, so most real overlaps have not had a chance to show up yet.` : "";
  if (edgeCount === 0) return h("p", { class: "fine" }, `No two repositories here shared two of the same accounts today.${young} Lines will appear as reused contributors show up.`);
  return h("p", { class: "fine" }, `${fmt(edgeCount)} line${edgeCount === 1 ? "" : "s"} on the map: a real pair of repositories that shared two or more of the same non-automated accounts that day.${young}`);
}

// ---------------------------------------------------------------- world
// A click on a point opens a fixed side panel (id="node-panel") that slides in from the right and
// stays visible regardless of scroll position. The earlier version appended the same content as a
// static block at the bottom of the #world card: real, but invisible on any normal-height screen
// until you scrolled down past the loudest-repos list, which read as "nothing happened" on click.
function worldSection(b: Bundle, world: WorldView): HTMLElement {
  const panel = h("aside", { id: "node-panel", class: "node-panel", "aria-live": "polite", "aria-label": "Selected repository" });
  const closePanel = () => { panel.classList.remove("is-open"); world.setMode("overview"); };
  panel.append(h("button", { type: "button", class: "node-panel-close", "aria-label": "Close", click: closePanel }, "Close ✕"));
  const panelBody = h("div", { class: "node-panel-body" });
  panel.append(panelBody);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && panel.classList.contains("is-open")) closePanel(); });

  // Ranked against every OTHER point on today's map, so "215 events" becomes "busier than 80% of
  // what you're looking at" -- a comparison a non-technical reader can actually use. This uses only
  // data already on the client (no new pipeline field); it is a plain rank, computed once, not a
  // claim, so it does not need a Claim wrapper or evidence -- it is arithmetic on the visible map.
  const sorted = [...b.world.nodes].sort((x, y) => x.e - y.e);
  const rankOf = (id: number) => sorted.findIndex((x) => x.id === id);
  const plainKind = (n: WorldNode): string => {
    if (n.r > 0) return "put out a release";
    if (n.f > n.a) return "was forked by more people than it has contributors";
    if (n.p > 0 && n.p >= n.e * 0.3) return "was mostly pull requests being reviewed and merged";
    if (n.a === 1) return "had activity from a single account, so this may be one person's own project";
    return "had ordinary day-to-day activity: code pushed, issues discussed";
  };

  const show = (n: WorldNode) => {
    session.reposFollowed.add(n.n);
    world.setMode("focus", { focusId: n.id });
    const url = b.latest.synthetic ? null : safeRepoUrl(n.n);
    const rank = rankOf(n.id), pct = Math.round((rank / Math.max(1, sorted.length - 1)) * 100);
    const scaleLine = sorted.length > 1
      ? (pct >= 90 ? `Busier than ${pct}% of the repositories on today's map, one of the loudest here.`
        : pct <= 15 ? `Quieter than most repositories on today's map, one of the calmer ones here.`
        : `About in the middle of today's map, neither unusually loud nor unusually quiet.`)
      : "";
    fill(panelBody,
      h("p", { class: "kicker" }, `${fmt(n.e)} events on ${b.world.date}`),
      h("h3", {}, n.n),
      h("p", { class: "plain" }, `In plain terms: this repository ${plainKind(n)}. ${scaleLine}`),
      h("p", {}, `We recorded ${fmt(n.e)} public GitHub events from ${fmt(n.a)} account${n.a === 1 ? "" : "s"} that day.`),
      h("p", { class: "fine" }, `${fmt(n.f)} fork event${n.f === 1 ? "" : "s"} (someone copied it), ${fmt(n.p)} pull-request event${n.p === 1 ? "" : "s"} (a proposed code change), ${fmt(n.r)} release event${n.r === 1 ? "" : "s"} (a new published version).`),
      h("details", { class: "evidence", toggle: (e) => { if ((e.target as HTMLDetailsElement).open) session.evidenceOpened++; } }, h("summary", {}, "Show me the data"),
        h("dl", {}, ...([["source", `worlds/${b.world.date}.json`], ["repository id", String(n.id)], ["events", String(n.e)], ["accounts", String(n.a)], ["position", "a fixed function of the repository id: it carries no meaning"], ["brightness", "log of that day's events"]] as [string, string][]).flatMap(([k, v]) => [h("dt", {}, k), h("dd", {}, v)]))),
      url ? h("a", { class: "btn", href: url, rel: "noopener noreferrer", target: "_blank" }, "Open on GitHub ↗") : (b.latest.synthetic ? h("p", { class: "fine" }, "No link on demo data: these repository names are invented.") : null),
      h("p", { class: "fine" }, "We can see what happened. We can't see why."));
    panel.setAttribute("tabindex", "-1");
    panel.classList.add("is-open");
    panel.focus();
  };
  world.onPick = show;

  // heartbeat: real hourly totals for the day
  const hours = Array.from({ length: 24 }, (_, i) => b.hourly.hours.find((x) => x.h === i));
  const vals = hours.map((x) => x?.e ?? 0), labels = hours.map((_, i) => `${String(i).padStart(2, "0")}:00`);
  const readout = h("p", { class: "mono", "aria-live": "polite" });
  const stripHost = h("div", { class: "strip-host" });
  const setHour = (i: number) => {
    const x = hours[i];
    readout.textContent = x ? `${labels[i]} to ${String((i + 1) % 24).padStart(2, "0")}:00 UTC · ${fmt(x.e)} events · ${fmt(x.a)} accounts · ${fmt(x.r)} repositories` : `${labels[i]} UTC · no data`;
    fill(stripHost, barStrip(vals, labels, `Public GitHub events per hour on ${b.hourly.date} (UTC)`, i));
  };
  setHour(new Date().getUTCHours());
  const slider = h("input", { type: "range", min: 0, max: 23, value: new Date().getUTCHours(), "aria-label": "Hour of the day, UTC", input: (e) => setHour(Number((e.target as HTMLInputElement).value)) });

  return h("section", { id: "world", class: "chapter", "data-mode": "overview", "aria-label": "The World" }, panel,
    h("div", { class: "card card--wide" },
      h("p", { class: "kicker" }, "The World"),
      h("p", { class: "lead" }, `${fmt(b.world.nodes.length)} of yesterday's busiest repositories. Each point is one repository; brighter means more events that day. Tap any point, or any name in the list below, to open it.`),
      edgeNote(b.world.edges.length, b.latest.ledger_days),
      h("p", { class: "sr-only" }, "The map is a visual only. Every repository on it is also available as a button below."),
      h("h3", { class: "sub" }, "The day, hour by hour"), stripHost, slider, readout,
      pulseBlock(b),
      h("h3", { class: "sub" }, "Loudest yesterday"),
      h("ul", { class: "loud" }, ...[...b.world.nodes].sort((a, c) => c.e - a.e).slice(0, 10).map((n) =>
        h("li", {}, h("button", { type: "button", class: "linkish", click: () => show(n) }, n.n), h("span", { class: "mono" }, ` ${fmt(n.e)} events`))))));
}

function pulseBlock(b: Bundle): HTMLElement {
  const p = b.pulse;
  if (!p) return h("p", { class: "fine" }, "No live pulse has been published yet.");
  const head = p.status === "current" ? `Latest ${p.available_hours} complete hours (UTC ${p.window?.from.slice(11, 16)} to ${p.window?.to.slice(11, 16)})` : p.status === "partial" ? `PARTIAL: ${p.available_hours} of ${p.requested_hours} hours available; missing ${p.missing.join(", ")}` : "PULSE UNAVAILABLE: the latest hours could not be retrieved, and nothing here is estimated";
  return h("div", { class: "pulse" },
    h("h3", { class: "sub" }, "The pulse"), h("p", { class: "mono" }, head),
    p.window ? h("p", {}, `${fmt(p.window.events)} events in that window. Generated ${ago(p.generated_at)}. GH Archive publishes with a lag, so “now” here means a few hours ago.`) : null,
    p.loudest.length ? h("ul", { class: "loud" }, ...p.loudest.slice(0, 5).map((r) => h("li", {}, h("span", {}, r.repo), h("span", { class: "mono" }, ` ${fmt(r.events)} events from ${fmt(r.actors)} accounts · usually ${r.usual_per_day}/day`)))) : null);
}

// ---------------------------------------------------------------- story extras
function storyIntro(isToday: boolean): HTMLElement {
  return h("div", { class: "story-intro" }, h("p", { class: "fine" }, isToday ? "Today's story was chosen by the pipeline from every repository we observed. Nobody picked it by hand." : "From the archive. The map shows how the world looked that day, if we kept it."));
}
const REASONS = (held: string | null): string => {
  if (!held) return "";
  if (held.startsWith("warming_up")) {
    const [have, need] = (held.split(":")[1] ?? "").split("/");
    return `We have ${have} of the ${need} days of record we need before we can say what "normal" looks like for a repository. Until then we would rather say nothing than guess.`;
  }
  return "Something may have been loud, but nothing was both unusual enough and clearly not a script.";
};
function quietDay(b: Bundle, date: string): HTMLElement {
  // For the latest day the freshly published `latest.json` is the authority; the archive index is for past days.
  const held = date === b.latest.date ? b.latest.held_reason : (b.index.stories.find((r) => r.date === date)?.held_reason ?? null);
  const title = held?.startsWith("warming_up") ? "Still learning what normal looks like" : "Nothing crossed the line";
  return h("section", { class: "step", "data-mode": "silence" }, h("div", { class: "card" },
    h("p", { class: "kicker" }, date), h("p", { class: "word" }, title), h("p", {}, REASONS(held)),
    h("p", { class: "fine" }, "A day with no story is still a day. It is in the archive too.")));
}
function exitStep(b: Bundle, s: Story): HTMLElement {
  const other = b.pulse?.loudest.find((r) => r.repo !== s.repo);
  return h("section", { class: "step", "data-mode": "overview" }, h("div", { class: "card" },
    h("p", { class: "kicker" }, "While you were reading"),
    other && b.pulse && b.pulse.status !== "unavailable"
      ? h("p", {}, `Somewhere else, ${other.repo} recorded ${fmt(other.events)} events from ${fmt(other.actors)} accounts in the last few hours we can see. Its usual is ${other.usual_per_day} a day.`)
      : h("p", {}, "Something else moved too. The pulse for the latest hours isn't available right now, so we won't guess what."),
    h("p", { class: "fine" }, "We can see what happened. We can't see why. Public doesn't mean complete.")));
}

// ---------------------------------------------------------------- time machine
function timeSection(b: Bundle, world: WorldView): HTMLElement {
  const days = b.worldDays, hist = b.history.days;
  let idx = days.length - 1;
  const out = h("div", { class: "time-out", "aria-live": "polite" });
  const chartHost = h("div", {});
  const render = () => {
    const d = days[idx]!, row = hist.find((r) => r.date === d), hi = hist.findIndex((r) => r.date === d);
    fill(chartHost, lineChart(hist.map((r) => ({ d: r.date, v: r.events })), hi, `Public GitHub events per day, ${hist.length} days on record`));
    fill(out, h("p", { class: "word" }, d),
      row ? h("p", {}, `${fmt(row.events)} events across ${fmt(row.repos)} repositories. ${fmt(row.forks)} forks, ${fmt(row.prs)} pull-request events, ${fmt(row.issues)} issue events, ${fmt(row.stars)} stars.`) : h("p", {}, "No totals for this day."));
  };
  const slider = h("input", { type: "range", min: 0, max: Math.max(0, days.length - 1), value: idx, "aria-label": "Day to view", disabled: days.length < 2,
    input: async (e) => { idx = Number((e.target as HTMLInputElement).value); const d = days[idx]!; session.daysScrubbed.add(d); const w = await loadWorld(d); if (w) world.setWorld(w); render(); } });
  render();
  return h("section", { id: "time", class: "chapter", "data-mode": "overview", "aria-label": "Time machine" },
    h("div", { class: "card card--wide" },
      h("p", { class: "kicker" }, "Time"), h("p", { class: "lead" }, "Drag to move the World between days. The same repositories stay in the same places; only their brightness changes, and some appear or fade."),
      slider, out, chartHost,
      h("p", { class: "fine" }, `Honest depth: we keep ${days.length} day${days.length === 1 ? "" : "s"} of worlds and ${b.latest.ledger_days} day${b.latest.ledger_days === 1 ? "" : "s"} of totals. The record starts the day the pipeline first ran, and grows by one day each day. We don't pretend to have 2011.`)));
}

// ---------------------------------------------------------------- graveyard
function graveSection(b: Bundle): HTMLElement {
  const rows = b.graveyard.rows, need = Number(b.method["graveyard_min_silent_days"] ?? 90);
  const detail = h("div", { class: "grave-detail", "aria-live": "polite" });
  const pick = (r: GraveRow) => {
    session.graveyardViewed.add(r.repo);
    fill(detail, h("h3", {}, r.repo), h("ol", { class: "vline" },
      h("li", {}, h("strong", {}, r.first_day), " first seen in our record"),
      h("li", {}, h("strong", {}, r.peak_day), ` busiest day we saw: ${fmt(r.peak_events)} events`),
      h("li", {}, `${fmt(r.active_days)} days with public activity, ${fmt(r.total_events)} events in all`),
      h("li", {}, h("strong", {}, r.last_day), " last public event we observed"),
      h("li", { class: "vline-end" }, `Since then: ${fmt(r.silent_days)} days with none.`)),
      h("p", { class: "fine" }, "We can't tell why it went quiet. It may be finished, moved, private, or resting. Public doesn't mean complete."));
  };
  return h("section", { id: "graveyard", class: "chapter", "data-mode": "graveyard", "aria-label": "The Graveyard" },
    h("div", { class: "card card--wide" }, h("p", { class: "kicker" }, "The Graveyard"),
      rows.length
        ? [h("p", { class: "lead" }, `Repositories that were once busy in our record and have shown no public activity for at least ${need} days.`), h("ul", { class: "loud" }, ...rows.slice(0, 12).map((r) => h("li", {}, h("button", { type: "button", class: "linkish", click: () => pick(r) }, r.repo), h("span", { class: "mono" }, ` ${fmt(r.silent_days)} days quiet`)))), detail]
        : [h("p", { class: "word" }, "Nothing here yet."), h("p", {}, `A repository has to be quiet for ${need} days before we call it quiet. We have ${b.latest.ledger_days} day${b.latest.ledger_days === 1 ? "" : "s"} of record, so this place opens in about ${Math.max(0, need - b.latest.ledger_days)} days. Silence has to be measured; it can't be assumed.`)]));
}

// ---------------------------------------------------------------- archive
function archiveSection(b: Bundle, open: (d: string) => void): HTMLElement {
  const label = (r: StoryIndexRow) => new Date(r.date + "T00:00:00Z").toLocaleDateString([], { month: "short", day: "numeric", timeZone: "UTC" }).toUpperCase();
  return h("section", { id: "archive", class: "chapter", "data-mode": "overview", "aria-label": "Archive" },
    h("div", { class: "card card--wide" }, h("p", { class: "kicker" }, "The internet's memory"),
      h("p", { class: "lead" }, "Every day gets an entry, including the days when nothing crossed the line. Six months from now this page is the record of what the pipeline found."),
      h("ol", { class: "archive" }, ...b.index.stories.map((r) => h("li", {},
        h("span", { class: "mono" }, label(r)),
        r.id ? h("button", { type: "button", class: "linkish", click: () => open(r.date) }, r.title) : h("span", { class: "muted" }, r.title),
        h("span", { class: "muted" }, r.repo ? ` · ${r.repo}` : "")))) ));
}

// ---------------------------------------------------------------- method
function methodSection(b: Bundle): HTMLElement {
  const m = b.method, s = b.status;
  const kv = (rows: [string, string][]) => h("dl", { class: "kv" }, ...rows.flatMap(([k, v]) => [h("dt", {}, k), h("dd", {}, v)]));
  return h("section", { id: "method", class: "chapter", "data-mode": "overview", "aria-label": "Methodology" },
    h("div", { class: "card card--wide" }, h("p", { class: "kicker" }, "Method"),
      h("h3", { class: "sub" }, "Where it comes from"), h("p", {}, "GH Archive: hourly files of public GitHub events. A day is published only when all 24 hours are present and intact; otherwise the previous day stays up and says so."),
      h("h3", { class: "sub" }, "What is counted"), h("p", {}, "Events, not commits. In October 2025 GitHub removed commit summaries and pull-request merge details from the public event payloads, so a sentence like “96 commits” or “merged” can no longer be supported, and the pipeline refuses to write one."),
      h("h3", { class: "sub" }, "What is not counted"), h("p", {}, "Private repositories, work that never reaches GitHub, and everything a person is or feels. GitHub is one window into the internet, not the internet."),
      h("h3", { class: "sub" }, "Four kinds of sentence"),
      kv([["Observed", "counted directly in the event stream"], ["Derived", "arithmetic on observed counts (ratios, gaps, percentiles)"], ["Our reading", "restrained pattern language, always marked as ours"], ["We can't see", "what the stream cannot establish: who, why, quality, place, private work"]]),
      h("h3", { class: "sub" }, "How a story is found"),
      h("p", {}, "Usual = the mean over the days we actually observed (silent days count as zero; days before our record are unknown, never zero). Then:"),
      kv([["Growth", `at least ${m["min_fold"]}× usual, at least ${m["min_absolute_excess"]} events above it, and above the ${(Number(m["min_percentile"]) * 100).toFixed(1)}th percentile of repositories of similar size that day`],
          ["Resurrection", `at least ${m["resurrection_min_silent_days"]} observed-silent days after at least ${m["resurrection_min_prior_active_days"]} active days, then ${m["resurrection_min_events_today"]}+ events`],
          ["Graveyard", `peak of ${m["graveyard_min_peak_events"]}+ events, then ${m["graveyard_min_silent_days"]}+ days with none`],
          ["Fork burst", `${m["fork_min_forks"]}+ forks in a day and ${m["fork_min_fold"]}× the usual`],
          ["Needs", `${m["min_events_today"]}+ events from ${m["min_distinct_actors_today"]}+ accounts, and ${m["ledger_min_coverage_days"]}+ days of record before we judge anything`],
          ["Automation", `set aside as “not a human moment” if one account made ${(Number(m["max_top_actor_share"]) * 100).toFixed(0)}%+ of a repository's events or every account name looks automated. Bots are real activity, so they are recorded, just not the story of the day.`]]),
      h("p", { class: "fine" }, "Which story wins is an editorial priority (novelty, size, evidence, how human it looks) with a penalty for repeating a recent kind. It is never shown as a rating, and it does not mean “best project”."),
      h("h3", { class: "sub" }, "Status of the last update"),
      kv([["Source day", s.source_date], ["Archive hours", s.hours], ["Events", fmt(s.events)], ["Lines rejected", `${fmt(s.rejected_lines)} (${(s.reject_rate * 100).toFixed(3)}%; a day above 1% is not published)`],
          ["Repository-creation events seen", `${fmt(s.birth_signal.repo_create_events)}, ${s.birth_signal.birth_signal_present ? "so we can name repositories as created" : "none, so we only say “first seen in our record”"}`],
          ["Days of record", String(s.ledger_days)], ["Pipeline", `${s.pipeline_version} / engine ${s.engine_version}`], ["Data", b.latest.synthetic ? "SYNTHETIC DEMO" : "GH Archive"]]),
      h("details", { class: "evidence" }, h("summary", {}, "Source files and fingerprints"),
        h("ul", { class: "files" }, ...b.provenance.files.map((f) => h("li", {}, h("code", {}, `${b.latest.date}-${f.hour}.json.gz`), `: ${fmt(f.bytes)} bytes · sha256 ${f.sha256.slice(0, 16)}…`))))));
}

// ---------------------------------------------------------------- epilogue
function epilogue(b: Bundle): HTMLElement {
  return h("section", { id: "epilogue", class: "chapter epilogue", "data-mode": "silence", "aria-label": "Closing" }, h("div", { class: "epilogue-inner", "aria-live": "polite", id: "epi" }));
}
function renderEpilogue(b: Bundle) {
  const next = nextDailyUpdate();
  const when = next.toLocaleString([], { weekday: "short", hour: "2-digit", minute: "2-digit" });
  // The time itself is real (converted from 05:17 UTC to the visitor's own clock). Whether it
  // actually happens depends on whether this site's GitHub Actions workflow is deployed and
  // enabled; a local checkout with no workflow running will never update on its own, so we say
  // that plainly instead of implying an automation that may not exist yet.
  fill($("#epi"), 
    ...session.lines(b.latest.events, b.latest.date).map((l) => h("p", { class: "epi-line" }, l)),
    h("p", { class: "epi-line" }, "Tomorrow there will be more, if the daily update is running."),
    h("p", { class: "word" }, "Somewhere, something is being built."),
    h("p", { class: "fine" }, `The scheduled update runs at 05:17 UTC (${when} your time), only when this site's GitHub Actions workflow is deployed and enabled. A local checkout with no workflow running updates only when you run the pipeline yourself.`));
}
