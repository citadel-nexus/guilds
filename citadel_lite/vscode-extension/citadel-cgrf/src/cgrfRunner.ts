// src/cgrfRunner.ts
// Runs CGRF CLI as subprocess and parses JSON output.

import { execFile } from "child_process";
import * as path from "path";
import * as fs from "fs";
import { getConfig } from "./config";

// ── JSON types matching CGRF CLI output ──

export interface CgrfCheck {
  name: string;
  passed: boolean;
  message: string;
  required: boolean;
}

export interface ValidateResult {
  command: "validate";
  tier: number;
  module_path: string;
  compliant: boolean;
  checks: CgrfCheck[];
  warnings: string[];
}

export interface TierCheckEntry {
  module_path: string;
  compliant: boolean;
  failed_checks: { name: string; message: string }[];
}

export interface TierCheckResult {
  command: "tier-check";
  tier: number;
  results: TierCheckEntry[];
  summary: { total: number; passed: number; failed: number };
}

export interface ReportModule {
  module_path: string;
  compliant: boolean;
}

export interface ReportResult {
  command: "report";
  tier: number;
  modules: ReportModule[];
  summary: { total: number; compliant: number; non_compliant: number };
}

// ── Runner ──

/**
 * Locate cgrf.py by walking up from the workspace root.
 * Returns the directory containing cgrf.py (used as cwd for subprocess).
 */
export function findCgrfRoot(workspaceRoot: string): string | undefined {
  const configured = getConfig().cgrfPath;
  if (configured) {
    const dir = path.dirname(configured);
    if (fs.existsSync(configured)) {
      return dir;
    }
  }

  // Walk up looking for cgrf.py
  let current = workspaceRoot;
  for (let i = 0; i < 5; i++) {
    if (fs.existsSync(path.join(current, "cgrf.py"))) {
      return current;
    }
    const parent = path.dirname(current);
    if (parent === current) break;
    current = parent;
  }
  return undefined;
}

function runCli(
  cwd: string,
  args: string[]
): Promise<string> {
  const pythonPath = getConfig().pythonPath;
  const cgrfScript = path.join(cwd, "cgrf.py");

  return new Promise((resolve, reject) => {
    execFile(
      pythonPath,
      [cgrfScript, ...args, "--json"],
      { cwd, timeout: 30_000 },
      (error, stdout, stderr) => {
        // CLI returns exit code 1 for non-compliant but still produces valid JSON
        if (stdout && stdout.trim()) {
          resolve(stdout.trim());
        } else if (error) {
          reject(new Error(stderr || error.message));
        } else {
          reject(new Error("No output from CGRF CLI"));
        }
      }
    );
  });
}

/**
 * Run `cgrf validate --module <path> --tier <n> --json`.
 */
export async function runValidate(
  workspaceRoot: string,
  filePath: string,
  tier: number
): Promise<ValidateResult> {
  const cwd = findCgrfRoot(workspaceRoot);
  if (!cwd) {
    throw new Error("cgrf.py not found in workspace");
  }
  const raw = await runCli(cwd, ["validate", "--module", filePath, "--tier", String(tier)]);
  return JSON.parse(raw) as ValidateResult;
}

/**
 * Run `cgrf tier-check <modules...> --tier <n> --json`.
 */
export async function runTierCheck(
  workspaceRoot: string,
  modules: string[],
  tier: number
): Promise<TierCheckResult> {
  const cwd = findCgrfRoot(workspaceRoot);
  if (!cwd) {
    throw new Error("cgrf.py not found in workspace");
  }
  const raw = await runCli(cwd, ["tier-check", ...modules, "--tier", String(tier)]);
  return JSON.parse(raw) as TierCheckResult;
}

/**
 * Run `cgrf report --tier <n> --json`.
 */
export async function runReport(
  workspaceRoot: string,
  tier: number
): Promise<ReportResult> {
  const cwd = findCgrfRoot(workspaceRoot);
  if (!cwd) {
    throw new Error("cgrf.py not found in workspace");
  }
  const raw = await runCli(cwd, ["report", "--tier", String(tier)]);
  return JSON.parse(raw) as ReportResult;
}
