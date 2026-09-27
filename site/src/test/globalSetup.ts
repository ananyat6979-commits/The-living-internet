import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";

/** Runs ONCE before any test file is collected, regardless of whether the suite is invoked via
 *  `npm test` (whose `pretest` script would otherwise do this) or directly via `vitest`/`vitest run`.
 *  Without this, `haveData` in helpers.ts was evaluated at module-import time, before Vitest's own
 *  npm-lifecycle pretest step was guaranteed to have finished writing test-data/, which silently
 *  skipped most of the app suite whenever the suite was run any way other than `npm test` exactly. */
export default function setup() {
  if (existsSync("test-data/latest.json")) return;
  const python = process.platform === "win32" ? "python" : "python3";
  execFileSync(python, ["-m", "pipeline.demo", "site/test-data"], { cwd: "..", stdio: "inherit" });
}
