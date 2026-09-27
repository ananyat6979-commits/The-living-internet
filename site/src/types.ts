// The data contract. Mirrors what pipeline/publish.py writes. The UI may not invent facts;
// anything numeric it shows must come from one of these shapes.
export type ClaimClass = "observed" | "derived" | "interpretation" | "unknown";

export interface Claim {
  id: string; cls: ClaimClass; text: string;
  metric: string | null; value: number | string | null; unit: string | null;
  evidence: Record<string, unknown>;
}
export interface Beat { beat: string; visual: string; text?: string; claims: string[]; }
export interface SeriesPt { d: string; e: number | null; }   // e === null => before our record (unknown, NOT zero)
export interface EvidenceEvent { id: string; t: string; type: string; action: string | null; file: string; sha256: string | null; }
export interface Evidence { repo_id: number; day: string; total: number; shown: number; events: EvidenceEvent[]; }
export interface Story {
  id: string; date: string; archetype: "resurrection" | "growth" | "fork" | "newcomer";
  repo: string; repo_id: number; title: string; hook: string;
  automation_shaped: boolean; automation_reason: string;
  claims: Claim[]; beats: Beat[]; provenance_sha: string;
  series: SeriesPt[]; evidence: Evidence;
}
export interface Latest {
  date: string; generated_at: string; events: number; actors: number; repositories: number;
  status: string; held_reason: string | null; story_id: string | null;
  candidates: number; ledger_days: number; synthetic: boolean;
}
export interface Status {
  status: string; last_success: string; source_date: string; hours: string; events: number;
  rejected_lines: number; reject_rate: number; candidates: number; ledger_days: number;
  birth_signal: { repo_create_events: number; branch_create_events: number; repos_active: number; birth_signal_present: boolean };
  pipeline_version: string; engine_version: string; synthetic?: boolean;
}
export interface WorldNode { id: number; n: string; x: number; y: number; e: number; a: number; f: number; p: number; r: number; }
export interface WorldEdge { s: number; t: number; w: number; reason: string; }
export interface World { date: string; nodes: WorldNode[]; edges: WorldEdge[]; encoding: Record<string, string>; }
export interface HourRow { h: number; e: number; a: number; r: number; }
export interface DayRow { date: string; events: number; repos: number; forks: number; prs: number; issues: number; stars: number; }
export interface Pulse {
  generated_at: string; requested_hours: number; available_hours: number; missing: string[];
  status: "current" | "partial" | "unavailable"; hours: { t: string; e: number; a: number }[];
  loudest: { repo: string; events: number; actors: number; usual_per_day: number }[];
  window: { from: string; to: string; events: number } | null;
}
export interface GraveRow { repo_id: number; repo: string; silent_days: number; peak_events: number; peak_day: string; first_day: string; last_day: string; active_days: number; total_events: number; }
export interface StoryIndexRow { date: string; id: string | null; archetype: string; title: string; repo: string; held_reason: string | null; }
export interface Bundle {
  latest: Latest; status: Status; world: World; worldDays: string[]; hourly: { date: string; hours: HourRow[] };
  history: { days: DayRow[] }; graveyard: { date: string; rows: GraveRow[] };
  story: Story | null; index: { stories: StoryIndexRow[] }; pulse: Pulse | null;
  provenance: { files: { hour: number; sha256: string; bytes: number }[]; pipeline_version: string; engine_version: string; generated_at: string; accounting: { lines_read: number; accepted: number; rejected: number } };
  method: Record<string, number | string | string[]>;
}
