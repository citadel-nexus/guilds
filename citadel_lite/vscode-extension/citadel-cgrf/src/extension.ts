// src/extension.ts
// Citadel CGRF VS Code Extension — entry point.

import * as vscode from "vscode";
import { runValidate, runTierCheck, ValidateResult } from "./cgrfRunner";
import { getConfig } from "./config";
import { CgrfStatusBar } from "./statusBar";
import { CgrfDiagnostics } from "./diagnostics";
import { CgrfCodeLensProvider } from "./codeLens";

let statusBar: CgrfStatusBar;
let diagnostics: CgrfDiagnostics;
let codeLensProvider: CgrfCodeLensProvider;

// ── Helpers ──

function getWorkspaceRoot(): string | undefined {
  return vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
}

async function validateFile(
  uri: vscode.Uri,
  tier?: number
): Promise<ValidateResult | undefined> {
  const root = getWorkspaceRoot();
  if (!root) {
    vscode.window.showWarningMessage("CGRF: No workspace folder open");
    return;
  }

  const t = tier ?? getConfig().defaultTier;

  try {
    const result = await runValidate(root, uri.fsPath, t);
    statusBar.update(result);
    diagnostics.update(uri, result);
    codeLensProvider.setResult(uri, result.compliant, result.tier);
    return result;
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    statusBar.showError("Error");
    vscode.window.showErrorMessage(`CGRF validation failed: ${msg}`);
    return;
  }
}

// ── Activation ──

export function activate(context: vscode.ExtensionContext): void {
  statusBar = new CgrfStatusBar();
  diagnostics = new CgrfDiagnostics();
  codeLensProvider = new CgrfCodeLensProvider();

  // Register CodeLens provider for Python files
  context.subscriptions.push(
    vscode.languages.registerCodeLensProvider(
      { language: "python", scheme: "file" },
      codeLensProvider
    )
  );

  // Command: Validate current file
  context.subscriptions.push(
    vscode.commands.registerCommand("citadel-cgrf.validate", async () => {
      const editor = vscode.window.activeTextEditor;
      if (!editor || editor.document.languageId !== "python") {
        vscode.window.showInformationMessage("CGRF: Open a Python file to validate");
        return;
      }
      const result = await validateFile(editor.document.uri);
      if (result) {
        const status = result.compliant ? "Compliant" : "Non-Compliant";
        vscode.window.showInformationMessage(`CGRF: ${status} (Tier ${result.tier})`);
      }
    })
  );

  // Command: Tier Check all agents
  context.subscriptions.push(
    vscode.commands.registerCommand("citadel-cgrf.tierCheck", async () => {
      const root = getWorkspaceRoot();
      if (!root) {
        vscode.window.showWarningMessage("CGRF: No workspace folder open");
        return;
      }
      const tier = getConfig().defaultTier;
      try {
        const result = await runTierCheck(root, ["src/agents/*.py"], tier);
        const { passed, failed } = result.summary;
        vscode.window.showInformationMessage(
          `CGRF Tier Check: ${passed} passed, ${failed} failed (Tier ${tier})`
        );
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        vscode.window.showErrorMessage(`CGRF tier-check failed: ${msg}`);
      }
    })
  );

  // Command: Set target tier
  context.subscriptions.push(
    vscode.commands.registerCommand("citadel-cgrf.setTier", async () => {
      const pick = await vscode.window.showQuickPick(
        [
          { label: "Tier 0", description: "Experimental", value: 0 },
          { label: "Tier 1", description: "Development", value: 1 },
          { label: "Tier 2", description: "Production", value: 2 },
          { label: "Tier 3", description: "Mission-Critical", value: 3 },
        ],
        { placeHolder: "Select target CGRF tier" }
      );
      if (pick) {
        await vscode.workspace
          .getConfiguration("citadel-cgrf")
          .update("defaultTier", pick.value, vscode.ConfigurationTarget.Workspace);
        vscode.window.showInformationMessage(`CGRF: Target tier set to ${pick.label}`);
      }
    })
  );

  // Validate on save
  context.subscriptions.push(
    vscode.workspace.onDidSaveTextDocument(async (doc) => {
      if (doc.languageId !== "python") return;
      if (!getConfig().validateOnSave) return;
      await validateFile(doc.uri);
    })
  );

  // Update status bar on active editor change
  context.subscriptions.push(
    vscode.window.onDidChangeActiveTextEditor(async (editor) => {
      if (!editor || editor.document.languageId !== "python") {
        statusBar.hide();
        return;
      }
      await validateFile(editor.document.uri);
    })
  );

  // Cleanup
  context.subscriptions.push(statusBar, diagnostics, codeLensProvider);

  // Validate active file on startup
  const activeEditor = vscode.window.activeTextEditor;
  if (activeEditor && activeEditor.document.languageId === "python") {
    validateFile(activeEditor.document.uri);
  }
}

export function deactivate(): void {
  // All disposables registered via context.subscriptions
}
