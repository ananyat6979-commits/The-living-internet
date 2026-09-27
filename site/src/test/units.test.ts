import { describe, it, expect } from "vitest";
import { silentGap, observedMean, roles } from "../lib/series";
import { safeRepoUrl, freshness } from "../lib/data";
import { notesForBeat, densityFor } from "../lib/audio";
import { Session, nextDailyUpdate } from "../lib/session";
import { mulberry32, seedFrom } from "../lib/rng";
import { h } from "../lib/dom";
import type { SeriesPt } from "../types";

const S = (...e: (number | null)[]): SeriesPt[] => e.map((v, i) => ({ d: `d${i}`, e: v }));

describe("silence is measured, not assumed", () => {
  it("counts consecutive OBSERVED zero days before today", () => expect(silentGap(S(5, 7, 0, 0, 0, 0, 9))).toEqual({ length: 4, priorIdx: 1, complete: true }));
  it("reports a lower bound when the record starts mid-silence (null = unknown, not zero)", () => expect(silentGap(S(null, null, 0, 0, 9))).toEqual({ length: 2, priorIdx: -1, complete: false }));
  it("no gap when yesterday was active", () => expect(silentGap(S(0, 4, 9))?.length).toBe(0));
  it("baseline excludes unknown days and counts silent days as zero", () => expect(observedMean(S(null, null, 10, 0, 0, 10, 99))).toEqual({ mean: 5, days: 4 }));
  it("roles mark the gap, past, unknown and today", () => expect(roles(S(null, 5, 0, 0, 9))).toEqual(["unknown", "past", "gap", "gap", "today"]));
});

describe("safety", () => {
  it("h() never interprets data as HTML", () => {
    const evil = `<img src=x onerror="window.__pwned=1"><script>window.__pwned=1</script>`;
    const el = h("p", {}, evil);
    expect(el.querySelector("img,script")).toBeNull();
    expect(el.textContent).toBe(evil);
  });
  it("only real GitHub owner/repo names become links", () => {
    expect(safeRepoUrl("acme/rocket")).toBe("https://github.com/acme/rocket");
    for (const bad of ["javascript:alert(1)", "a/b/c", "../x", "a b/c", "x/<y>", "https://evil.com/a", ""]) expect(safeRepoUrl(bad)).toBeNull();
  });
  it("staleness is stated in words", () => {
    expect(freshness("2026-09-23T05:00:00Z", Date.parse("2026-09-23T09:00:00Z")).state).toBe("current");
    const s = freshness("2026-09-20T05:00:00Z", Date.parse("2026-09-23T09:00:00Z"));
    expect(s.state).toBe("stale"); expect(s.label).toMatch(/^STALE/);
  });
});

describe("audio and session are grounded in real counts", () => {
  it("a quiet hour is silent, a peak hour is fullest, and it never decreases with activity", () => {
    expect(notesForBeat(0.05)).toBe(0); expect(notesForBeat(1)).toBe(3);
    let prev = 0; for (let d = 0; d <= 1; d += 0.05) { const n = notesForBeat(d); expect(n).toBeGreaterThanOrEqual(prev); prev = n; }
  });
  it("density is relative to the day's own peak", () => expect(densityFor([10, 20, 5])).toEqual([0.5, 1, 0.25]));
  it("the closing screen omits things the visitor did not do instead of reporting zeros", () => {
    const s = new Session(); const l = s.lines(1000, "2026-09-22", s.startedAt + 5000);
    expect(l).toHaveLength(1); expect(l[0]).toContain("under a minute"); expect(l[0]).toContain("1,000");
    s.evidenceOpened = 3; s.storiesOpened.add("x");
    expect(s.lines(1000, "d").join(" ")).toMatch(/1 story.*3 times/);
  });
  it("next update is the next 05:17 UTC", () => {
    expect(nextDailyUpdate(new Date("2026-09-23T04:00:00Z")).toISOString()).toBe("2026-09-23T05:17:00.000Z");
    expect(nextDailyUpdate(new Date("2026-09-23T06:00:00Z")).toISOString()).toBe("2026-09-24T05:17:00.000Z");
  });
  it("atmosphere randomness is reproducible", () => { const a = mulberry32(seedFrom("x")), b = mulberry32(seedFrom("x")); expect([a(), a()]).toEqual([b(), b()]); });
});
