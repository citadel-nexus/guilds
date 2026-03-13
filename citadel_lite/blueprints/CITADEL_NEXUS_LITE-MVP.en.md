# CITADEL NEXUS LITE — MVP (Minimum Viable Product) Implementation Checklist (Final Version → Translation into MVP) FOR Dmitry

## Complete Memory Layer + Multi-Agent Orchestration System

**Date:** January 27, 2026  
**Target:** Microsoft AI Dev Days Hackathon (Agentic DevOps Category)  
**Owner:** Kousaki (Memory Layer Lead)  
**Purpose:** Sharing the minimum viable product (MVP) configuration for the upcoming Microsoft AI Dev Days Hackathon

---

# MVP (Minimum Viable Product) Implementation Checklist (Final Version → Translation into MVP)

## 0. Fixed Assumptions (Corresponding to v0 Diagram)

- The v0 diagram (concept/Azure wiring/Sequence) has been fixed as "correct" (as you have declared).

- The MVP prioritizes **end-to-end (E2E) functionality locally**.

- Azure/Foundry/Copilot are treated as **interchangeable "subsequent wiring"**.
  
  citadel-technical-blueprint-kou…

---

# Phase 1: Fix the "Contract (Interface)" to Pass E2E

This is the most important part. Even if we discard the thickness of the final form, **the contract must be fixed**.

## 1. Fix Event Contract (Event JSON v1)

**Fixed (MVP and actual implementation)**

- `types.EventJsonV1` (mandatory fields are hardcoded)
  
  - `schema_version="event_json_v1"`
  
  - `event_id`, `event_type`
  
  - `source` (e.g., github/ci/alert)
  
  - `occurred_at`
  
  - `repo`, `ref/branch` (at least one)
  
  - `summary`
  
  - `artifacts` (includes log_excerpt / links)  
    → Fixed as the only truth of the input.
    
    citadel-technical-blueprint-kou…

**Stub**

- Event Ingest (equivalent to Functions/Webhook) is not needed for MVP  
  → Just reading `demo/events/*.json` is sufficient.
  
  citadel-technical-blueprint-kou…

## 2. Fix Handoff Packet Contract (Common Structure for A2A Handoff)

**Fixed**

- `types.HandoffPacket`
  
  - `event` (EventJsonV1)
  
  - `artifacts`
  
  - `memory_hits` (to be expanded later)
  
  - `agent_outputs` (outputs from sentinel/sherlock/fixer/guardian)
  
  - `risk` (risk_score, etc.)
  
  - `audit_span_id`  
    → Fixed in the format of "appended and passed on".
    
    citadel-technical-blueprint-kou…

## 3. Fix Decision Contract (Output from Guardian)

**Fixed**

- `types.Decision`
  
  - `action`: `approve | need_approval | block`
  
  - `risk_score` (0–100 or 0–1 is acceptable)
  
  - `rationale` (short text)
  
  - `policy_refs` (array: can be empty at first)
    
    citadel-technical-blueprint-kou…

---

# Phase 2: Implement the Skeleton of the Orchestrator (Backbone of the Process)

## 4. Create the Orchestrator (Fixed Order)

**Fixed (actual implementation)**

- `orchestrator.py`
  
  - Retrieve one item from the outbox (MVP can use file input)
  
  - Always call `audit.start()`
  
  - Handoff in the order of Sentinel → Sherlock → Fixer → Guardian
  
  - Branch according to Guardian Decision
  
  - Always call `audit.finish()`
    
    citadel-technical-blueprint-kou…

**Stub**

- Queue (Service Bus / Outbox) is replaced with "File Outbox"
  
  - `demo/events/*.json` → treated as "outbox"
  
  - Alternatively, just read `outbox/pending/*.json`
    
    citadel-technical-blueprint-kou…

---

# Phase 3: 4 Agents are OK with "Minimal Logic + Fixed Output"

While the final form is expected to be on the Foundry Agent Service, the MVP will use **the same I/F for local functions**.

## 5. Sentinel (Detection and Classification)

**Fixed**

- `agents/sentinel.py`  
  Input: HandoffPacket → Output: classification/severity/signals appended to `agent_outputs.sentinel`

**Stub is OK**

- Classification can be rule-based (branching by event_type).
  
  citadel-technical-blueprint-kou…

## 6. Sherlock (Diagnosis)

**Fixed**

- `agents/sherlock.py`  
  Output: hypotheses/confidence/evidence appended.

**Stub is OK**

- Initially, create hypotheses based on keyword matches within `log_excerpt`  
  (e.g., `ModuleNotFoundError`, `ENV`, `PermissionDenied`).
  
  citadel-technical-blueprint-kou…

## 7. Fixer (Repair Proposal)

**Fixed**

- `agents/fixer.py`
  
  - Output: `fix_plan` (proposal content) + `patch/pr_draft` (text) + `risk_estimate`.

**Stub is OK**

- Initially, just return "repair policy text" (patch not required).

- Implement `FIXER_MODE` to create a switch for **local/coping**.
  
  - `local`: text generation.
  
  - `copilot`: to be implemented later (NotImplemented is acceptable for MVP).
    
    citadel-technical-blueprint-kou…

## 8. Guardian (Governance)

**Fixed (treated as "core" even in MVP)**

- `agents/guardian.py` (or `governance/engine.py`)
  
  - Calculate `risk_score`.
  
  - Return `Decision(action, rationale, policy_refs)`.

**Stub is OK**

- Policies can be a minimum of 3 rules.
  
  - `risk_score < 30` → approve.
  
  - `30–70` → need_approval.
  
  - `>=70` → block.

- `policy_refs` can be fixed strings like `"POLICY_DEMO_RISK_BAND_01"`.
  
  citadel-technical-blueprint-kou…

---

# Phase 4: Memory / Audit / Execution are "I/F Fixed + Content Stub"

The final form document is thick here. The MVP will **solidify only the I/F with the assumption of replacement**.

## 9. Memory Layer (Initially "3 Fixed Cases" is Sufficient)

**Fixed**

- Prepare `recall(query, k) -> list[MemoryHit]` in `memory/store.py`.

- `MemoryHit` type (id, title, snippet, tags, confidence, link).

**Stub**

- Just prepare 3 entries in `memory/mock_corpus.json` to return.
  
  citadel-technical-blueprint-kou…

## 10. Audit / Logs (Properly Retained in MVP)

**Fixed (actual implementation)**

- `audit/logger.py`
  
  - `audit.start(span_id, event_id)`
  
  - `audit.log(stage, payload)`
  
  - `audit.finish(outcome)`.

- `audit/report.py`
  
  - Generate `audit_report.json` (event/decision/agent_outputs/links).

**Stub is OK**

- Telemetry (App Insights, etc.) can be done later. For now, save JSON in `out/audit/...`.
  
  citadel-technical-blueprint-kou…

## 11. Execution (Initially "Write Instructions Without Execution")

**Fixed**

- Prepare `execute(decision, fix_plan) -> outcome` in `execution/runner.py`.

**Stub**

- Do not actually create PRs/CI reruns.  
  → Just output `out/execution/<event_id>/action.json`.
  
  citadel-technical-blueprint-kou…

---

# Phase 5: MVP "Pass Criteria" (Complete for Now)

- Runs with a single command.  
  `python -m src.orchestrator demo/events/ci_failed.sample.json`.

- `out/audit/<event_id>/audit_report.json` is generated.

- Outputs from 4 agents are gathered in `handoff_packet.json`.

- Decision is one of `approve|need_approval|block`.

- For approve/need_approval, `out/execution/.../action.json` is generated.
  
  citadel-technical-blueprint-kou…

---

# Phase 6: Approach the Final Form "Replacement Points" (Collaboration with Dmitry in Later Stages)

After the MVP passes, the order to align with the final form document.

## 12. Replace Outbox → Service Bus (Maintain I/F)

- Create `outbox_adapter.py` and switch the source from file to service bus.

## 13. Wrap Agents → Foundry Agent Service

- `agents/*.py` maintain I/F, replace internal calls with Foundry.

## 14. Audit → App Insights / Storage

- Only replace the backend of `audit/logger`.

## 15. Implement FixerCopilot (if necessary)

- Implement the contents of `FIXER_MODE=copilot`.
  
  - One of PR creation/modification/testing addition is sufficient.

---

# Rules When in Doubt (Super Important)

- **Fix the "Contract (types)", "Order of the Orchestrator", and "Guardian Decision".**

- **Stub the "External Wiring (Azure/Foundry/Copilot)" and "Heavy Store Groups".**

- **Audit must be real even in MVP** (this is the essence of Citadel).
  
  citadel-technical-blueprint-kou…