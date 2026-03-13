// src/codeLens.ts
// CodeLens provider showing CGRF Tier badge at module top.

import * as vscode from "vscode";

const TIER_LABELS: Record<number, string> = {
  0: "Experimental",
  1: "Development",
  2: "Production",
  3: "Mission-Critical",
};

/** Regex to find _CGRF_TIER = N in source. */
const TIER_REGEX = /_CGRF_TIER\s*=\s*(\d+)/;

export class CgrfCodeLensProvider implements vscode.CodeLensProvider {
  private _onDidChange = new vscode.EventEmitter<void>();
  readonly onDidChangeCodeLenses = this._onDidChange.event;

  // Cache of last validation result per file
  private cache = new Map<string, { compliant: boolean; tier: number }>();

  /** Update cached result and refresh lenses. */
  setResult(uri: vscode.Uri, compliant: boolean, tier: number): void {
    this.cache.set(uri.toString(), { compliant, tier });
    this._onDidChange.fire();
  }

  provideCodeLenses(document: vscode.TextDocument): vscode.CodeLens[] {
    if (document.languageId !== "python") return [];

    const text = document.getText();
    const match = TIER_REGEX.exec(text);
    if (!match) return [];

    const declaredTier = parseInt(match[1], 10);
    const label = TIER_LABELS[declaredTier] ?? `Tier ${declaredTier}`;

    // Find the line containing _CGRF_TIER
    const offset = match.index;
    const pos = document.positionAt(offset);
    const range = new vscode.Range(pos.line, 0, pos.line, 0);

    const cached = this.cache.get(document.uri.toString());
    const icon = cached ? (cached.compliant ? "$(pass)" : "$(error)") : "$(question)";
    const statusText = cached
      ? (cached.compliant ? "Compliant" : "Non-Compliant")
      : "Not validated";

    return [
      new vscode.CodeLens(range, {
        title: `${icon} CGRF Tier ${declaredTier} (${label}) — ${statusText}`,
        command: "citadel-cgrf.validate",
        tooltip: "Click to validate CGRF compliance",
      }),
    ];
  }

  dispose(): void {
    this._onDidChange.dispose();
  }
}
