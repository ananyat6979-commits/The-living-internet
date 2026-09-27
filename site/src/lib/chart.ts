import { s } from "./dom";
import type { SeriesPt } from "../types";
import { observedMean, roles, silentGap } from "./series";

export type Highlight = "none" | "all" | "past" | "gap" | "today" | "baseline";

/** Bars = observed daily events. A small tick = observed zero. Blank hatched region = before our record (unknown). */
export function seriesChart(series: SeriesPt[], label: string): SVGSVGElement {
  const W = 640, H = 150, pad = 10, n = series.length;
  const max = Math.max(1, ...series.map((p) => p.e ?? 0));
  const bw = (W - pad * 2) / n;
  const rs = roles(series);
  const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": label, class: "chart", "data-highlight": "none", preserveAspectRatio: "none" });
  svg.append(s("title", {}, label));
  const firstObs = series.findIndex((p) => p.e !== null);
  if (firstObs > 0) {
    svg.append(s("rect", { x: pad, y: 6, width: firstObs * bw, height: H - 22, class: "unknown-zone" }));
    svg.append(s("text", { x: pad + 6, y: 24, class: "chart-note" }, "before our record"));
  }
  const gap = silentGap(series);
  if (gap && gap.length > 0 && gap.complete) {
    svg.append(s("rect", { x: pad + (gap.priorIdx + 1) * bw, y: 6, width: gap.length * bw, height: H - 22, class: "gap-band" }));
    svg.append(s("text", { x: pad + (gap.priorIdx + 1 + gap.length / 2) * bw, y: 22, class: "chart-note gap-note", "text-anchor": "middle" }, `${gap.length} days with none we observed`));
  }
  series.forEach((p, i) => {
    const x = pad + i * bw, role = rs[i] ?? "past";
    if (p.e === null) return;
    if (p.e === 0) { svg.append(s("rect", { x, y: H - 16, width: Math.max(1, bw * 0.8), height: 1.5, class: `bar zero`, "data-role": role })); return; }
    const bh = Math.max(1.5, (p.e / max) * (H - 30));
    svg.append(s("rect", { x, y: H - 16 - bh, width: Math.max(1, bw * 0.8), height: bh, class: "bar", "data-role": role, "data-day": p.d, "data-e": p.e }));
  });
  const { mean, days } = observedMean(series);
  if (days > 0) {
    const y = H - 16 - (mean / max) * (H - 30);
    svg.append(s("line", { x1: pad, x2: W - pad, y1: y, y2: y, class: "baseline" }));
    svg.append(s("text", { x: W - pad, y: Math.max(12, y - 4), class: "chart-note baseline-note", "text-anchor": "end" }, `usual ≈ ${mean.toFixed(1)}/day`));
  }
  svg.append(s("line", { x1: pad, x2: W - pad, y1: H - 15, y2: H - 15, class: "axis" }));
  const last = series[series.length - 1], first = series[Math.max(0, firstObs)];
  if (first) svg.append(s("text", { x: pad + Math.max(0, firstObs) * bw, y: H - 3, class: "chart-note" }, first.d));
  if (last) svg.append(s("text", { x: W - pad, y: H - 3, class: "chart-note", "text-anchor": "end" }, last.d));
  return svg;
}

/** A tiny bar strip (used for hourly heartbeat). */
export function barStrip(values: number[], labels: string[], label: string, selected: number | null): SVGSVGElement {
  const W = 480, H = 64, n = values.length, max = Math.max(1, ...values), bw = W / n;
  const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": label, class: "strip", preserveAspectRatio: "none" });
  svg.append(s("title", {}, label));
  values.forEach((v, i) => svg.append(s("rect", { x: i * bw + 1, y: H - 4 - (v / max) * (H - 10), width: Math.max(1, bw - 2), height: Math.max(1, (v / max) * (H - 10)),
    class: `strip-bar${selected === i ? " is-selected" : ""}`, "data-label": labels[i] ?? "" })));
  return svg;
}

export function lineChart(points: { d: string; v: number }[], selectedIdx: number, label: string): SVGSVGElement {
  const W = 640, H = 120, pad = 10, n = points.length;
  const max = Math.max(1, ...points.map((p) => p.v)), min = Math.min(...points.map((p) => p.v), max);
  const lo = Math.max(0, min * 0.9), span = Math.max(1, max - lo);
  const xy = (i: number, v: number) => [pad + (n <= 1 ? (W - 2 * pad) / 2 : (i / (n - 1)) * (W - 2 * pad)), H - 14 - ((v - lo) / span) * (H - 28)] as const;
  const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": label, class: "line", preserveAspectRatio: "none" });
  svg.append(s("title", {}, label));
  const d = points.map((p, i) => { const [x, y] = xy(i, p.v); return `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`; }).join(" ");
  svg.append(s("path", { d, class: "line-path", fill: "none" }));
  const sel = points[selectedIdx];
  if (sel) { const [x, y] = xy(selectedIdx, sel.v); svg.append(s("line", { x1: x, x2: x, y1: 4, y2: H - 14, class: "line-marker" })); svg.append(s("circle", { cx: x, cy: y, r: 4, class: "line-dot" })); }
  return svg;
}
