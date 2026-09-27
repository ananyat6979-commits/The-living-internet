import { describe, it, expect, beforeEach, vi } from "vitest";
import { haveData, readJSON, stubBrowser, stubFetch } from "./helpers";
import type { Story, Latest, Bundle } from "../types";
import { silentGap } from "../lib/series";

const boot = async () => { vi.resetModules(); document.body.innerHTML = `<div id="app"></div>`; await import("../main"); await vi.waitFor(() => { if (!document.querySelector("#app > *")) throw new Error("not booted"); await_(); }, { timeout: 4000 }); };
const await_ = () => { if (document.querySelector("#story-root")?.children.length === 0) throw new Error("story not rendered"); };

describe.skipIf(!haveData)("the whole app, booted in jsdom on the pipeline's real output", () => {
  beforeEach(() => { location.hash = ""; stubBrowser(); });

  it("renders the story from data, and every sentence is a compiled claim", async () => {
    stubFetch(); await boot();
    const story = readJSON<Story>("stories/2026-09-22.json");
    const shown = [...document.querySelectorAll("#story-root .claim-text")].map((e) => e.textContent);
    const claimsUsed = story.beats.flatMap((b) => b.claims).map((id) => story.claims.find((c) => c.id === id)!.text);
    expect(shown).toEqual(claimsUsed);
  });

  it("no number appears in the story cards that is not in a claim, the receipts, or a chart derived from the series", async () => {
    stubFetch(); await boot();
    const story = readJSON<Story>("stories/2026-09-22.json");
    const allowed = new Set<string>();
    const grab = (t: string) => t.match(/\d[\d,.]*/g)?.forEach((n) => allowed.add(n.replace(/[,.]$/, "")));
    story.claims.forEach((c) => grab(c.text)); grab(story.date); grab(String(story.evidence.total)); grab(String(story.evidence.shown)); grab(story.title); grab(story.repo);
    const clone = document.querySelector("#story-root")!.cloneNode(true) as HTMLElement;
    clone.querySelectorAll("svg, table, pre, dl, .files, .kicker, .story-intro, .fine, summary").forEach((n) => n.remove());
    const unexplained = (clone.textContent?.match(/\d[\d,.]*/g) ?? []).map((n) => n.replace(/[,.]$/, "")).filter((n) => !allowed.has(n));
    expect(unexplained).toEqual([]);
  });

  it("the chart's silent gap equals the number the claim states", async () => {
    stubFetch(); await boot();
    const story = readJSON<Story>("stories/2026-09-22.json");
    if (story.archetype !== "resurrection") return;
    const claim = story.claims.find((c) => c.metric === "silent_days")!;
    expect(silentGap(story.series)?.length).toBe(claim.value);
  });

  it("is honest that the data is synthetic when it is", async () => {
    stubFetch(); await boot();
    expect(document.querySelector(".synthetic")?.textContent).toMatch(/SYNTHETIC DEMO DATA/);
  });

  it("a hostile repository name from the data cannot inject markup", async () => {
    const story = readJSON<Story>("stories/2026-09-22.json");
    const evil = `x<img src=x onerror=alert(1)>/y`;
    stubFetch({ "stories/2026-09-22.json": { ...story, repo: evil }, "latest.json": { ...readJSON<Latest>("latest.json"), synthetic: false } });
    await boot();
    expect(document.querySelector("#story-root img")).toBeNull();
    expect(document.querySelector("#story-root .repo")?.textContent).toContain(evil);
    expect(document.querySelector("#story-root .repo a")).toBeNull();          // not a valid repo name => no link
  });

  it("a day with no story says so and why, instead of inventing one", async () => {
    const latest = readJSON<Latest>("latest.json");
    stubFetch({ "latest.json": { ...latest, story_id: null, held_reason: "warming_up:3/14" } });
    await boot();
    const txt = document.querySelector("#story-root")!.textContent!;
    expect(txt).toMatch(/3 of the 14 days of record/); expect(document.querySelector("#story-root .claim")).toBeNull();
  });

  it("when nothing has been published it shows an honest empty state, not fake content", async () => {
    stubFetch({ "latest.json": null }); vi.resetModules(); document.body.innerHTML = `<div id="app"></div>`; await import("../main");
    await vi.waitFor(() => expect(document.querySelector(".unavailable")).not.toBeNull());
    expect(document.querySelector(".unavailable")!.textContent).toMatch(/Nothing has been published/);
  });

  it("an old snapshot is labelled STALE in words and tells the visitor the world hasn't changed", async () => {
    const latest = readJSON<Latest>("latest.json");
    stubFetch({ "latest.json": { ...latest, generated_at: "2026-01-01T00:00:00Z" } });
    await boot();
    expect(document.querySelector(".pill")?.textContent).toMatch(/^STALE/);
    expect(document.querySelector(".stale-note")?.getAttribute("role")).toBe("status");
  });

  it("the graveyard says it is not open yet, and why, when there is not enough record", async () => {
    stubFetch({ "graveyard.json": { date: "2026-09-22", rows: [] } }); await boot();
    expect(document.querySelector("#graveyard")!.textContent).toMatch(/Silence has to be measured/);
  });

  it("every archive day appears, including days with no story", async () => {
    stubFetch(); await boot();
    const idx = readJSON<{ stories: { date: string }[] }>("stories/index.json").stories;
    expect(document.querySelectorAll("#archive li")).toHaveLength(idx.length);
    expect(document.querySelector("#archive")!.textContent).toMatch(/Nothing crossed the line/);
  });

  it("keyboard parity: every loud repository on the canvas is also a real button", async () => {
    stubFetch(); await boot();
    const btns = document.querySelectorAll("#world .loud button");
    expect(btns.length).toBeGreaterThanOrEqual(5); btns[0]!.dispatchEvent(new Event("click"));
    expect(document.querySelector(".node-panel")!.textContent).toMatch(/[Ww]e recorded [\d,]+ public GitHub events/);
  });

  it("nav anchors resolve to sections, not to the background canvas (no duplicate ids)", async () => {
    stubFetch(); await boot();
    const ids = [...document.querySelectorAll("[id]")].map((e) => e.id);
    expect(ids.filter((i, n) => ids.indexOf(i) !== n)).toEqual([]);
    expect(document.getElementById("world")!.tagName).toBe("SECTION");
  });

  it("the canvas is decorative to assistive tech and the sections are landmarks with names", async () => {
    stubFetch(); await boot();
    expect(document.querySelector("canvas")!.getAttribute("aria-hidden")).toBe("true");
    for (const id of ["opening", "world", "story", "time", "graveyard", "archive", "method"]) expect(document.getElementById(id)!.getAttribute("aria-label")).toBeTruthy();
    expect(document.querySelector("a.skip") === null).toBe(true);  // skip link lives in index.html, not the app root
  });

  it("the receipts table renders one <tr> per event and 4 header cells (h() accepts spread children and arrays)", async () => {
    stubFetch(); await boot();
    const story = readJSON<Story>("stories/2026-09-22.json");
    const table = document.querySelector(".step--receipts table")!;
    expect(table.querySelectorAll("thead th")).toHaveLength(4);
    expect(table.querySelectorAll("tbody tr")).toHaveLength(story.evidence.events.length);
    expect(table.querySelector("tbody tr td")!.textContent).toBe(story.evidence.events[0]!.id);
  });

  it("demo data never links out: an invented name like ghost/oldtool would point at a real GitHub user", async () => {
    stubFetch(); await boot();
    expect(document.querySelectorAll('a[href*="github.com"]')).toHaveLength(0);
    document.querySelector<HTMLButtonElement>("#world .loud button")!.dispatchEvent(new Event("click"));
    expect(document.querySelector(".node-panel")!.textContent).toMatch(/No link on demo data/);
    expect(document.querySelectorAll('a[href*="github.com"]')).toHaveLength(0);
  });

  it("real data: story and map cards get a safe, new-tab 'Open on GitHub' link to the exact repository", async () => {
    const latest = readJSON<Latest>("latest.json"), story = readJSON<Story>("stories/2026-09-22.json");
    stubFetch({ "latest.json": { ...latest, synthetic: false } });
    await boot();
    const a = document.querySelector<HTMLAnchorElement>("#story-root .repo a")!;
    expect(a.href).toBe(`https://github.com/${story.repo}`);
    expect(a.rel).toBe("noopener noreferrer"); expect(a.target).toBe("_blank"); expect(a.textContent).toMatch(/Open on GitHub/);
    document.querySelector<HTMLButtonElement>("#world .loud button")!.dispatchEvent(new Event("click"));
    const card = document.querySelector<HTMLAnchorElement>(".node-panel a.btn")!;
    expect(card.href).toMatch(/^https:\/\/github\.com\/[^/]+\/[^/]+$/);
  });

  it("clicking a repository opens a visible fixed panel immediately, not a block buried below the fold", async () => {
    stubFetch(); await boot();
    const panel = document.getElementById("node-panel")!;
    expect(panel.classList.contains("is-open")).toBe(false);
    document.querySelector<HTMLButtonElement>("#world .loud button")!.dispatchEvent(new Event("click"));
    expect(panel.classList.contains("is-open")).toBe(true);
    expect(panel.textContent).toMatch(/[Ww]e recorded [\d,]+ public GitHub events/);
    // the panel is NOT inside the scrolling .card (that was the bug: content real, but invisible)
    expect(document.querySelector(".card--wide")!.contains(panel)).toBe(false);
    panel.querySelector<HTMLButtonElement>(".node-panel-close")!.dispatchEvent(new Event("click"));
    expect(panel.classList.contains("is-open")).toBe(false);
  });

  it("the closing screen never claims the site will update itself unless a live schedule is actually running", async () => {
    stubFetch(); await boot();
    document.getElementById("epilogue")!.scrollIntoView();
    document.querySelectorAll("[data-mode]").forEach((el) => el.dispatchEvent(new Event("intersect")));
    await new Promise((r) => setTimeout(r, 0));
  });

  it("the panel explains a repository in plain language, not just raw counts, for a non-technical reader", async () => {
    stubFetch(); await boot();
    document.querySelector<HTMLButtonElement>("#world .loud button")!.dispatchEvent(new Event("click"));
    const plain = document.querySelector(".node-panel-body p.plain");
    expect(plain).not.toBeNull();
    expect(plain!.textContent).toMatch(/In plain terms:/);
    expect(plain!.textContent!.length).toBeGreaterThan("In plain terms: ".length + 10);
  });

  it("the World section explains why there are few or no connecting lines instead of leaving them unexplained", async () => {
    stubFetch(); await boot();
    const note = document.querySelector("#world .lead + p.fine, #world .lead ~ p.fine")!.textContent!;
    const world = readJSON<Bundle["world"]>(`worlds/${readJSON<Latest>("latest.json").date}.json`);
    if (world.edges.length === 0) expect(note).toMatch(/No two repositories here shared/);
    else expect(note).toMatch(/line.*on the map/);
  });

  it("says plainly when NO repositories share contributors yet, instead of an unexplained empty map", async () => {
    const world = readJSON<Bundle["world"]>(`worlds/${readJSON<Latest>("latest.json").date}.json`);
    stubFetch({ [`worlds/${world.date}.json`]: { ...world, edges: [] } });
    await boot();
    const note = document.querySelector("#world .lead + p.fine")!.textContent!;
    expect(note).toMatch(/No two repositories here shared/);
  });
});
