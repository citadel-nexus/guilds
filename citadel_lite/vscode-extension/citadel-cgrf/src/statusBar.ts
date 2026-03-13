// src/statusBar.ts
// Status bar item showing CGRF Tier for the active file.

import * as vscode from "vscode";
import { ValidateResult } from "./cgrfRunner";

const TIER_LABELS: Record<number, string> = {
  0: "Experimental",
  1: "Development",
  2: "Production",
  3: "Mission-Critical",
};

export class CgrfStatusBar {
  private item: vscode.StatusBarItem;

  constructor() {
    this.item = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 100);
    this.item.command = "citadel-cgrf.validate";
    this.item.tooltip = "Click to validate CGRF compliance";
  }

  /** Update the status bar with a validation result. */
  update(result: ValidateResult): void {
    const label = TIER_LABELS[result.tier] ?? `Tier ${result.tier}`;
    if (result.compliant) {
      this.item.text = `$(pass) CGRF: Tier ${result.tier} (${label})`;
      this.item.backgroundColor = undefined;
    } else {
      this.item.text = `$(error) CGRF: Tier ${result.tier} (${label})`;
      this.item.backgroundColor = new vscode.ThemeColor("statusBarItem.warningBackground");
    }
    this.item.show();
  }

  /** Show an error state. */
  showError(message: string): void {
    this.item.text = `$(alert) CGRF: ${message}`;
    this.item.backgroundColor = new vscode.ThemeColor("statusBarItem.errorBackground");
    this.item.show();
  }

  /** Hide the status bar (non-Python file). */
  hide(): void {
    this.item.hide();
  }

  dispose(): void {
    this.item.dispose();
  }
}
