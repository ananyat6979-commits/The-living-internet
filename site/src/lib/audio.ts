import { mulberry32 } from "./rng";

/** The sound of the day. Muted by default; starts only on a user gesture; never carries information the
 *  visuals do not (audio is atmosphere). Each hour of the real day is one beat; the number of notes in a beat
 *  follows that hour's share of the day's peak hourly event count. */
const SCALE = [196.0, 220.0, 261.63, 293.66, 329.63, 392.0, 440.0]; // A minor pentatonic-ish, low and soft

export function densityFor(hours: number[]): number[] {
  const max = Math.max(1, ...hours);
  return hours.map((v) => v / max);
}
/** How many notes to play for a beat of given density (0..1). Quiet hour => 0 or 1; peak hour => 3. */
export function notesForBeat(density: number): number { return density <= 0.15 ? 0 : Math.min(3, 1 + Math.floor(density * 2.5)); }

export class Soundscape {
  private ctx: AudioContext | null = null;
  private master: GainNode | null = null;
  private timer: number | null = null;
  private idx = 0;
  private dens: number[] = [];
  private rnd = mulberry32(7);
  private quiet = false;
  on = false;

  setHours(hours: number[]) { this.dens = densityFor(hours); }
  setQuiet(q: boolean) { this.quiet = q; if (this.master && this.ctx) this.master.gain.setTargetAtTime(q ? 0.0 : 0.6, this.ctx.currentTime, 0.8); }

  async toggle(): Promise<boolean> {
    if (this.on) { this.stop(); return false; }
    const AC = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!AC) return false;
    this.ctx ??= new AC();
    if (!this.master) { this.master = this.ctx.createGain(); this.master.gain.value = 0.6; this.master.connect(this.ctx.destination); }
    await this.ctx.resume();
    this.on = true;
    this.timer = window.setInterval(() => this.beat(), 900);
    return true;
  }
  stop() { this.on = false; if (this.timer !== null) window.clearInterval(this.timer); this.timer = null; void this.ctx?.suspend(); }

  private beat() {
    if (!this.ctx || !this.master || !this.dens.length) return;
    const d = this.dens[this.idx % this.dens.length] ?? 0;
    this.idx++;
    if (this.quiet) return;
    for (let i = 0; i < notesForBeat(d); i++) this.ping(SCALE[Math.floor(this.rnd() * SCALE.length)] ?? 220, i * 0.18);
  }
  private ping(freq: number, delay: number) {
    if (!this.ctx || !this.master) return;
    const t = this.ctx.currentTime + delay, o = this.ctx.createOscillator(), g = this.ctx.createGain();
    o.type = "sine"; o.frequency.value = freq;
    g.gain.setValueAtTime(0, t); g.gain.linearRampToValueAtTime(0.02, t + 0.05); g.gain.exponentialRampToValueAtTime(0.0001, t + 1.4);
    o.connect(g); g.connect(this.master); o.start(t); o.stop(t + 1.5);
  }
  /** A single rising tone for a return from silence. */
  swell() {
    if (!this.on || !this.ctx || !this.master) return;
    const t = this.ctx.currentTime, o = this.ctx.createOscillator(), g = this.ctx.createGain();
    o.type = "sine"; o.frequency.setValueAtTime(110, t); o.frequency.exponentialRampToValueAtTime(330, t + 2.2);
    g.gain.setValueAtTime(0, t); g.gain.linearRampToValueAtTime(0.04, t + 1.2); g.gain.exponentialRampToValueAtTime(0.0001, t + 3);
    o.connect(g); g.connect(this.master); o.start(t); o.stop(t + 3.1);
  }
}
