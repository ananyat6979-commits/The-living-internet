/** What the visitor actually did. Feeds the closing screen. Everything here is counted, nothing is invented.
 *  Stays in memory only: nothing is stored, nothing is sent anywhere. */
export class Session {
  readonly startedAt = Date.now();
  storiesOpened = new Set<string>();
  evidenceOpened = 0;
  reposFollowed = new Set<string>();
  daysScrubbed = new Set<string>();
  graveyardViewed = new Set<string>();
  chaptersReached = new Set<string>();

  minutes(now = Date.now()) { return Math.max(0, (now - this.startedAt) / 60000); }

  /** Lines for the closing screen. Zero counts are omitted rather than reported as failures. */
  lines(events: number, day: string, now = Date.now()): string[] {
    const m = this.minutes(now);
    const out = [`You spent ${m < 1 ? "under a minute" : `${Math.round(m)} minute${Math.round(m) === 1 ? "" : "s"}`} looking at ${events.toLocaleString("en-US")} public events from ${day}.`];
    if (this.storiesOpened.size) out.push(`You read ${this.storiesOpened.size} stor${this.storiesOpened.size === 1 ? "y" : "ies"}.`);
    if (this.reposFollowed.size) out.push(`You followed ${this.reposFollowed.size} repositor${this.reposFollowed.size === 1 ? "y" : "ies"} on the map.`);
    if (this.evidenceOpened) out.push(`You asked “how do we know?” ${this.evidenceOpened} time${this.evidenceOpened === 1 ? "" : "s"}.`);
    if (this.daysScrubbed.size) out.push(`You travelled through ${this.daysScrubbed.size} day${this.daysScrubbed.size === 1 ? "" : "s"}.`);
    if (this.graveyardViewed.size) out.push(`You visited ${this.graveyardViewed.size} quiet repositor${this.graveyardViewed.size === 1 ? "y" : "ies"}.`);
    return out;
  }
}

/** Next scheduled daily update (05:17 UTC), for the "come back" line. */
export function nextDailyUpdate(now = new Date()): Date {
  const t = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate(), 5, 17, 0));
  if (t.getTime() <= now.getTime()) t.setUTCDate(t.getUTCDate() + 1);
  return t;
}
