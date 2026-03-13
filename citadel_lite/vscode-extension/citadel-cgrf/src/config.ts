// src/config.ts
// Extension configuration helpers.

import * as vscode from "vscode";

export interface CgrfConfig {
  pythonPath: string;
  defaultTier: number;
  validateOnSave: boolean;
  cgrfPath: string;
}

export function getConfig(): CgrfConfig {
  const cfg = vscode.workspace.getConfiguration("citadel-cgrf");
  return {
    pythonPath: cfg.get<string>("pythonPath", "python"),
    defaultTier: cfg.get<number>("defaultTier", 1),
    validateOnSave: cfg.get<boolean>("validateOnSave", true),
    cgrfPath: cfg.get<string>("cgrfPath", ""),
  };
}
