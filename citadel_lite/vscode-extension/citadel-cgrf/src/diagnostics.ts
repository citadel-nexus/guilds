// src/diagnostics.ts
// Maps CGRF validation results to VS Code Diagnostics (Problems panel).

import * as vscode from "vscode";
import { ValidateResult } from "./cgrfRunner";

export class CgrfDiagnostics {
  private collection: vscode.DiagnosticCollection;

  constructor() {
    this.collection = vscode.languages.createDiagnosticCollection("CGRF");
  }

  /** Update diagnostics for a file based on validation result. */
  update(uri: vscode.Uri, result: ValidateResult): void {
    const diagnostics: vscode.Diagnostic[] = [];

    for (const check of result.checks) {
      if (check.passed) continue;

      const severity = check.required
        ? vscode.DiagnosticSeverity.Error
        : vscode.DiagnosticSeverity.Warning;

      // Place at top of file (line 0) since CGRF checks are module-level
      const range = new vscode.Range(0, 0, 0, 0);
      const diag = new vscode.Diagnostic(range, `[${check.name}] ${check.message}`, severity);
      diag.source = "CGRF";
      diagnostics.push(diag);
    }

    for (const warning of result.warnings) {
      const range = new vscode.Range(0, 0, 0, 0);
      const diag = new vscode.Diagnostic(range, warning, vscode.DiagnosticSeverity.Information);
      diag.source = "CGRF";
      diagnostics.push(diag);
    }

    this.collection.set(uri, diagnostics);
  }

  /** Clear diagnostics for a file. */
  clear(uri: vscode.Uri): void {
    this.collection.delete(uri);
  }

  dispose(): void {
    this.collection.dispose();
  }
}
