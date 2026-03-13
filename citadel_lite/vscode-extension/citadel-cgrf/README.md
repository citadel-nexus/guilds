# Citadel CGRF Validator — VS Code Extension

Real-time CGRF (Citadel Governance & Regulatory Framework) Tier validation for Citadel Lite agents.

## Features

- **Status Bar**: Shows current file's CGRF Tier and compliance status
- **Validate on Save**: Automatically validates Python files when saved
- **Problems Panel**: Failed checks appear as Errors/Warnings in the Problems panel
- **CodeLens**: Tier badge displayed at `_CGRF_TIER` definition in source
- **Commands**: Manual validate, tier-check all agents, set target tier

## Requirements

- Python 3.10+ with `cgrf.py` accessible in the workspace
- Citadel Lite project with CGRF CLI (`src/cgrf/cli.py`)

## Extension Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `citadel-cgrf.pythonPath` | `python` | Python executable path |
| `citadel-cgrf.defaultTier` | `1` | Default validation tier (0-3) |
| `citadel-cgrf.validateOnSave` | `true` | Auto-validate on file save |
| `citadel-cgrf.cgrfPath` | (auto) | Path to cgrf.py |

## Commands

- **CGRF: Validate Current File** — Run validation on the active Python file
- **CGRF: Tier Check All Agents** — Check all agents against the target tier
- **CGRF: Set Target Tier** — Change the default validation tier

## Development

```bash
cd vscode-extension/citadel-cgrf
npm install
npm run compile
# Press F5 in VS Code to launch Extension Development Host
```

## Architecture

The extension calls `cgrf.py` as a subprocess with `--json` output mode and parses the structured result:

```
VS Code Extension ──(subprocess)──> python cgrf.py validate --json
                  <──(JSON stdout)── { "compliant": true, "checks": [...] }
```
