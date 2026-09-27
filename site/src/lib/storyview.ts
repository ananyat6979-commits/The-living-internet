import { h } from "./dom";
import { seriesChart, type Highlight } from "./chart";
import { safeRepoUrl, fmt } from "./data";
import type { Claim, Story } from "../types";
import type { Mode } from "./world";

/** How each beat of a story moves the World and the chart. The words come from claims; this table only chooses motion. */
export const BEAT_MAP: Record<string, { mode: Mode; chart: Highlight }> = {
  silence_field: { mode: "silence", chart: "none" }, silence_stretch: { mode: "silence", chart: "gap" },
  past_activity: { mode: "focus", chart: "past" }, reignite: { mode: "reignite", chart: "today" },
  hold: { mode: "focus", chart: "all" }, fade_to_blank: { mode: "silence", chart: "none" },
  baseline_line: { mode: "focus", chart: "baseline" }, spike_rise: { mode: "focus", chart: "today" },
  peer_strip: { mode: "focus", chart: "all" }, single_node: { mode: "focus", chart: "none" },
  birth_point: { mode: "focus", chart: "today" }, fork_burst: { mode: "fork", chart: "none" },
};
const LABEL: Record<string, string> = {
  silence: "The silence", before: "Before that", return: "The return", read: "Our reading", unknown: "What we can't see",
  spike: "Yesterday", peers: "Compared with similar repositories", branch: "The branches", first: "First sighting", hook: "",
};
export const TAG: Record<Claim["cls"], string> = { observed: "Observed", derived: "Derived", interpretation: "Our reading", unknown: "We can't see" };

export interface StoryHooks { onEvidence: (claimId: string) => void; links: boolean; }

function claimEl(c: Claim, hooks: StoryHooks): HTMLElement {
  const p = h("p", { class: `claim claim--${c.cls}` }, h("span", { class: "tag" }, TAG[c.cls]), " ", h("span", { class: "claim-text" }, c.text));
  if (c.cls === "observed" || c.cls === "derived") {
    const rows: [string, string][] = [["measure", String(c.metric)], ["value", `${String(c.value)}${c.unit ? " " + c.unit : ""}`],
      ...Object.entries(c.evidence).map(([k, v]) => [k.replace(/_/g, " "), String(v)] as [string, string])];
    const det = h("details", { class: "evidence", toggle: (e) => { if ((e.target as HTMLDetailsElement).open) hooks.onEvidence(c.id); } },
      h("summary", {}, "How do we know?"),
      h("dl", {}, ...rows.flatMap(([k, v]) => [h("dt", {}, k), h("dd", {}, v)])),
      h("p", { class: "fine" }, c.cls === "derived" ? "Derived: arithmetic on observed counts. The inputs are the observed claims above it." : "Observed: counted directly in the public event stream. The receipts at the end of this story let you find the raw events yourself."));
    return h("div", { class: "claim-wrap" }, p, det);
  }
  return h("div", { class: "claim-wrap" }, p);
}

export function renderStory(story: Story, hooks: StoryHooks): HTMLElement {
  const byId = new Map(story.claims.map((c) => [c.id, c]));
  const url = hooks.links ? safeRepoUrl(story.repo) : null;
  const root = h("div", { class: "story", "data-story": story.id, "data-date": story.date });
  root.append(h("section", { class: "step step--title", "data-mode": "focus", "data-focus": String(story.repo_id), "data-highlight": "none" },
    h("div", { class: "card card--title" },
      h("p", { class: "kicker" }, `${story.date} · today's story`),
      h("h2", { class: "title" }, story.title),
      h("p", { class: "hook" }, story.hook),
      h("p", { class: "repo" }, story.repo, " ", url ? h("a", { class: "btn", href: url, rel: "noopener noreferrer", target: "_blank" }, "Open on GitHub ↗") : null),
      h("p", { class: "fine" }, "Scroll. Every sentence below is built from a counted number; open “How do we know?” under any of them."))));

  for (const b of story.beats) {
    const map = BEAT_MAP[b.visual] ?? { mode: "focus" as Mode, chart: "none" as Highlight };
    const claims = b.claims.map((id) => byId.get(id)).filter((c): c is Claim => !!c);
    const label = LABEL[b.beat] ?? "";
    const step = h("section", { class: `step step--${b.visual}`, "data-mode": map.mode, "data-focus": String(story.repo_id), "data-highlight": map.chart, "data-beat": b.beat },
      h("div", { class: `card${b.text && !claims.length ? " card--word" : ""}` },
        label ? h("p", { class: "kicker" }, label) : null,
        b.text ? h("p", { class: "word" }, b.text) : null,
        map.chart !== "none" && story.series?.length ? seriesChart(story.series, `Daily public events for ${story.repo}, ${story.series.length} days`) : null,
        ...claims.map((c) => claimEl(c, hooks))));
    root.append(step);
  }
  root.append(receiptsStep(story));
  return root;
}

function receiptsStep(story: Story): HTMLElement {
  const ev = story.evidence;
  const files = [...new Map(ev.events.map((e) => [e.file, e.sha256])).entries()];
  const first = ev.events[0];
  return h("section", { class: "step step--receipts", "data-mode": "focus", "data-focus": String(story.repo_id), "data-highlight": "none", "data-beat": "receipts" },
    h("div", { class: "card card--wide" },
      h("p", { class: "kicker" }, "The receipts"),
      h("p", { class: "lead" }, `${fmt(ev.shown)} of the ${fmt(ev.total)} events we counted for this repository on ${ev.day}. These are real GitHub event ids. Account names are deliberately left out.`),
      h("div", { class: "table-wrap" }, h("table", {},
        h("caption", { class: "sr-only" }, "Sample of raw events behind this story"),
        h("thead", {}, h("tr", {}, ...["event id", "time (UTC)", "type", "archive file"].map((t) => h("th", { scope: "col" }, t)))),
        h("tbody", {}, ...ev.events.map((e) => h("tr", {}, h("td", {}, e.id), h("td", {}, e.t.slice(11, 19)), h("td", {}, e.type + (e.action ? ` · ${e.action}` : "")), h("td", {}, e.file)))))),
      first ? h("details", { class: "evidence" }, h("summary", {}, "Check it yourself"),
        h("p", { class: "fine" }, "Download the hourly file, then look for an id from the table. If it is not there, we are wrong."),
        h("pre", {}, `curl -sL https://data.gharchive.org/${first.file} -o hour.json.gz\n${first.sha256 ? `sha256sum hour.json.gz   # expect ${first.sha256}\n` : ""}zcat hour.json.gz | grep '"id":"${first.id}"'`),
        h("ul", { class: "files" }, ...files.map(([f, sha]) => h("li", {}, h("code", {}, f), sha ? `: sha256 ${sha.slice(0, 16)}…` : "")))) : null,
      h("p", { class: "fine" }, `Story fingerprint ${story.provenance_sha}: identifies the exact source files and pipeline versions it came from.`)));
}
