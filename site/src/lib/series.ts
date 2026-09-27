import type { SeriesPt } from "../types";

/** The silent stretch immediately before the last point ("today"): consecutive OBSERVED zero days.
 *  `complete` is false if we ran out of record before finding the last active day (then it is a lower bound). */
export interface Gap { length: number; priorIdx: number; complete: boolean; }
export function silentGap(series: SeriesPt[]): Gap | null {
  const last = series.length - 1;
  if (last < 1) return null;
  let n = 0;
  for (let i = last - 1; i >= 0; i--) {
    const p = series[i];
    if (!p || p.e === null) return { length: n, priorIdx: -1, complete: false };
    if (p.e > 0) return { length: n, priorIdx: i, complete: true };
    n++;
  }
  return { length: n, priorIdx: -1, complete: false };
}

/** Mean events/day over up to `window` observed days before the last point. Unobserved (null) days are excluded,
 *  observed silent days count as 0, the same rule the pipeline uses. */
export function observedMean(series: SeriesPt[], window = 28): { mean: number; days: number } {
  const prior = series.slice(0, -1).filter((p): p is { d: string; e: number } => p.e !== null).slice(-window);
  const days = prior.length;
  return { mean: days ? prior.reduce((a, p) => a + p.e, 0) / days : 0, days };
}

export type Role = "past" | "gap" | "today" | "unknown";
export function roles(series: SeriesPt[]): Role[] {
  const gap = silentGap(series);
  return series.map((p, i) => {
    if (i === series.length - 1) return "today";
    if (p.e === null) return "unknown";
    if (gap && gap.length > 0 && i > gap.priorIdx && p.e === 0) return "gap";
    return "past";
  });
}
