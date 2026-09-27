import type { Bundle, Latest, Pulse, Story } from "../types";

const BASE = import.meta.env.BASE_URL; // "/" locally, "/<repo>/" on Pages. Never a root-relative literal.

async function getJSON<T>(rel: string, optional = false): Promise<T | null> {
  try {
    const r = await fetch(`${BASE}data/${rel}`, { cache: "no-cache" });
    if (!r.ok) { if (optional) return null; throw new Error(`${rel}: HTTP ${r.status}`); }
    return (await r.json()) as T;
  } catch (e) {
    if (optional) return null;
    throw e;
  }
}

export class DataUnavailable extends Error {}

/** Load everything the experience needs. Required files must exist; the story and pulse are optional
 *  (a warming-up or quiet day legitimately has no story; the pulse may be partial). */
export async function loadBundle(): Promise<Bundle> {
  let latest: Latest;
  try { latest = (await getJSON<Latest>("latest.json"))!; }
  catch (e) { throw new DataUnavailable("No snapshot has been published yet."); }

  const [status, world, worldIdx, hourly, history, graveyard, index, pulse, provenance, method] = await Promise.all([
    getJSON<Bundle["status"]>("status.json"), getJSON<Bundle["world"]>(`worlds/${latest.date}.json`),
    getJSON<{ days: string[] }>("worlds/index.json"),
    getJSON<Bundle["hourly"]>("hourly.json"), getJSON<Bundle["history"]>("history.json"),
    getJSON<Bundle["graveyard"]>("graveyard.json"), getJSON<Bundle["index"]>("stories/index.json"),
    getJSON<Pulse>("pulse.json", true), getJSON<Bundle["provenance"]>("provenance.json"),
    getJSON<Bundle["method"]>("method.json"),
  ]);
  const story = latest.story_id ? await getJSON<Story>(`stories/${latest.date}.json`, true) : null;
  return { latest, status: status!, world: world!, worldDays: worldIdx?.days ?? [latest.date], hourly: hourly!, history: history!, graveyard: graveyard!,
           story, index: index!, pulse, provenance: provenance!, method: method! };
}

const storyCache = new Map<string, Story | null>();
export async function loadStory(date: string): Promise<Story | null> {
  if (!storyCache.has(date)) storyCache.set(date, await getJSON<Story>(`stories/${date}.json`, true));
  return storyCache.get(date) ?? null;
}
const worldCache = new Map<string, Bundle["world"] | null>();
export async function loadWorld(date: string): Promise<Bundle["world"] | null> {
  if (!worldCache.has(date)) worldCache.set(date, await getJSON<Bundle["world"]>(`worlds/${date}.json`, true));
  return worldCache.get(date) ?? null;
}

/** Freshness is computed from the publish timestamp, in words AND a machine state, so "stale" is never colour-only. */
export function freshness(generatedAt: string, now = Date.now()): { state: "current" | "stale"; label: string } {
  const hours = (now - Date.parse(generatedAt)) / 3.6e6;
  return hours > 30 ? { state: "stale", label: `STALE: last update ${ago(generatedAt, now)}` }
                    : { state: "current", label: `Updated ${ago(generatedAt, now)}` };
}

/** A repository name becomes a link only if it matches GitHub's own grammar: owner = alphanumerics and single
 *  hyphens (no dots, so "." and ".." can never appear), repo = [A-Za-z0-9_.-] but never "." or "..". */
export function safeRepoUrl(name: string): string | null {
  const m = /^([A-Za-z0-9](?:[A-Za-z0-9-]{0,38}))\/([A-Za-z0-9_.-]{1,100})$/.exec(name);
  if (!m || m[2] === "." || m[2] === "..") return null;
  return `https://github.com/${m[1]}/${m[2]}`;
}

export function fmt(n: number): string { return n.toLocaleString("en-US"); }
export function ago(iso: string, now = Date.now()): string {
  const s = Math.max(0, (now - Date.parse(iso)) / 1000);
  if (s < 90) return "just now";
  if (s < 5400) return `${Math.round(s / 60)} minutes ago`;
  if (s < 129600) return `${Math.round(s / 3600)} hours ago`;
  return `${Math.round(s / 86400)} days ago`;
}
