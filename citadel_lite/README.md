# Citadel Lite — Autonomous AI Operating System

[Japanese](README.ja.md)

**Microsoft AI Dev Days Hackathon 2026** — Aiming to conquer all 6 categories

| Category                             | Implementation Details                                                  |
| ------------------------------------ | --------------------------------------------------------------------- |
| **AI Applications & Agents**         | ZES AI Employee, Watcher Live Monitoring Agent, MCP Voice Integration  |
| **Agentic DevOps**                   | OAD Loop: Detection → Diagnosis → Repair → Governance → Self-Recovery  |
| **Best Use of Microsoft Foundry**    | All 4 core agents operate via Azure Foundry Agent Service             |
| **Best Enterprise Solution**         | ZES SaaS: Scout ¥2,200/month · Operator ¥2,900/month · Autopilot ¥4,400/month |
| **Best Multi-Agent System**          | 5 agents on A2A protocol, handoff with typed HandoffPacket           |
| **Best Azure Integration**           | Foundry + Azure OpenAI + Cosmos DB Memory + Service Bus Events       |

**Microsoft AI Dev Days Hackathon — Agentic DevOps Category**

Citadel Lite is a closed-loop multi-agent DevOps pipeline that detects CI/CD failures, diagnoses root causes, suggests fixes, enforces governance, and executes repairs. All of this is accompanied by a tamper-evident audit trail and responsible AI policies.

**Latest Implementation (2026-03-06)**:

- ✅ **VCC × OAD × Perplexity Integration Complete** - MS-A1 to A7 + MS-B1 to B3 + MS-C1 to C3 all implemented; 177 tests passed (BLUEPRINT v9.0)
- ✅ **Nemesis Defense System** - L2 Inspector / L3 Honeypots / L4 Oracle + Admin API completed (MS-B1 to B3)
- ✅ **VCCSakeReader + CAPS grade Integration** - `.sake` profile loading + T1 to T5 grade mapping (MS-C3)
- ✅ **DiagnosticsLoop** - READ→THINK→WRITE→ASSESS 4-step diagnostic loop + OrchestratorV3 Wire-in (MS-A3/A6)
- ✅ **Datadog Adapter** - External Observability emit of loop execution results (MS-A5)
- ✅ **CGRF CLAUDE.md + Audit Script** - Automatic audit of all modules via cgrf_audit.py (MS-C1)
- ✅ **Notion SMP Registry DB** - Module metadata synchronization with Notion (MS-C2)
- ✅ **Code Quality Enhancement** - Event JSON v1 A2A contract modification + elimination of deprecated API `datetime.utcnow()` (2026-02-28)
- ✅ **Notion/Supabase Visualization Integration** - Notion MCA block + Supabase REST mirror + Grafana 9-panel MCA dashboard (MS-7)
- ✅ **Generic Markdown + Gitlog Conversion + GGUF Enrichment** - GenericMarkdownTranslator / GitlogTranslator + Local Inference + CI Script (MS-8)
- ✅ **Roadmap Tracker & API** - IR snapshot + Finance Guild report + Health endpoint (MS-3)
- ✅ **Security Enhancements** - Command injection prevention (shlex.quote), eval() elimination (ast.literal_eval), cryptographic randomness (secrets.choice)
- ✅ **Stability Enhancements** - Wall-clock timeout, SSE memory leak prevention, upper limits on unbounded data structures (deque)
- ✅ **MCA Evolution Engine** - 7Phase AI teaching orchestration + automatic proposal generation (MS-4)
- ✅ **AWS Bedrock Integration** - 3 MCA teachings (Mirror/Oracle/Government) operational via Claude Opus 4.5
- ✅ **VS Code Extension** - CGRF Tier real-time IDE validation (Phase 27)
- ✅ **Monitoring & Observability** - Prometheus 16 metrics (12+4 MCA) + Grafana dashboard completed (Phase 26)
- ✅ **AIS XP/TP Economy** - Dual-Token economy engine completed (Phase 25)
- ✅ **AGS Pipeline** - 4-stage constitutional judicial pipeline completed (Phase 24)
- ✅ **CGRF v3.0 Tier 2 Achieved** - All 4 agents reached production level
- ✅ **Auto-Execution & Auto-Merge** - Risk-based fully automated system (Phase 22)
- ✅ **REFLEX Self-Repair** - Automatic retry feature on verification failure
- ✅ **1310 Tests Passed** - Full suite (as of 2026-03-06, +177 new tests)

---

## Structure
```
citadel-lite/
├── config/                        # Configuration files
│   ├── azure.yaml.example
│   └── settings.yaml              # Auto-execution, AGS, AIS, Monitoring settings
├── grafana/                       # Grafana dashboards (Phase 26, MS-7)
│   ├── citadel_dashboard.json     # Prometheus dashboard (11 panels)
│   └── mca_dashboard.json         # ✨ MCA 9-panel Grafana dashboard (MS-7)
├── ci/                            # ✨ CI scripts (MS-8)
│   └── translate_evolve_publish.sh  # translate→evolve→publish batch execution
├── old/                           # Legacy file backup (V2→V3 integration)
│   ├── orchestrator_v2.py
│   ├── orchestrator.py
│   ├── store.py
│   ├── runner.py
│   ├── sherlock.py
│   └── fixer.py
│
├── vscode-extension/              # ✨ VS Code Extension (Phase 27)
│   └── citadel-cgrf/
│       ├── package.json           # Extension manifest
│       ├── src/                   # TypeScript source (extension, cgrfRunner, statusBar, etc.)
│       └── test/                  # Extension tests
│
├── demo/
│   ├── events/
│   │   ├── ci_failed.sample.json
│   │   ├── deploy_failure.sample.json
│   │   └── security_alert.sample.json
│   └── run_demo.py
├── docs/                          # ✨ NEW: Documentation
│   └── AUTO_EXECUTION.md          # ✨ NEW: Auto-execution guide
│
├── src/
│   ├── types.py                    # Added CGRFMetadata dataclass (v3.0)
│   ├── orchestrator_v3.py          # Verify retry + REFLEX self-healing
│   ├── app.py
│   ├── process_loop.py
│   │
│   ├── agents/
│   │   ├── sentinel_v2.py          # CGRF Tier 1 metadata
│   │   ├── sherlock_v3.py          # CGRF Tier 1 metadata
│   │   ├── fixer_v3.py             # CGRF Tier 1 metadata
│   │   └── guardian_v3.py          # CGRF Tier 2 metadata
│   │
│   ├── ags/                        # ✨ AGS Pipeline (Phase 24)
│   │   ├── __init__.py             # Package init & public API
│   │   ├── caps_stub.py            # CAPS grading (D/C/B/A/S) + AIS bridge
│   │   ├── s00_generator.py        # S00: Intent normalization → SapientPacket
│   │   ├── s01_definer.py          # S01: Schema + CAPS tier validation
│   │   ├── s02_fate.py             # S02: 5 policy gates → ALLOW/REVIEW/DENY
│   │   ├── s03_archivist.py        # S03: Audit hash-chain recording
│   │   └── pipeline.py             # AGSPipeline runner (S00→S01→S02→S03)
│   │
│   ├── ais/                        # ✨ NEW: AIS XP/TP Economy (Phase 25)
│   │   ├── __init__.py             # Package init & public API
│   │   ├── profile.py              # AgentProfile (XP/TP tracking, CAPS conversion)
│   │   ├── storage.py              # ProfileStore (file-based JSON persistence)
│   │   ├── costs.py                # CostTable (action TP costs)
│   │   ├── rewards.py              # RewardCalculator (tier multipliers, bonuses)
│   │   └── engine.py               # AISEngine (budget, rewards, spending)
│   │
│   ├── monitoring/                 # ✨ NEW: Monitoring & Observability (Phase 26)
│   │   ├── __init__.py             # Package init & public API re-export
│   │   ├── metrics.py              # 12 Prometheus metrics + fail-open recording
│   │   └── middleware.py           # Optional FastAPI HTTP middleware
│   │
│   ├── cgrf/                       # CGRF CLI Validator
│   │   ├── __init__.py
│   │   ├── __main__.py
│   │   ├── cli.py                  # 3 commands: validate/tier-check/report
│   │   ├── validator.py            # Tier 0-3 validation logic
│   │   └── README.md               # CGRF CLI documentation
│   │
│   ├── a2a/
│   │   ├── protocol.py
│   │   └── agent_wrapper.py
│   │
│   ├── llm/
│   │   ├── client.py
│   │   └── prompts.py
│   │
│   ├── memory/
│   │   ├── store_v2.py             # RAG memory (old store.py is backed up in old/)
│   │   ├── vector_store.py         # FAISS vector memory
│   │   └── corpus.json
│   │
│   ├── execution/
│   │   ├── runner_V2.py            # generates verify_results.json (old runner.py is backed up in old/)
│   │   └── outcome_store.py
│   │
│   ├── audit/
│   │   ├── report.py               # Added CGRF metadata output
│   │   └── logger.py
│   │
│   ├── approval/
│   │   ├── request.py
│   │   └── response.py
│   │
│   ├── governance/
│   │   ├── policies.yaml
│   │   └── policy_engine.py
│   │
│   ├── reflex/
│   │   ├── manifest.yaml
│   │   └── dispatcher.py
│   │
│   ├── ingest/
│   │   ├── normalizer.py
│   │   ├── webhook.py
│   │   └── outbox.py
│   │
│   ├── github/
│   │   └── client.py               # ✨ UPDATED: CI wait + auto-merge
│   │
│   ├── streaming/
│   │   └── emitter.py
│   │
│   ├── mcp_server/
│   │   └── server.py
│   │
│   ├── dashboard/
│   │   ├── index.html
│   │   ├── app.js
│   │   └── style.css
│   │
│   ├── azure/
│   │   ├── config.py
│   │   ├── servicebus_adapter.py
│   │   ├── foundry_agents.py
│   │   ├── cosmos_memory.py
│   │   └── telemetry.py
│   │
│   ├── roadmap_ir/                    # ✨ Roadmap IR Schema (MS-1)
│   │   ├── schema.json               # JSON Schema Draft 2020-12
│   │   ├── types.py                   # Pydantic v2 models
│   │   └── validators.py             # Semantic validation
│   │
│   ├── roadmap_translator/            # ✨ Roadmap Translator (MS-2)
│   │   ├── cli.py                     # translate --in ... --out ...
│   │   ├── pipeline.py                # Ingest→Detect→Translate→Normalize→Merge→Validate→Emit
│   │   ├── enricher.py                # ✨ IR enrich (GGUF/rule-based) (MS-8)
│   │   ├── detect.py                  # ✨ Generic/Gitlog fallback detection (MS-8)
│   │   └── translators/
│   │       ├── readme.py              # README latest implementation → items
│   │       ├── markdown_roadmap.py    # Phase N: → items
│   │       ├── implementation_summary.py  # Impl Summary → items
│   │       ├── generic_markdown.py    # ✨ Generic Markdown fallback (MS-8)
│   │       └── gitlog.py              # ✨ git log → EvidenceGit items (MS-8)
│   │
│   ├── roadmap/                       # ✨ Roadmap utilities (MS-8)
│   │   └── gguf_engine.py             # GGUF local inference + rule-based fallback
│   │
│   ├── mca/                           # ✨ MCA Evolution Engine (MS-4/MS-7)
│   │   ├── cli.py                     # evolve --meta ... --dry-run
│   │   ├── evolution_engine.py        # 7Phase orchestration
│   │   ├── metrics_aggregator.py      # Unified metrics snapshot
│   │   ├── notion_bridge.py           # ✨ Notion/Supabase bridge (MS-7)
│   │   ├── professors/               # Mirror, Oracle, Government (Bedrock)
│   │   │   ├── bedrock_adapter.py     # BedrockProfessorBase mixin
│   │   │   ├── prof_mirror.py         # Code pattern + coverage analysis
│   │   │   ├── prof_oracle.py         # Strategic guidance + health
│   │   │   └── prof_government.py     # CAPS compliance + proposal governance
│   │   └── proposals/
│   │       └── models.py              # EP-CODE/RAG/SALES/STALE/GAP
│   │
│   ├── contracts/                     # ✨ A2A Event JSON v1 contract (modified)
│   │   ├── handoff_packet.py          # HandoffPacket with jsonschema validation
│   │   ├── handoff_packet_contract.py # __post_init__ required field check
│   │   └── decision_contract.py       # ISO 8601 'T' separator enforcement
│   │
│   └── infra/                         # ✨ Infrastructure (MS-4/MS-7)
│       ├── bedrock_professor_client.py  # AWS Bedrock Claude client
│       ├── notion_mca_client.py         # ✨ Notion API (EVO tracker, ZES RAG DB) (MS-7)
│       └── supabase_mca_mirror.py       # ✨ Supabase REST mirror (MS-7)
│
├── tests/
│   ├── test_sentinel_v2.py        # Tier 1 unit tests (9 tests)
│   ├── test_sherlock_v3.py        # (12 tests)
│   ├── test_fixer_v3.py           # (13 tests)
│   ├── test_guardian_v3.py        # (9 tests)
│   ├── test_ags.py                # AGS unit tests (17 tests) - Phase 24
│   ├── test_ais.py                # AIS unit tests (25 tests) - Phase 25
│   ├── test_monitoring.py         # Monitoring unit tests (15 tests) - Phase 26
│   ├── test_mca_engine.py         # MCA Evolution Engine (18 tests) - MS-4
│   ├── test_mca_professors.py     # MCA Professors (21 tests) - MS-4
│   ├── test_mca_proposals.py      # MCA Proposals (16 tests) - MS-4
│   ├── test_notion_mca_client.py  # ✨ Notion MCA Client (40 tests) - MS-7
│   ├── test_supabase_mca_mirror.py # ✨ Supabase Mirror (14 tests) - MS-7
│   ├── test_notion_bridge.py      # ✨ Notion Bridge (21 tests) - MS-7
│   ├── test_generic_markdown_translator.py  # ✨ Generic Markdown (~12 tests) - MS-8
│   ├── test_gguf_engine.py        # ✨ GGUF Engine (~10 tests) - MS-8
│   ├── test_a2a_protocol.py       # (5 tests)
│   ├── test_execution.py          # (3 tests)
│   ├── test_pipeline_e2e.py       # (4 tests — faiss/numpy compatibility dependent)
│   ├── contracts/                 # ✨ A2A Event JSON v1 contract tests (modified 2026-02-28)
│   │   ├── test_handoff_packet.py
│   │   └── test_decision_contract.py
│   └── integration/               # Phase 23 Integration Tests (41 tests)
│       ├── test_a2a_handoff.py              # A2A pipeline integration (4 tests)
│       ├── test_sentinel_v2_integration.py  # Sentinel integration (4 tests)
│       ├── test_sherlock_v3_integration.py  # Sherlock integration (6 tests)
│       ├── test_fixer_v3_integration.py     # Fixer integration (7 tests)
│       ├── test_guardian_v3_integration.py  # Guardian integration (8 tests)
│       ├── test_memory_recall.py            # Memory integration (5 tests)
│       └── test_execution_verify.py         # Execution & verification integration (7 tests)
│
├── out/                            # Execution results directory
│   └── <event_id>/
│       ├── handoff_packet.json
│       ├── handoff_packet.attempt_N.json  # ✨ Retry attempt file
│       ├── decision.json
│       ├── audit_report.json              # ✨ includes cgrf_metadata
│       ├── verify_results.json            # ✨ verification results
│       └── execution_outcome.json
│
├── cgrf.py                         # ✨ NEW: CGRF CLI entry point
├── IMPLEMENTATION_SUMMARY_20260211.md  # ✨ NEW: Summary of today's achievements
└── README_merged_r2.md             # This file
```

---

## Quick Start

### Run the demo (all events)

```bash
python demo/run_demo.py
```

**Example output** (with CGRF Tier display):

```
✓ Sentinel V2: classification=incident, severity=medium
  [CGRF]: Tier 1 (Development) | Module: sentinel_v2 v2.1.0

✓ Sherlock V3: hypotheses=2, confidence=0.85, label=deps_missing
  [CGRF]: Tier 1 (Development) | Module: sherlock_v3 v3.0.0

✓ Fixer V3: fix_plan="Install missing dependencies...", risk=0.2
  [CGRF]: Tier 1 (Development) | Module: fixer_v3 v3.0.0

✓ Guardian V3: action=approve, risk_score=0.125
  [CGRF]: Tier 2 (Production) | Module: guardian_v3 v3.0.0

Pipeline completed in 78.4ms
```

### Enable auto-execution and auto-merge

```bash
# ON/OFF switch (config/settings.yaml)
auto_execution:
  enabled: true              # Auto-execution ON/OFF
  auto_merge:
    enabled: true            # Auto-merge ON/OFF
    max_risk_threshold: 0.25 # Risk threshold (< 0.25 for auto-merge)
    ci_wait_timeout: 300     # CI wait time (seconds)
    merge_method: squash     # Merge method (squash/merge/rebase)
    exclude_branches:        # Excluded branches
      - main
      - master
      - production
    exclude_event_types:     # Excluded events
      - security_alert
      - deploy_failed

Workflow:

Event → Guardian judgment (risk < 0.25)
              ↓
          PR auto-creation
              ↓
          Wait for CI completion
              ↓
        CI success → Auto-merge
```

Details: docs/AUTO_EXECUTION.md

### Run a single event

```bash
python demo/run_demo.py demo/events/ci_failed.sample.json
```

### Run with Orchestrator V3 (Verify Retry enabled)

```bash
python -m src.orchestrator_v3 demo/events/ci_failed.sample.json
```

### Validate with CGRF CLI

```bash
# Validate a single module
python cgrf.py validate --module src/agents/sentinel_v2.py --tier 1

# Batch validate multiple modules
python cgrf.py tier-check src/agents/*.py --tier 1

# Compliance report for all modules
python cgrf.py report --tier 1
```

Details: [src/cgrf/README.md](src/cgrf/README.md)

### Run FastAPI server

```bash
uvicorn src.app:app --reload
```

### Run MCP server (for Claude Desktop / VS Code)

```bash
python -m src.mcp_server.server
```

### Execute MCA Evolution Cycle

```bash
# Basic execution (dry-run)
python -m src.mca.cli evolve --meta config/mca_meta_001.yaml --dry-run

# With metrics + specify output file
python -m src.mca.cli evolve --meta config/mca_meta_001.yaml \
  --files 120 --lines 15000 --tests 68 \
  --out out/mca_evolution.json --dry-run

# Roadmap IR integration (expected to be completed in MS-5)
python -m src.mca.cli evolve --roadmap-ir roadmap_ir.json --dry-run
```

The following environment variables are required in `.env` for AWS Bedrock connection:

```bash
AWS_BEDROCK_ACCESS_KEY_ID=...
AWS_BEDROCK_SECRET_ACCESS_KEY=...
AWS_BEDROCK_REGION=us-east-1
```### Run the Roadmap Translator

```bash
python -m src.roadmap_translator.cli translate \
  --in README.md EVOLUTION_ROADMAP.md IMPLEMENTATION_SUMMARY.md \
  --out roadmap_ir.json --report roadmap_ir.report.md
```

### Run Tests

```bash
pytest tests/ -v
```

**Test Configuration**:

- `test_pipeline_e2e.py` - 4 E2E tests (ci_failed, security_alert, deploy_failure, verify_retry)
- `test_a2a_protocol.py` - 5 A2A protocol tests
- `test_execution.py` - 3 execution backend tests
- `test_sentinel_v2.py` - 9 unit tests
- `test_sherlock_v3.py` - 12 unit tests
- `test_fixer_v3.py` - 13 unit tests
- `test_guardian_v3.py` - 9 unit tests
- `test_ags.py` - 17 AGS unit tests (Phase 24)
- `test_ais.py` - 25 AIS unit tests (Phase 25)
- `test_monitoring.py` - 15 Monitoring unit tests (Phase 26)
- `test_cgrf_cli_json.py` - **8 CGRF CLI JSON tests** ✨ Phase 27
- `tests/integration/` - 41 integration tests (7 files) (Phase 23)
- `test_mca_engine.py` - **18 MCA Engine tests** ✨ MS-4
- `test_mca_professors.py` - **21 MCA Professor tests** ✨ MS-4
- `test_mca_proposals.py` - **16 MCA Proposal tests** ✨ MS-4
- `test_notion_mca_client.py` - **40 Notion MCA Client tests** ✨ MS-7
- `test_supabase_mca_mirror.py` - **14 Supabase Mirror tests** ✨ MS-7
- `test_notion_bridge.py` - **21 Notion Bridge tests** ✨ MS-7
- `test_generic_markdown_translator.py` - **~12 Generic Markdown tests** ✨ MS-8
- `test_gguf_engine.py` - **~10 GGUF Engine tests** ✨ MS-8
- `tests/contracts/` - A2A Event JSON v1 contract tests (handoff_packet, etc.)
- Subsystem tests for Nemesis/Mike/F993, etc.
- **Total: 1310 passed (Full suite as of 2026-03-06, +177 VCC/OAD/Perplexity/Nemesis tests)** ✅

> **CI conditions**: Run with `pytest tests/ -q` from the repo root (requires `pytest.ini` at root). `test_pipeline_e2e.py` auto-skips when `localhost:1234` (local LLM) is unavailable — safe in standard CI without a running model server.

### Environment Variables (Optional, Enhance AI for All Agents)

```bash
# Azure OpenAI (recommended)
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_KEY=your-key
AZURE_OPENAI_DEPLOYMENT=gpt-4o

# Or OpenAI directly
OPENAI_API_KEY=sk-...

# AWS Bedrock (for MCA Professors)
AWS_BEDROCK_ACCESS_KEY_ID=...
AWS_BEDROCK_SECRET_ACCESS_KEY=...
AWS_BEDROCK_REGION=us-east-1

# GitHub execution (for actual PR creation)
GITHUB_TOKEN=ghp_...
```

If LLM keys are set, all four agents will generate AI-driven analyses based on natural language reasoning. If no keys are present, the system will fall back to rule-based logic — same pipeline, same contracts, same outputs.

---

## CGRF v3.0 Governance Framework ✨

**CGRF (Complete Governance & Reflex Framework)** is a tiered governance framework for autonomous systems.

### Tier System

| Tier | Name               | Test Coverage | Implementation Time | Requirements                         |
| ---- | ---------------- | -------- | ---- | -------------------------- |
| 0    | Experimental     | 0%       | <5 min  | Basic structure only                     |
| 1    | Development      | 50% target    | ~2 hours | docstring, metadata, unit tests |
| 2    | Production       | 80% target    | 1-2 days | Integration tests, policy compliance               |
| 3    | Mission-Critical | 95% target    | ~1 week | E2E tests, audit trails, full governance        |

### CGRF Metadata (Implemented for All Agents)

Each agent outputs CGRF v3.0 metadata:

```python
@dataclass
class CGRFMetadata:
    report_id: str          # "SRS-SENTINEL-20260211-001-V3.0"
    tier: int               # 0-3
    module_version: str     # "2.1.0"
    module_name: str        # "sentinel_v2"
    execution_role: str     # "BACKEND_SERVICE"
    created: str            # ISO timestamp
    author: str             # "agent" | "human"
    last_updated: str       # ISO timestamp (optional)
```

**Current Implementation Status** (Post Phase 23 Completion):

- Sentinel V2: **Tier 2 (Production)** ✅
- Sherlock V3: **Tier 2 (Production)** ✅
- Fixer V3: **Tier 2 (Production)** ✅
- Guardian V3: **Tier 2 (Production)** ✅

### CGRF CLI Validator

Command-line tool to validate CGRF compliance of modules:

```bash
# Detailed validation report
python cgrf.py validate --module src/agents/sentinel_v2.py --tier 1

# Batch validation
python cgrf.py tier-check src/agents/*.py --tier 1

# Overall report
python cgrf.py report --tier 1
```

**Validation Items** (Tier 1):

- ✅ **parse**: Parsable with Python AST
- ✅ **module_docstring**: Module docstring required
- ✅ **cgrf_metadata**: Complete metadata, Tier match
- ✅ **test_file**: Corresponding test file exists

Details: [src/cgrf/README.md](src/cgrf/README.md)

---

## REFLEX Self-Healing System ✨

**REFLEX (5-stage pipeline)**: Observe → Diagnose → Respond → Verify → Learn

### Verify Retry Feature of Orchestrator V3

`src/orchestrator_v3.py` automatically retries on verification failure:

```python
# Maximum 2 attempts, auto-retry on verification failure
max_attempts = 2
attempt_no = 1

while attempt_no <= max_attempts:
    # Run pipeline
    run_pipeline()

    # Check verification results
    verify_results = read_verify_results()

    if verify_results["all_success"]:
        break  # Success → Done

    if attempt_no < max_attempts:
        # Inject feedback and retry
        inject_verify_feedback()
        attempt_no += 1
        continue

    # Final attempt failed → Exit
    break
```

**Generated Files**:

- `out/<event_id>/handoff_packet.attempt_1.json` - Result of attempt 1
- `out/<event_id>/audit_report.attempt_1.json` - Audit of attempt 1
- `out/<event_id>/decision.attempt_1.json` - Decision of attempt 1
- `out/<event_id>/verify_results.json` - Verification results (all_success flag)
- `out/<event_id>/handoff_packet.json` - Final result (packet_artifacts.attempts array)

**E2E Test**:

```bash
pytest tests/test_pipeline_e2e.py::test_verify_retry_on_failure -v
```

---

## Demo Output

The demo executes three events through the full V3 pipeline:

### Verification Steps (verification_steps)

Fixer V3 suggests post-fix verification commands based on Sherlock's labels (e.g., `deps_missing` / `permission_denied` / `security_alert`):

**deps_missing**:

```bash
python -c "import sys; print(sys.version)"
pip install -r requirements.txt
python -c "import {module}"
```

**permission_denied**:

```bash
ls -l {file}
test -r {file} && echo OK_READ || echo NG_READ
test -x {file} && echo OK_EXEC || echo NG_EXEC
```

**security_alert**:

```bash
npm ls {package} || true
npm audit || true
npm audit fix || true
npm ls {package} || true
```

### Risk Mitigation by Guardian

Guardian V3 adjusts risk based on the presence of verification steps:

```
base_risk = (fixer_risk * 0.4) + (severity_weight * 0.3) + confidence_penalty + security_bump

mitigations:
  - verification_steps provided: -0.04
  - verification all success: -0.08

final_risk = base_risk - mitigations
```

**Audit Output** (`audit_report.json`):

```json
{
  "artifacts": {
    "guardian_risk_model": {
      "base_risk": 0.285,
      "mitigations": [
        {"id": "M_VERIFICATION_STEPS_PROVIDED", "delta": -0.04, "active": true},
        {"id": "M_VERIFICATION_PASSED", "delta": -0.08, "active": false}
      ],
      "final_risk": 0.245,
      "verify": {
        "has_steps": true,
        "has_results": false,
        "all_success": false
      }
    }
  },
  "cgrf_metadata": {
    "sentinel": {"tier": 1, "module_name": "sentinel_v2", ...},
    "sherlock": {"tier": 1, "module_name": "sherlock_v3", ...},
    "fixer": {"tier": 1, "module_name": "fixer_v3", ...},
    "guardian": {"tier": 2, "module_name": "guardian_v3", ...}
  }
}
```

### Demo Result Summary

| Event            | Severity | Confidence  | Risk Score | Decision            | CGRF Tier   |
| --------------- | --- | ---- | ------ | ------------- | ----------- |
| CI Failure (Missing Dependencies)   | Medium | 0.85 | 0.125  | **Approved** (auto)    | Tier 1 x 3  |
| Deployment Failure (Permission)      | High   | 0.90 | 0.198  | **Approved** (auto)    | Tier 1 x 3  |
| Security Alert (CVE) | Critical  | 0.90 | 0.608  | **Approval Needed** (human) | + Tier 2 x1 |

---

## Rationale for Modules

Each folder isolates a single responsibility within the pipeline. The system is designed so that all modules can run without external dependencies (local file-based backend) or switch to Azure managed services — same code path, same contracts, different backends.

### Key Module Details

**`config/`** — Configuration templates for external services. Settings are environment-specific and not application logic, hence kept outside `src/`. `azure.yaml.example` serves as documentation for Azure services the system can connect to and the credentials each requires.

**`demo/`** — Self-contained demo harness. The `events/` subfolder contains curated JSON payloads to execute different pipeline behaviors. `run_demo.py` sequentially executes all commands and provides colored terminal output (with CGRF Tier display).

**`src/types.py`** — The single source of truth for all data contracts. Defines `EventJsonV1`, `HandoffPacket`, `AgentOutput`, `Decision`, and **`CGRFMetadata`** (v3.0). All modules in the system import from here.

**`src/orchestrator_v3.py`** — A2A + memory + execution + reflex + **verify retry**. Reads `out/<event_id>/verify_results.json` and retries up to 2 times on verification failure. Saves files for each attempt and includes an attempts array in the final result.

**`src/app.py`** — FastAPI application that exposes the pipeline over HTTP. Provides webhook endpoints for GitHub Actions and Azure Alerts, raw event submission endpoints, pipeline status queries, agent registry, audit trail retrieval, listing reflex rules, and SSE streaming.

**`src/agents/`** — Four specialized agents forming the diagnostic repair pipeline. Each agent outputs **CGRF v3.0 metadata**:

1. **Sentinel V2** (Tier 1) — First responder. Classifies event types, assigns severity, and extracts signals from log text.
2. **Sherlock V3** (Tier 1) — Root cause analyst. Generates hypotheses, scores confidence based on evidence strength, and incorporates memory from past incidents.
3. **Fixer V3** (Tier 1) — Repair engineer. Proposes remediation plans, estimates risks, and generates **verification_steps**.
4. **Guardian V3** (Tier 2) — Governance gate. Calculates multi-factor risk scores, verifies against RAI policies and governance rules, and makes decisions.

Each agent operates in two modes:

- **LLM Mode**: Natural language analysis with Azure OpenAI / OpenAI
- **Rule Mode**: Pattern matching and templates

**`src/ags/`** ✨ — **AGS (Agent Governance System) Pipeline** (Phase 24). A "constitutional judiciary" layer inserted before execution after Guardian's decision. Achieves double-check governance through a 4-stage pipeline (S00 GENERATOR → S01 DEFINER → S02 FATE → S03 ARCHIVIST):

- `caps_stub.py` - CAPS grading system (D/C/B/A/S) + `get_ais_profile()` AIS bridge
- `s00_generator.py` - HandoffPacket + Decision → SapientPacket conversion
- `s01_definer.py` - Schema validation + CAPS Tier requirement checks
- `s02_fate.py` - 5 policy gates → ALLOW/REVIEW/DENY decisions
- `s03_archivist.py` - Audit hash chain records
- `pipeline.py` - AGSPipeline runner, AGSVerdict dataclass
- Design principle: Escalation only (can be strict but cannot be loosened), fail-open (availability prioritized)

**`src/ais/`** ✨ — **AIS (Agent Intelligence System) XP/TP Economy** (Phase 25). Dynamically manages agent capabilities in a Dual-Token Economy of XP/TP:

- `profile.py` - AgentProfile dataclass (XP/TP tracking, transaction logs, CAPS grade auto-resolution)
- `storage.py` - ProfileStore (file-based JSON persistence, `data/ais/profiles/{agent_id}.json`)
- `costs.py` - CostTable (TP costs per action: approve_fix=50, create_pr=70, deploy=90)
- `rewards.py` - RewardCalculator (Tier multipliers, Quality bonus +50%, Critical TP, Low risk bonus)
- `engine.py` - AISEngine (budget checks, reward recording, TP spending, fail-open)
- Design principle: fail-open (fallback to CAPS stub default on error), per-agent tracking

**`src/monitoring/`** ✨ — **Monitoring & Observability** (Phase 26/MS-7). Prometheus metrics output and Grafana dashboard integration:

- `metrics.py` - 16 Prometheus metric definitions (12 DevOps + 4 MCA), isolated CollectorRegistry, fail-open recording functions
  - MS-7 additions: `citadel_mca_evolution_proposals_total`, `citadel_mca_evolution_proposals_approved`, `citadel_mca_domain_health_score`, `citadel_mca_evolution_cycle_duration_seconds`
- `middleware.py` - Optional FastAPI HTTP middleware (`citadel_http_request_duration_seconds`)
- Supports Prometheus scraping at the `/metrics` endpoint
- Design principle: fail-open (all features work even if `prometheus_client` is not installed), isolated registry (test safe)

**`grafana/`** ✨ — **Grafana Dashboard** (Phase 26). Provisioning JSON to visualize Prometheus metrics:

- `citadel_dashboard.json` - 11 panels across 4 sections (Pipeline Overview, Agent Activity, Governance, Auto-Merge)
- Pipeline runs rate, in-flight gauge, latency percentiles, agent invocations, XP/TP/grade, AGS verdicts, risk distribution

**`src/cgrf/`** ✨ — **CGRF v3.0 CLI Validator**. Command-line tool to validate CGRF Tier compliance of modules:

- `cli.py` - 3 commands (validate, tier-check, report)
- `validator.py` - Tier 0-3 validation logic
- Tier requirement checks: parse, docstring, cgrf_metadata, test_file, integration_tests, e2e_tests
- Color-coded output (Tier 0=DIM, 1=CYAN, 2=YELLOW, 3=RED)
- Windows console support

**`src/a2a/`** — Handoff protocol between agents. Dispatches `A2AMessage` objects through a protocol layer that handles agent registration, capability discovery, message routing, and execution tracing instead of the orchestrator directly calling agents.

**`src/llm/`** — LLM abstraction layer. `client.py` implements `LLMClient` with a multi-backend fallback chain: Azure OpenAI → OpenAI directly → graceful failure (agents fall back to rules).

**`src/memory/`** — Incident memory for learning through pipeline execution. `store_v2.py` provides `recall(query, k)` and `remember(event_id, summary, tags, outcome)`. The orchestrator recalls memory before Sherlock runs.

**`src/execution/`** — The layer that "closes the loop." `runner_V2.py` implements backend strategy patterns:

- `DryRunExecutionBackend` - Logs actions (demo/test)
- `LocalExecutionBackend` - Writes JSON artifacts to disk
- `GitHubExecutionBackend` - Creates actual branches, opens PRs

**`runner_V2.py` generates `verify_results.json`** (execution results of verification steps, `all_success` flag):

```json
{
  "schema_version": "verify_results_v0",
  "event_id": "demo-ci-failed-001",
  "results": [
    {"step": "python -c 'import sys'", "success": true, "output": "3.11.0"},
    {"step": "pip install -r requirements.txt", "success": true, "simulated": true}
  ],
  "all_success": true,
  "simulated": true
}
```

**`src/audit/`** — Tamper-evident audit trails. `report.py` generates audit report JSON containing **CGRF metadata**. `logger.py` implements a SHA-256 hash chain audit logger.

**`src/approval/`** — Human-in-the-loop approval workflow. When Guardian returns `need_approval`, the orchestrator uses this module to request human review before execution proceeds.**`src/governance/`** — Responsible AI policy framework. `policies.yaml` declares six RAI principles, five governance rules, and three compliance mappings. `policy_engine.py` loads the engine at runtime.

**`src/reflex/`** — Automation rules after decisions. `manifest.yaml` declares rules that trigger after Guardian's decisions based on event type, severity, and risk score. `dispatcher.py` reads the manifest and matches rules against the current event/decision.

**`src/ingest/`** — Event ingestion and normalization. `normalizer.py` converts payloads from different sources into the standard `EventJsonV1` format. `outbox.py` implements a file-based outbox pattern.

**`src/github/`** — GitHub REST API integration for actual execution. It handles branch creation, file commits, opening pull requests, retrieving workflow logs, re-triggering failed CI workflows, and verifying webhook signatures.

**`src/streaming/`** — Real-time pipeline observation via server-sent events. `emitter.py` emits events that any SSE client can consume in real-time.

**`src/mcp_server/`** — Model Context Protocol server. `server.py` exposes the pipeline as six tools and two resources, callable by any MCP-compatible client (such as Claude Desktop, VS Code with Copilot).

**`src/dashboard/`** — Web-based control panel. It provides an event submission form, visualization of pipeline stage progress, agent output cards, risk gauges, audit trail display, memory panel, and agent registry.

**`src/azure/`** — Azure service backend. Each file implements the same ABC/interface as the local backend but is backed by Azure services.

**`src/roadmap_ir/`** ✨ — **Roadmap IR Schema** (MS-1). Common contract for the entire system (JSON Schema Draft 2020-12 + Pydantic v2):

- `schema.json` - JSON Schema definitions (Source, Catalog, Item, Evidence, Conflict, Note, Metrics)
- `types.py` - Pydantic v2 models (7 enums, 16 models, Evidence union)
- `validators.py` - Semantic validation (prohibiting ID duplication, enforcing status=unknown for items without evidence, cycle detection)
- 31 tests, CGRF Tier 1

**`src/roadmap_translator/`** ✨ — **Roadmap Translator** (MS-2). Deterministic (non-LLM) document → IR conversion pipeline:

- `pipeline.py` - 7-step orchestration: Ingest→Detect→Translate→Normalize→Merge→Validate→Emit
- `translators/readme.py` - README `**Latest Implementation**` → item extraction
- `translators/markdown_roadmap.py` - RoadMap `### Phase N:` → item extraction
- `translators/implementation_summary.py` - Impl Summary `### N. title ✅` → item extraction
- `cli.py` - `translate --in ... --out roadmap_ir.json --report roadmap_ir.report.md`
- 37 tests, all 12 modules CGRF Tier 1

**`src/mca/`** ✨ — **MCA Evolution Engine** (MS-4). Automated evolution cycle by AI professors:

- `evolution_engine.py` - 7Phase orchestration (Data→Meta→Metrics→AI→Proposals→SANCTUM→Publisher)
- `metrics_aggregator.py` - Integrated snapshot of code/plan/Phase/IR metrics
- `professors/bedrock_adapter.py` - `BedrockProfessorBase` mixin (Claude Opus 4.5 via AWS Bedrock)
- `professors/prof_mirror.py` - Mirror professor: code pattern + plan coverage analysis
- `professors/prof_oracle.py` - Oracle professor: strategic guidance + health assessment + tier coverage
- `professors/prof_government.py` - Government professor: CAPS compliance + proposal approval/rejection + enum_tags
- `proposals/models.py` - `EvolutionProposal` (EP-CODE/EP-RAG/EP-SALES/EP-STALE/EP-GAP) + 5 factory functions
- `cli.py` - `evolve --meta ... --roadmap-ir ... --out ... --dry-run`
- 55 tests, all 9 modules CGRF Tier 1
- Design principle: Professors extend ProfessorBase with `BedrockProfessorBase` mixin (preserving original OpenAI path)

**`src/infra/`** ✨ — **Infrastructure** (MS-4/MS-7). External service clients:

- `bedrock_professor_client.py` - AWS Bedrock Claude calls (boto3, retry, `load_dotenv()` support)
- Environment variables: `AWS_BEDROCK_ACCESS_KEY_ID`, `AWS_BEDROCK_SECRET_ACCESS_KEY`, `AWS_BEDROCK_REGION`
- `notion_mca_client.py` ✨ - Notion API client (MS-7): Block addition to EVO Tracker page, record registration to ZES RAG DB, direct requests
- `supabase_mca_mirror.py` ✨ - Supabase REST mirror (MS-7): `automation_events` + `mca_proposals` tables, direct REST calls independent of supabase-py
- Environment variables (MS-7): `NOTION_TOKEN`, `NOTION_EVO_TRACKER_PAGE_ID`, `NOTION_ZES_RAG_DB_ID`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`
- Design principle: Graceful no-op when credentials are not set, testable with `dry_run=True`

**`src/mca/notion_bridge.py`** ✨ — **Notion/Supabase Bridge** (MS-7). Bridge layer to synchronize MCA proposals to Notion + Supabase:

- `publish_proposal()` - EvolutionProposal → Notion EVO Tracker + ZES RAG DB + Supabase three-point synchronization
- 40 + 14 + 21 = **75 tests** (test_notion_mca_client / test_supabase_mca_mirror / test_notion_bridge)
- 4 MCA Prometheus metrics added: `citadel_mca_evolution_proposals_total`, `citadel_mca_evolution_proposals_approved`, `citadel_mca_domain_health_score`, `citadel_mca_evolution_cycle_duration_seconds`

**`src/roadmap/gguf_engine.py`** ✨ — **GGUF Local Inference Engine** (MS-8). Automatically falls back to rule-based when `llama_cpp` is not installed:

- `load_model()` - Loads model from `CITADEL_GGUF_MODEL` environment variable, returns `None` on failure
- `generate_text(prompt)` - With model: `Llama.create_completion()`, without model: rule-based
- `summarize(text)` - Trims to the first 150 characters
- `generate_risk(text)` - Generates risk string from "blocked"/"dependency"/"not implemented" keywords
- `recommend(status, verify)` - Generates template from status/verify combinations

**`src/roadmap_translator/enricher.py`** ✨ — **IR Enricher** (MS-8). Automatically enriches each Item of Roadmap IR with GGUF:

- `enrich_ir(ir, engine)` - Adds `summary`, `recommendations`, `risk_notes` to `raw`
- Automatically calls `gguf_engine.load_model()` when engine is not specified

**`src/roadmap_translator/translators/generic_markdown.py`** ✨ — **Generic Markdown Translator** (MS-8). Fallback for `.md` files unmatched by other Translators:

- Extracts Items from headings (H1 to H6) + numbered/bulleted lists
- Status detection: `✅`→done, `TODO/[ ]/planned`→planned, `blocked/🚫`→blocked, `WIP/in_progress`→in_progress, others→unknown
- Retains parent heading hierarchy in `raw.hierarchy_path`
- item_id: `generic-{slug}`

**`src/roadmap_translator/translators/gitlog.py`** ✨ — **Gitlog Translator** (MS-8). Generates Items with `EvidenceGit` from `git log` text output:

- Input: Output of `git log --pretty=format:"%H%n%an%n%ai%n%s" --name-only`
- `FILE_PHASE_MAP`: Fallback estimation dictionary mapping file patterns to Phase numbers
- item_id: `git-{commit[:7]}`

**`ci/translate_evolve_publish.sh`** ✨ — **CI Bulk Script** (MS-8). GitHub Actions / GitLab CI compatible script for translate → evolve → publish:

- Supports environment variables: `CITADEL_DRY_RUN`, `CITADEL_GGUF_MODEL`, `NOTION_TOKEN`, `SUPABASE_URL`
- Exits with code 1 on error

**`src/contracts/`** ✨ — **A2A Event JSON v1 Contract** (Revised 2026-02-28). Type-safe A2A handoff contract:

- `handoff_packet.py` - `source_agent_id`/`target_agent_id`/`payload` fields, jsonschema structural validation, raises `jsonschema.ValidationError` with `from_dict()`
- `handoff_packet_contract.py` - `id`/`timestamp`/`payload` fields, raises `ValueError("Missing required fields: [...]")` in `__post_init__`, supports `to_json()` / `from_json()`
- `decision_contract.py` - Enforces ISO 8601 'T' separator (explicitly rejects whitespace separation)

**`vscode-extension/`** ✨ — **VS Code Extension** (Phase 27). Real-time IDE validation for CGRF Tier:

- `citadel-cgrf/src/extension.ts` - Entry point (command registration, onSave, editor change handler)
- `citadel-cgrf/src/cgrfRunner.ts` - `python cgrf.py validate --json` subprocess + JSON parse
- `citadel-cgrf/src/statusBar.ts` - Status bar Tier display (compliant=green, error=red)
- `citadel-cgrf/src/diagnostics.ts` - CGRF validation failure → VS Code Problems panel
- `citadel-cgrf/src/codeLens.ts` - Tier badge CodeLens on `_CGRF_TIER = N` definition line
- `citadel-cgrf/src/config.ts` - Extension settings management

**`tests/`** — Automated validation. 1310 tests passed (as of 2026-03-06):

- `test_pipeline_e2e.py` - 4 E2E tests
- `test_a2a_protocol.py` - 5 A2A tests
- `test_execution.py` - 3 execution tests
- `test_sentinel_v2.py` - 9 unit tests
- `test_sherlock_v3.py` - 12 unit tests
- `test_fixer_v3.py` - 13 unit tests
- `test_guardian_v3.py` - 9 unit tests
- `test_ags.py` - 17 AGS unit tests (Phase 24 + 1 AIS integration test)
- `test_ais.py` - 25 AIS unit tests (Phase 25)
- `test_monitoring.py` - 15 Monitoring unit tests (Phase 26)
- `test_cgrf_cli_json.py` - 8 CGRF CLI JSON tests ✨ Phase 27
- `test_mca_engine.py` - 18 MCA Evolution Engine tests ✨ MS-4
- `test_mca_professors.py` - 21 MCA Professor tests ✨ MS-4
- `test_mca_proposals.py` - 16 MCA Proposal tests ✨ MS-4
- `test_notion_mca_client.py` - 40 Notion MCA Client tests ✨ MS-7
- `test_supabase_mca_mirror.py` - 14 Supabase Mirror tests ✨ MS-7
- `test_notion_bridge.py` - 21 Notion Bridge tests ✨ MS-7
- `test_generic_markdown_translator.py` - ~12 Generic Markdown tests ✨ MS-8
- `test_gguf_engine.py` - ~10 GGUF Engine tests ✨ MS-8
- `tests/contracts/` - A2A Event JSON v1 contract tests ✨ (Revised 2026-02-28)
- `tests/integration/` - 41 integration tests (7 files) (Phase 23)
- Subsystem tests for Nemesis/Mike/F993, etc.

---

## LLM-Driven Dual-Mode Agents

All V3 agents follow the same pattern: **Try LLM first, fallback to rules**.

```
Request → LLMClient.complete(system_prompt, context)
              │
         ┌────┴────┐
         │ Success   │ → Returns structured JSON (AI-generated) + cgrf_metadata
         └────┬────┘
              │ Failure / No API key
              ▼
         Rule-based logic → Returns structured JSON (template-based) + cgrf_metadata
```

### LLM Backend Chain

```
DevOps Agent:
  Azure OpenAI (AZURE_OPENAI_ENDPOINT)
      ↓ Unavailable
  OpenAI Direct (OPENAI_API_KEY)
      ↓ Unavailable
  Rule-based fallback (no external dependencies)

MCA Professors:
  AWS Bedrock (Claude Opus 4.5)
      ↓ Unavailable
  Returns None → EvolutionEngine is skipped
```

Each agent has a dedicated system prompt with a structured JSON output schema:

- **Sentinel**: Incident detection, classification, prioritization + CGRF metadata (Tier 1)
- **Sherlock**: Root cause inference and hypothesis generation, confidence scores, evidence chains + CGRF metadata (Tier 1)
- **Fixer**: Remediation plans, risk assessments, rollback strategies, patch generation, **verification_steps** + CGRF metadata (Tier 1)
- **Guardian**: Governance decisions, policy compliance, RAI assessments, **guardian_risk_model** + CGRF metadata (Tier 2)

All responses include `llm_powered: true/false` and `llm_usage` metrics when AI is active.

---

## MCP Server (Model Context Protocol)

Exposes the pipeline as tools for any MCP-compatible client (Claude Desktop, VS Code, etc.).

### Tools

| Tool                        | Description                                |
| -------------------------- | --------------------------------- |
| `citadel_run_pipeline`     | Executes the full pipeline against events               |
| `citadel_diagnose`         | Runs Sentinel + Sherlock against event descriptions |
| `citadel_propose_fix`      | Runs Fixer against diagnostics                    |
| `citadel_check_governance` | Runs Guardian against remediation proposals               |
| `citadel_recall_memory`    | Searches incident memory                      |
| `citadel_audit_trail`      | Retrieves the audit chain of events                    |

### Resources

| URI                  | Description                   |
| -------------------- | -------------------- |
| `citadel://agents`   | List of registered agents and their capabilities |
| `citadel://policies` | Governance policies and compliance mappings    |

### Claude Desktop Configuration

```json
{
  "mcpServers": {
    "citadel-lite": {
      "command": "python",
      "args": ["-m", "src.mcp_server.server"],
      "cwd": "/path/to/citadel_lite"
    }
  }
}
```

---

## Web Dashboard

The real-time single-page dashboard is located at `src/dashboard/index.html`:

- **Event Submission Form** — Triggers the pipeline from the browser
- **Pipeline Progress** — Live tracking of stages (Sentinel → Sherlock → Fixer → Guardian → Execution)
- **Agent Output Cards** — Expandable JSON results from each agent + **CGRF metadata**
- **Governance Panel** — Risk gauges, decision displays, policy references, **guardian_risk_model**
- **Audit Trail** — Visualization of hash chains with integrity status
- **Memory Panel** — Recalled incidents and similarity scores
- **Agent Registry** — All registered A2A agents and their capabilities

It features a dark theme, is connected via SSE for real-time updates, and has a polling fallback.

---

## SSE Pipeline Streaming

Live pipeline observation through real-time server-sent event streaming:

```
GET /stream/{event_id}  →  SSE stream of PipelineEvent messages
```

Event types: `stage_start`, `stage_complete`, `agent_output`, `decision`, `error`, `pipeline_complete`

Used by the web dashboard and available to any SSE-compatible client.

---

## GitHub Integration

`src/github/client.py` provides actual GitHub execution:

- **Creating Fix PRs** — Branch creation, file commits, opening PRs (end-to-end)
- **Workflow Logs** — Retrieval of CI/CD execution logs for diagnostics
- **Re-running Workflows** — Re-triggering failed CI after fixes
- **Webhook Verification** — Verification of HMAC-SHA256 signatures

Set `GITHUB_TOKEN` and `EXECUTION_MODE=github` to enable live PR creation.

---

## Architecture

### Pipeline Flow (CGRF v3.0 Integration)

```
External Event → Normalization → Outbox → Orchestrator V3
                                            │
                    ┌───────────────────────┤
                    ▼                       ▼
              Memory Recall              A2A Protocol
                    │                      │
                    ▼                      ▼
              ┌─────────┐  ┌─────────┐  ┌───────┐  ┌──────────┐
              │Sentinel │→│ Sherlock │→│ Fixer  │→│ Guardian  │
              │ Detection & │  │Diagnosis │  │Suggestion │  │Governance│
              │ Classification │  │Root Cause │  │ Correction │  │  Gate   │
              │Tier 1   │  │Tier 1   │  │Tier 1 │  │  Tier 2  │
              └─────────┘  └─────────┘  └───────┘  └──────────┘
                   ↓             ↓           ↓           ↓
              CGRF Meta    CGRF Meta   CGRF Meta   CGRF Meta
                                                         │
                                                    Guardian Decision
                                                         │
                                                         ▼
                                                ┌──────────────┐
                                                │  AGS Pipeline │ ✨ Phase 24
                                                │  S00→S01→S02  │
                                                │  →S03         │
                                                │ Escalation    │
                                                │  Dedicated Check │
                                                └──────┬───────┘
                                                       │
                              ┌─────────────────────────┤
                              ▼              ▼           ▼
                          Approval       Approval Needed      Block
                              │              │           │
                              ▼              ▼           ▼
                     Reflexive Dispatch   Human Gate    Stop + Report
                              │              │
                              ▼              ▼
                         Execute          Execute
                         (PR/CI)      (If Approved)
                              │
                              ▼
                    ExecutionRunner (runner_V2.py)
                              │
                              ▼
                    verify_results.json Generation
                              │
                              ▼
                    ┌─────────┴─────────┐
                    ▼                   ▼
              all_success=true    all_success=false
                    │                   │
                    ▼                   ▼
                  Complete            retry < max_attempts?
                                        │
                              ┌─────────┴─────────┐
                              ▼                   ▼
                            Yes                 No
                              │                   │
                Inject verify_feedback          Complete
                              │              (Failed)
                         attempt += 1
                              │
                              └─→ Re-run Pipeline
```

### REFLEX 5-Stage Pipeline

```
1. Observe   → ExecutionRunner executes verification_steps
2. Diagnose  → verify_results.json generation, all_success determination
3. Respond   → Orchestrator V3 makes retry decision
4. Verify    → Re-execute on next attempt, inject verify_feedback
5. Learn     → Save success/failure patterns in Memory Store
```

### A2A Handoff Protocol

Agents communicate via `A2AMessage` objects containing a shared `HandoffPacket`. Each agent:

1. Receives the packet via `handoff()`
2. Reads upstream outputs from `packet.agent_outputs`
3. Reads memory hits from `packet.memory_hits`
4. Adds its own output + **cgrf_metadata** via `packet.add_output()`
5. Returns the updated message

### Guardian V3 — Multi-Factor Risk Scoring

```python
# Base risk calculation
base_risk = (fixer_risk * 0.4) + (severity_weight * 0.3) + confidence_penalty + security_bump

# Severity weights
severity_weight: low=0.1, medium=0.3, high=0.6, critical=0.9

# Confidence penalty
confidence_penalty: (1 - sherlock_confidence) * 0.2

# Security bump
security_bump: +0.2 if "security_vulnerability" in signals else 0.0

# Mitigations
mitigation_verification_steps = -0.04 if has_verification_steps else 0.0
mitigation_verification_passed = -0.08 if verification_all_success else 0.0

# Final risk
aggregate_risk = base_risk + mitigation_verification_steps + mitigation_verification_passed
aggregate_risk = max(0.0, min(1.0, aggregate_risk))

# Decision bands
if aggregate_risk < 0.25:
    action = "approve"
elif aggregate_risk < 0.65:
    action = "need_approval"
else:
    action = "block"
```

**Audit Output** (`guardian_risk_model`):

```json
{
  "base_risk": 0.285,
  "mitigations": [
    {"id": "M_VERIFICATION_STEPS_PROVIDED", "delta": -0.04, "active": true},
    {"id": "M_VERIFICATION_PASSED", "delta": -0.08, "active": false}
  ],
  "final_risk": 0.245,
  "verify": {
    "has_steps": true,
    "has_results": false,
    "all_success": false
  }
}
```

### Responsible AI Framework

Six RAI principles (RAI-001 to RAI-006):

- Human oversight, transparency, integrity of audit trails
- Proportional response, fail-safe defaults, memory privacy

Five governance rules (risk thresholds + security + production protection)

Three compliance mappings: Microsoft RAI standards, SOC 2 Type II, ISO 27001

### Audit Trail

Each pipeline execution generates a SHA-256 hash chain:

```
genesis → event_received → sentinel → sherlock → fixer → guardian → ags.verdict → execution → ais.rewards → completion
```

Each entry is hashed as follows: `SHA256(previous_hash + stage + timestamp + payload)`

The audit report includes a **cgrf_metadata** section:

```json
{
  "cgrf_metadata": {
    "sentinel": {
      "report_id": "SRS-SENTINEL-20260211-abc123-V2.1.0",
      "tier": 1,
      "module_version": "2.1.0",
      "module_name": "sentinel_v2",
      "execution_role": "BACKEND_SERVICE",
      "created": "2026-02-11T12:34:56Z",
      "author": "agent"
    },
    "sherlock": {...},
    "fixer": {...},
    "guardian": {...}
  }
}
```

---

## Azure Integration (Optional)

Set environment variables or copy `config/azure.yaml.example` to `config/azure.yaml`:

| Service                  | Purpose            | Environment Variable                                    |
| --------------------- | ------------- | --------------------------------------- |
| Service Bus           | Event Queue       | `AZURE_SERVICEBUS_CONNECTION`           |
| Cosmos DB             | Incident Memory     | `AZURE_COSMOS_CONNECTION`               |
| Azure OpenAI          | LLM for Agents    | `AZURE_OPENAI_ENDPOINT`                 |
| Foundry Agent Service | Agent Hosting  | `AZURE_FOUNDRY_ENDPOINT`                |
| Application Insights  | Telemetry         | `APPLICATIONINSIGHTS_CONNECTION_STRING` |
| Azure Storage         | Artifact Storage | `AZURE_STORAGE_CONNECTION`              |

If Azure is not configured, the system will run entirely locally with a file-based backend. Same code path, same contracts, different backend.

---

## API Endpoints (FastAPI)

| Method | Path                     | Description                              |
| ---- | ---------------------- | ------------------------------- |
| POST | `/webhook/github`      | GitHub Actions webhook            |
| POST | `/webhook/azure`       | Azure Alert webhook               |
| POST | `/webhook/event`       | Raw EventJsonV1 submission                 |
| GET  | `/pipeline/{event_id}` | Pipeline status + output               |
| GET  | `/stream/{event_id}`   | SSE real-time pipeline stream            |
| GET  | `/agents`              | Agent registry (cards + capabilities)           |
| GET  | `/audit/{event_id}`    | Event audit trail                       |
| GET  | `/reflex/rules`        | Active reflex rules manifest           |
| GET  | `/metrics`             | Prometheus metrics output ✨ Phase 26   |
| GET  | `/health`              | Health check (including monitoring_enabled) |

---

## Hackathon Category Coverage

| Category                             | Key Features                                                                                                                                                                                                                                                    |
| -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Grand Prize: Agentic DevOps** ($20K) | Complete closed loop: CI failure → Detection → Diagnosis → Correction → PR → CI pass. LLM-driven agents, real GitHub execution, MCP integration, **CGRF v3.0 Tier 2 Governance**, **AGS Constitutional Justice**, **AIS XP/TP Economy**, **Prometheus/Grafana Monitoring**, **VS Code Extension**, **REFLEX Self-Healing**, **Notion/Supabase Visualization**, **1310 Test Automated Validation** |
| **Best Multi-Agent System**             | A2A Protocol, Agent Registry, four LLM-driven agents (Tier 1-2), shared memory, MCP server exposing agents as tools                                                                                                                                                                            |
| **Best Use of Microsoft Foundry**      | Each agent as a Foundry Agent Service, Azure OpenAI models, structured output schema, **CGRF metadata integration**                                                                                                                                                                         |
| **Best Enterprise Solution**           | Hash chain audit, policy engine governance, reflex rules, RAI framework, web dashboard, SSE streaming, **CGRF CLI Validator**                                                                                                                                                              |
| **Best Azure Integration**                   | Service Bus, Cosmos DB, App Insights, Azure OpenAI with fallback chain, **Verify Retry Automation**                                                                                                                                                                      |
| **Best MS AI Platform**             | Foundry agents + Azure OpenAI + MCP protocol + web dashboard + GitHub integration + **CGRF Governance Framework**                                                                                                                                                                 |

---

## Testing

```
Unit Tests:
  tests/test_sentinel_v2.py    — 9 tests
  tests/test_sherlock_v3.py    — 12 tests
  tests/test_fixer_v3.py       — 13 tests
  tests/test_guardian_v3.py    — 9 tests
  tests/test_ags.py            — 17 tests (Phase 24 + 1 AIS integration)
  tests/test_ais.py            — 25 tests (Phase 25)
  tests/test_monitoring.py     — 15 tests (Phase 26)
  tests/test_cgrf_cli_json.py  — 8 tests ✨ Phase 27
  tests/test_mca_engine.py     — 18 tests ✨ MS-4
  tests/test_mca_professors.py — 21 tests ✨ MS-4
  tests/test_mca_proposals.py  — 16 tests ✨ MS-4
  tests/test_notion_mca_client.py  — 40 tests ✨ MS-7
  tests/test_supabase_mca_mirror.py — 14 tests ✨ MS-7
  tests/test_notion_bridge.py  — 21 tests ✨ MS-7
  tests/test_generic_markdown_translator.py — ~12 tests ✨ MS-8
  tests/test_gguf_engine.py    — ~10 tests ✨ MS-8
  tests/contracts/             — A2A Event JSON v1 contract tests ✨ (fixed 2026-02-28)

Integration Tests (41 tests):
  tests/integration/test_a2a_handoff.py              — 4 tests (A2A pipeline integration)
  tests/integration/test_sentinel_v2_integration.py  — 4 tests (Sentinel integration)
  tests/integration/test_sherlock_v3_integration.py  — 6 tests (Sherlock integration)
  tests/integration/test_fixer_v3_integration.py     — 7 tests (Fixer integration)
  tests/integration/test_guardian_v3_integration.py  — 8 tests (Guardian integration)
  tests/integration/test_memory_recall.py            — 5 tests (Memory integration)
  tests/integration/test_execution_verify.py         — 7 tests (Execution & verification integration)

E2E Tests:
  tests/test_pipeline_e2e.py   — 4 tests (ci_failed, security_alert, deploy_failure, verify_retry)
  tests/test_a2a_protocol.py   — 5 tests (registration, handoff, unknown agent, pipeline, trace)
  tests/test_execution.py      — 3 tests (local backend, dry run, result store)

+ Nemesis/Mike/F993 Subsystem Tests
────────────────────────────────────────────
Total: 1310 passed (full suite, as of 2026-03-06) ✅
```

**Production bugs discovered and fixed in Phase 23**:

- Missing cgrf_metadata in Guardian V3 (`src/a2a/agent_wrapper.py`)
- Sherlock V3 MemoryHit API bug (`src/agents/sherlock_v3.py`)
- Fixer V3 MemoryHit API bug (`src/agents/fixer_v3.py`)

**Issues fixed in code quality enhancement on 2026-02-28**:

- **Event JSON v1 A2A contract inconsistency** — Fixed `handoff_packet.py` (new fields `source_agent_id`/`target_agent_id`/`payload` + jsonschema), `handoff_packet_contract.py` (`__post_init__` required field checks), `decision_contract.py` (ISO 8601 'T' separator enforcement)
- **Deprecated API `datetime.utcnow()`** — Resolved DeprecationWarning in Python 3.12+. Replaced with `datetime.now(timezone.utc)` across 13 files. Added `.replace(tzinfo=None)` in `pentest_engine.py` for naive datetime comparison
```## All Phases Completed (Phase 21-27 + V2→V3 Integration + Evolution MS-1 to MS-8 + Code Quality Enhancement)

All planned phases and all milestones of the Evolution Cycle have been completed.

**Completed Evolution Milestones**:

- ✅ **MS-1**: Roadmap IR Schema & Type Definitions (31 tests)
- ✅ **MS-2**: 3 Translators + Pipeline (37 tests)
- ✅ **MS-3**: Roadmap Tracker & API (17 tests, reusing existing IR types)
- ✅ **MS-4**: MCA Core Engine + Teaching Rewrite (55 tests, Bedrock E2E confirmed)
- ✅ **MS-5**: Roadmap IR × MCA Integration — Feedback Loop Connection
- ✅ **MS-6**: Proposal Execution + SANCTUM — Completion of Automatic Execution (54 tests)
- ✅ **MS-7**: Notion/Supabase Visualization Integration + MCA Grafana Dashboard (75 tests)
- ✅ **MS-8**: General Markdown / Gitlog Translator + GGUF Enrichment + CI Scripts
- ✅ **Code Quality Enhancement** (2026-02-28): Event JSON v1 A2A Contract Modification + Planned API Cleanup of `datetime.utcnow()` (13 files)
- ✅ **MS-C1 to C3 + MS-A1 to A7 + MS-B1 to B3** (2026-03-06): VCC/OAD/Perplexity Integration + Nemesis Defense System (177 tests)

**Total Tests**: **1310 passed** (Full Suite, as of 2026-03-06) ✅

**Next Steps**:

- **MS-8 (Stagger Chain)** — To be started after resolving `CONFIDENCE_WRAPPER` JSON collision issue (⏸ On Hold)
- **Tier 3 (Mission-Critical) Promotion** — Targeting 95% E2E Test Coverage
- **Production Deployment** — Building Docker / Kubernetes / Prometheus Stack

---

## Documentation

- **Integration Blueprint v9.0**: [BLUEPRINT_INTEGRATION_VCC_OAD_PERPLEXITY_v9.0.md](BLUEPRINT_INTEGRATION_VCC_OAD_PERPLEXITY_v9.0.md) - VCC/OAD/Perplexity Integration + Nemesis Design Specifications — Updated: 2026-03-06
- **Integration Roadmap**: [ROADMAP_VCC_OAD_PERPLEXITY.md](ROADMAP_VCC_OAD_PERPLEXITY.md) - Implementation Roadmap for MS-A1 to MS-8 — Updated: 2026-03-06
- **Evolution Blueprint**: [EVOLUTION_BLUEPRINT_20260226.md](EVOLUTION_BLUEPRINT_20260226.md) - MCA Evolution Design Guidelines (Gap Analysis, Asset Utilization Policy) — Updated: 2026-02-28
- **Evolution Roadmap**: [EVOLUTION_ROADMAP_20260226.md](EVOLUTION_ROADMAP_20260226.md) - Development Milestones for MS-1 to MS-8 — Updated: 2026-02-28
- **MCA-META-001**: [config/mca_meta_001.yaml](config/mca_meta_001.yaml) - MCA System Constitution (Draft)
- **CGRF CLI**: [src/cgrf/README.md](src/cgrf/README.md) - CLI Usage, Validation Checklist, --json Output
- **VS Code Extension**: [vscode-extension/citadel-cgrf/README.md](vscode-extension/citadel-cgrf/README.md) - Extension Settings, Commands, Development Methods
- **Grafana Dashboard (DevOps)**: [grafana/citadel_dashboard.json](grafana/citadel_dashboard.json) - Prometheus Metrics Dashboard (Phase 26)
- **Grafana Dashboard (MCA)**: [grafana/mca_dashboard.json](grafana/mca_dashboard.json) - MCA 9-Panel Dashboard (MS-7)
- **CGRF Specifications**: `blueprints/CGRF-v3.0-Complete-Framework.md` - Complete Governance Framework Specifications
- **AGS Specifications**: `blueprints/AGS-System-Spec-v1.0.md` - Agent Governance System Specifications (Completed in Phase 24)
- **AIS Specifications**: `blueprints/AIS-System-Spec-v1.0.md` - Autonomy Index System Specifications
- **REFLEX Specifications**: `blueprints/REFLEX-System-Spec-v1.0.md` - Self-Healing Specifications

---

## License

MIT License (For Hackathon Submission)

---

## Hackathon Submission Checklist

> Fill in the blanks before submitting to the Microsoft AI Dev Days Hackathon portal.

| Requirement | Status | Link / Value |
| --- | --- | --- |
| Working project | ✅ | This repository |
| Project description | ✅ | This README |
| Demo video (YouTube / Vimeo, public) | ⬜ | `<!-- TODO: paste URL here -->` |
| Public GitHub repository | ⬜ | `<!-- TODO: paste GitHub URL here (currently GitLab) -->` |
| Architecture diagram (PNG/SVG) | ⬜ | `<!-- TODO: add to docs/architecture.png and link here -->` |
| Team member Microsoft Learn usernames | ⬜ | See Contributors below |

---

## Contributors

| Name | Role | Microsoft Learn Username |
| --- | --- | --- |
| **Dmitry** | types.py, orchestrator.py, audit/report.py, A2A Protocol, LLM Integration, Memory Store, Execution Runner, REFLEX Dispatcher, CGRF v3.0 Integration | `<!-- TODO -->` |
| **kousaki (Mike)** | Original MVP Architecture, V2/V3 Agent Implementation, CLI Validator | `<!-- TODO -->` |

---