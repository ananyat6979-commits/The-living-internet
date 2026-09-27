import type { World, WorldNode } from "../types";
import { mulberry32, seedFrom } from "./rng";

/** The World is ONE persistent canvas. Chapters do not replace it; they move its camera and change
 *  its `mode`. Semantic encoding (never random):
 *    position   = stable hash of repo id (in the data file)
 *    brightness = that day's events for the repo, log-scaled
 *    edges      = only edges present in the data (≥2 shared non-automated accounts)
 *  Atmosphere (twinkle/drift phase) uses a seeded PRNG keyed by repo id, so it is reproducible. */

export type Mode = "overview" | "focus" | "silence" | "reignite" | "graveyard" | "fork";

interface Cam { x: number; y: number; k: number; }
const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
const clamp = (v: number, a: number, b: number) => Math.max(a, Math.min(b, v));
const ease = (t: number) => t * t * (3 - 2 * t);

export class WorldView {
  private ctx: CanvasRenderingContext2D;
  private w = 1; private h = 1; private dpr = 1;
  private cam: Cam = { x: 0, y: 0, k: 1 };
  private target: Cam = { x: 0, y: 0, k: 1 };
  private nodes: WorldNode[] = [];
  private phase = new Map<number, number>();
  private byId = new Map<number, WorldNode>();
  private maxLog = 1;
  private focusId: number | null = null;
  private mode: Mode = "overview";
  private modeT = 1;               // 0..1 progress of the current mode's transition
  private modeStart = 0;
  private raf = 0; private running = false;
  reducedMotion = false;
  onPick: ((n: WorldNode) => void) | null = null;
  private edges: World["edges"] = [];
  private fadeOthers = 1;          // 1 = full field, ~0.12 = only focus visible
  private silence = 0;             // 0..1 how "quiet" the world is drawn
  private forkKids: { a: number; r: number; d: number }[] = [];
  private prevLog = new Map<number, number>();
  private ghosts: { n: WorldNode; lg: number }[] = [];
  private blendStart = 0; private blendT = 1;

  constructor(private canvas: HTMLCanvasElement) {
    const c = canvas.getContext("2d", { alpha: true });
    if (!c) throw new Error("2D canvas unavailable");
    this.ctx = c;
    this.resize();
    new ResizeObserver(() => this.resize()).observe(canvas.parentElement ?? canvas);
    canvas.addEventListener("pointerdown", (e) => this.pick(e));
  }

  nodeById(id: number): WorldNode | undefined { return this.byId.get(id); }
  get nodeCount(): number { return this.nodes.length; }

  setWorld(world: World) {
    // remember how bright everything WAS, so time travel is a continuous change, not a redraw
    this.prevLog = new Map(this.nodes.map((n) => [n.id, Math.log1p(n.e) / this.maxLog]));
    const incoming = new Set(world.nodes.map((n) => n.id));
    this.ghosts = this.nodes.filter((n) => !incoming.has(n.id)).map((n) => ({ n, lg: Math.log1p(n.e) / this.maxLog }));
    this.blendStart = performance.now(); this.blendT = this.reducedMotion || this.nodes.length === 0 ? 1 : 0;
    this.nodes = world.nodes; this.edges = world.edges;
    this.byId.clear(); this.phase.clear();
    let m = 1;
    for (const n of this.nodes) {
      this.byId.set(n.id, n);
      this.phase.set(n.id, mulberry32(seedFrom(`${world.date}:${n.id}`))() * Math.PI * 2);
      m = Math.max(m, Math.log1p(n.e));
    }
    this.maxLog = m;
    this.draw(performance.now());
  }

  private resize() {
    const p = this.canvas.parentElement ?? this.canvas;
    const r = p.getBoundingClientRect();
    this.dpr = Math.min(2, window.devicePixelRatio || 1);
    this.w = Math.max(1, r.width); this.h = Math.max(1, r.height);
    this.canvas.width = Math.round(this.w * this.dpr); this.canvas.height = Math.round(this.h * this.dpr);
    this.canvas.style.width = `${this.w}px`; this.canvas.style.height = `${this.h}px`;
    this.draw(performance.now());
  }

  /** Scene control used by the scroll director. */
  setMode(mode: Mode, opts: { focusId?: number | null; zoom?: number } = {}) {
    this.mode = mode; this.modeStart = performance.now(); this.modeT = this.reducedMotion ? 1 : 0;
    if ("focusId" in opts) this.focusId = opts.focusId ?? null;
    const f = this.focusId != null ? this.byId.get(this.focusId) : undefined;
    const scale = Math.min(this.w, this.h) * 0.46;
    if (f && mode !== "overview") {
      this.target = { x: -f.x * scale * (opts.zoom ?? 2.6), y: -f.y * scale * (opts.zoom ?? 2.6), k: opts.zoom ?? 2.6 };
    } else this.target = { x: 0, y: 0, k: 1 };
    this.fadeOthers = mode === "overview" ? 1 : mode === "graveyard" ? 0.35 : 0.1;
    this.silence = mode === "silence" || mode === "graveyard" ? 1 : 0;
    if (mode === "fork" && f) {
      const kids = Math.min(48, Math.max(6, Math.round(f.f * 1.2 || 12)));
      const rnd = mulberry32(seedFrom(`fork:${f.id}`));
      this.forkKids = Array.from({ length: kids }, (_, i) => ({ a: (i / kids) * Math.PI * 2 + rnd() * 0.2, r: 0.05 + rnd() * 0.06, d: rnd() }));
    }
    if (this.reducedMotion) { this.cam = { ...this.target }; this.draw(performance.now()); }
    else this.start();
  }

  start() { if (this.running) return; this.running = true; const loop = (t: number) => { if (!this.running) return; this.draw(t); this.raf = requestAnimationFrame(loop); }; this.raf = requestAnimationFrame(loop); }
  stop() { this.running = false; cancelAnimationFrame(this.raf); }

  private project(n: { x: number; y: number }) {
    const s = Math.min(this.w, this.h) * 0.46;
    return { x: this.w / 2 + this.cam.x + n.x * s * this.cam.k, y: this.h / 2 + this.cam.y + n.y * s * this.cam.k };
  }

  private pick(e: PointerEvent) {
    if (!this.onPick) return;
    const rect = this.canvas.getBoundingClientRect();
    const px = e.clientX - rect.left, py = e.clientY - rect.top;
    let best: WorldNode | null = null, bd = 1e9;
    for (const n of this.nodes) { const p = this.project(n); const d = Math.hypot(p.x - px, p.y - py); if (d < bd) { bd = d; best = n; } }
    if (best && bd <= Math.max(14, 18)) this.onPick(best);
  }

  /** Nearest node id to a screen point, used for keyboard/AT parity. */
  nodesByActivity(limit = 12): WorldNode[] { return [...this.nodes].sort((a, b) => b.e - a.e).slice(0, limit); }

  draw(now: number) {
    const { ctx, w, h, dpr } = this;
    if (this.modeT < 1) this.modeT = clamp((now - this.modeStart) / 1400, 0, 1);
    const t = ease(this.modeT);
    if (this.blendT < 1) this.blendT = clamp((now - this.blendStart) / 900, 0, 1);
    const eb = ease(this.blendT);
    const rate = this.reducedMotion ? 1 : 0.075;
    this.cam.x = lerp(this.cam.x, this.target.x, rate); this.cam.y = lerp(this.cam.y, this.target.y, rate); this.cam.k = lerp(this.cam.k, this.target.k, rate);

    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    const time = this.reducedMotion ? 0 : now / 1000;
    const focus = this.focusId != null ? this.byId.get(this.focusId) : undefined;

    // edges: only real relationships from the data
    if (this.mode === "overview") {
      // Visible enough to read as "these are connected" at a glance, without turning into a hairball:
      // width and alpha both scale with shared-actor count (data-driven, not decorative).
      for (const e of this.edges) {
        const a = this.byId.get(e.s), b = this.byId.get(e.t); if (!a || !b) continue;
        const pa = this.project(a), pb = this.project(b);
        ctx.lineWidth = Math.min(2.4, 0.8 + e.w * 0.18);
        ctx.strokeStyle = `rgba(243,233,210,${Math.min(0.55, 0.22 + e.w * 0.05)})`;
        ctx.beginPath(); ctx.moveTo(pa.x, pa.y); ctx.lineTo(pb.x, pb.y); ctx.stroke();
      }
    }

    for (const n of this.nodes) {
      const isFocus = focus && n.id === focus.id;
      const p = this.project(n);
      if (p.x < -20 || p.y < -20 || p.x > w + 20 || p.y > h + 20) continue;
      const lg = lerp(this.prevLog.get(n.id) ?? 0, Math.log1p(n.e) / this.maxLog, eb);   // 0..1 semantic brightness
      const tw = this.reducedMotion ? 0 : Math.sin(time * (0.6 + lg * 1.4) + (this.phase.get(n.id) ?? 0)) * 0.5 + 0.5;   // atmosphere
      let alpha = 0.22 + lg * 0.62 + tw * 0.08 * lg;
      let r = 1.3 + lg * 3.4;   // was 0.9 + lg*2.4: at typical demo/first-week scale (tens to low
                                 // hundreds of events) the old range (1.6-3.3px) read as uniform dots
                                 // on most displays; this widens it (1.3-4.7px) so size differences
                                 // are legible without a magnifying glass.
      if (!isFocus) alpha *= lerp(1, this.fadeOthers, t);
      if (this.silence && !isFocus) alpha *= 0.55;
      if (isFocus) {
        if (this.mode === "silence") { alpha = 0.10 + 0.05 * tw; r = 2; }               // the repo is drawn barely there during silence
        else if (this.mode === "reignite") { alpha = 0.35 + 0.65 * t; r = 2 + 7 * t; }  // and ignites on return
        else { alpha = 0.95; r = 3.5 + lg * 5; }
      }
      ctx.fillStyle = isFocus && this.mode === "reignite" ? `rgba(255,214,140,${alpha})` : `rgba(243,233,210,${alpha})`;
      ctx.beginPath(); ctx.arc(p.x, p.y, r, 0, 6.2832); ctx.fill();
      if (isFocus && this.mode === "reignite" && !this.reducedMotion) {
        for (let i = 0; i < 3; i++) {                     // ripple rings: reignition, one per ring
          const ph = (time * 0.5 + i / 3) % 1;
          ctx.strokeStyle = `rgba(255,214,140,${(1 - ph) * 0.35 * t})`;
          ctx.beginPath(); ctx.arc(p.x, p.y, 8 + ph * 90, 0, 6.2832); ctx.stroke();
        }
      }
    }

    if (eb < 1) for (const g of this.ghosts) {                 // repos that were on the map the day before and are not now
      const p = this.project(g.n);
      ctx.fillStyle = `rgba(243,233,210,${(1 - eb) * (0.16 + g.lg * 0.6)})`;
      ctx.beginPath(); ctx.arc(p.x, p.y, 0.9 + g.lg * 2.4, 0, 6.2832); ctx.fill();
    }

    // fork burst: each ray = one fork event recorded in the data (count from world node .f)
    if (this.mode === "fork" && focus) {
      const c = this.project(focus); const s = Math.min(w, h);
      for (const k of this.forkKids) {
        const reach = ease(clamp(t * 1.4 - k.d * 0.4, 0, 1)) * s * (0.12 + k.r * 2.4);
        const x = c.x + Math.cos(k.a) * reach, y = c.y + Math.sin(k.a) * reach;
        ctx.strokeStyle = "rgba(243,233,210,0.28)"; ctx.beginPath(); ctx.moveTo(c.x, c.y); ctx.lineTo(x, y); ctx.stroke();
        ctx.fillStyle = "rgba(255,214,140,0.85)"; ctx.beginPath(); ctx.arc(x, y, 2.2, 0, 6.2832); ctx.fill();
      }
    }
  }
}
