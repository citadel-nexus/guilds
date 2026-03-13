# EXHAUSTIVE CITADEL-NEXUS → CITADEL-LITE AUTONOMOUS FACTORY BLUEPRINT
## Autonomous Software Development with Governance, Agents, and Monetization
**Version**: 2.0 Implementation Ready  
**Date**: January 24, 2026  
**Organization**: Citadel-Nexus (Private) → Citadel-Lite (Public)  
**Tech Stack**: GitLab, Notion, Slack, Linear, GitHub, Perplexity, OpenAI Business, Supabase, AWS, GCS, Stripe  

---

## EXECUTIVE SUMMARY

You're building a **governed autonomous software factory** where:
- **Citadel-Nexus** (GitLab private) is the authoritative core
- **Citadel-Lite** (GitHub public) is the continuously-updated OSS artifact
- **Agents** (builder, qa, planner, docs, release) operate with explicit constraints
- **Governance** happens via Council (4-stage compilation pipeline) + policy gates
- **Proof of autonomy** is empirical: commit history, audit trails, agent identities
- **Monetization** flows through Stripe-measured usage + subscription tiers

**Critical outcome**: You can show investors/judges/customers actual commits from agent IDs, cryptographic evidence of decisions, and hard boundaries between private and public.

---

## 0. NON-NEGOTIABLE PRINCIPLES

### P0.1: Single Source of Truth (GitLab Private → GitHub Public)
**GitLab (Private Authority)**:
- `citadel-nexus/` core platform (proprietary code)
- `citadel-nexus-agents/` agent policies, prompts, templates
- `citadel-nexus-templates/` code generators, scaffolds
- `citadel-lite-export/` export assembly pipeline
- Secrets, infra manifests, proprietary modules
- Internal CI/CD, staging deployments

**GitHub (Public Artifact)**:
- `citadel-lite/` OSS repository (auto-generated from export)
- Public issues & discussions
- Release tags & changelogs (auto-generated)
- Public CI tests (GitHub Actions)

**Guarantee**: GitHub is NEVER written to directly by humans. Only the export pipeline touches it. This makes GitHub the "compiled artifact" of GitLab.

### P0.2: Agents Never Push to Main
**Agents CAN**:
- Open PRs (via comments/dispatch)
- Comment on/update PRs
- Trigger workflows
- Tag issues

**Agents CANNOT**:
- Direct push to main/master
- Change secrets
- Modify release settings
- Bypass policy gates

### P0.3: Separation of Agent Roles = Separation of Permissions
Create distinct GitHub Apps (not one omnibot):
- `citadel-planner-bot` (issues → tasks → plans)
- `citadel-builder-bot` (implements → opens PRs)
- `citadel-qa-bot` (runs tests → comments results)
- `citadel-docs-bot` (updates docs → commits)
- `citadel-release-bot` (generates changelog → tags)
- `citadel-triage-bot` (labels, dedupes, routes)

Each has minimal scoped permissions (Issues, PRs, no Admin/Secrets).

### P0.4: Everything is Event-Driven & Auditable
Every action must answer:
1. **What triggered it?** (GitHub issue, Slack command, external webhook)
2. **What policy allowed it?** (policy_gate.yaml route, CAPS check, cost approved)
3. **What tests passed?** (CI results)
4. **Proof**: Immutable audit trail (Supabase guardian_logs + hash chain)

---

## 1. TARGET OUTCOMES (What "Autonomous Software Development" Means)

You will demonstrate:

✅ **Continuous Change Generation**: Issues → PRs → Merges → Releases (all agent-driven)  
✅ **Autonomous Execution Within Governance**: Agents propose; policy gates decide; humans override  
✅ **Autonomous QA Loop**: Failures → tickets; agents patch; rerun; resolve  
✅ **Autonomous Documentation**: README, API docs, changelogs auto-generated  
✅ **Autonomous Project Management**: Linear, Notion updated in real-time  
✅ **Hard Boundaries**: Private ≠ Public (proprietary code stays in GitLab)  
✅ **Proof Artifacts**: Commit taxonomy, audit logs, runbooks, reproducible builds  

---

## 2. SYSTEM ARCHITECTURE OVERVIEW

### 2.1 Control Plane vs Work Plane

```
┌─────────────────────────────────────────────────────────────┐
│                    CONTROL PLANE                            │
│  (Citadel-Nexus private, orchestration only)               │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ Orchestrator (heartbeat cycle)                       │  │
│  │ Policy Gates (yaml-driven)                           │  │
│  │ Task Ledger (Supabase)                               │  │
│  │ Event Bus (NATS or n8n)                              │  │
│  │ Integration Routers (to GitHub, Linear, Notion,etc)  │  │
│  │ Secrets Vault                                        │  │
│  │ RBAC + Audit Trail                                   │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                          │
        ┌─────────────────┴─────────────────┐
        │                                   │
┌───────▼──────────────────┐    ┌──────────▼──────────────┐
│    WORK PLANE 1          │    │   WORK PLANE 2          │
│  (CI/CD Execution)       │    │  (Agent Execution)      │
│  GitLab CI Runners       │    │  GitHub Actions         │
│  Ephemeral containers    │    │  Ephemeral containers   │
│  Test runners            │    │  Build environments     │
│  Deployment targets      │    │  Deployment targets     │
└──────────────────────────┘    └─────────────────────────┘
```

### 2.2 Data Flow: Issue → PR → Release

```
1. PUBLIC ISSUE (GitHub)
   "Fix: Payment processing timeout on prod"
   
2. CITADEL-TRIAGE-BOT labels & creates Linear ticket
   Linear: "fix-payment-timeout" (Status: Backlog)
   
3. CITADEL-PLANNER-BOT creates task breakdown
   - Identify root cause (DB query, timeout value)
   - Write test case
   - Implement fix
   - Update docs
   
4. CITADEL-BUILDER-BOT opens PR
   - Fetches code from Citadel-Nexus (private)
   - Generates fix code
   - Opens PR to GitHub
   - Links to Linear ticket & GitHub issue
   
5. CITADEL-QA-BOT runs tests
   - Unit tests: ✅
   - Integration tests: ✅
   - Performance: ✅
   - Comments results
   - Updates Linear to "In Review"
   
6. POLICY GATE evaluates (Council compilation)
   - ALLOW (tests passed, code reviewed) →
   
7. CITADEL-RELEASE-BOT
   - Merges PR
   - Generates CHANGELOG entry
   - Tags release v1.2.3
   - Updates Notion "Release Notes"
   - Posts Slack announcement
   
8. DEPLOYMENT PIPELINE (AWS/GCS)
   - Build & test container
   - Deploy to staging → prod
   - Monitor health
   - Rollback if needed

9. AUDIT TRAIL (Immutable)
   - Guardian Logs: Every step cryptographically signed
   - Event Log: All state changes
   - Commit Metadata: Agent identity, policy verdict, XP awarded
```

---

## 3. CORE COMPONENTS & SPECIFICATIONS

### 3.1 Event Backbone (NATS or n8n)

Your stack supports n8n natively. Use it for:

**Core Subjects**:
```yaml
ingest.github.issue.created         # Public issue filed
ingest.github.pr.opened             # Agent opened PR
ingest.github.pr.merged             # PR merged (release candidate)
ingest.gitlab.mr.merged             # Internal MR merged (privat code)
ingest.linear.issue.updated         # Task status changed
ingest.slack.command                # Human command received
ingest.stripe.webhook               # Payment/usage event
orchestrator.cycle.state            # Heartbeat tick
orchestrator.decision.made          # Agent made decision
task.created                        # New work item
task.assigned                       # Work assigned to agent
task.completed                      # Work finished
policy.gate.result                  # ALLOW/DENY/REVIEW verdict
qa.test.failed                      # Test failure detected
release.ready                       # Ready to release
export.lite.generated               # Export assembly complete
export.lite.published               # Published to GitHub
```

**Event Envelope** (all events):
```json
{
  "event_id": "evt-2026-01-24-0001-uuid",
  "event_type": "ingest.github.pr.opened",
  "timestamp": "2026-01-24T14:32:15Z",
  "source": "github",
  "correlation_id": "issue-123-fix-payment",
  "tenant_id": "citadel-org",
  "actor": "citadel-builder-bot",
  "payload": {
    "pr_id": "gh-pr-456",
    "repo": "citadel-lite",
    "title": "Fix: Payment timeout retry logic",
    "body": "Fixes #123...",
    "agent_identity": "citadel-builder-bot",
    "policy_verdict": "ALLOWED",
    "policy_gate_name": "standard_pr_creation"
  },
  "hash": "sha256(...)",
  "signature": "ed25519(...)"
}
```

### 3.2 Task Ledger (Supabase Postgres)

**Core Tables**:

```sql
-- Tasks (work items)
CREATE TABLE tasks (
    task_id UUID PRIMARY KEY,
    tenant_id VARCHAR(255),
    type VARCHAR(50),  -- PLAN, BUILD, TEST, DEPLOY, DOCS, RELEASE
    status VARCHAR(50),  -- CREATED, ASSIGNED, IN_PROGRESS, COMPLETED, FAILED
    priority INTEGER,
    owner_agent VARCHAR(255),
    required_agents TEXT[],  -- agents needed for approval
    input_refs JSONB,  -- links to issue/pr/doc pointers
    result_refs JSONB,  -- output artifacts
    cost_xp INTEGER,  -- XP required
    cost_budget NUMERIC,  -- $ cost (for metering)
    created_at TIMESTAMP,
    deadline TIMESTAMP,
    completed_at TIMESTAMP
);

-- Decisions (orchestrator outcomes)
CREATE TABLE decisions (
    id UUID PRIMARY KEY,
    task_id UUID,
    decided_at TIMESTAMP,
    decision TEXT,  -- ALLOW/REVIEW/DENY
    reason TEXT,
    policy_gate_name VARCHAR(255),
    required_approvals TEXT[]
);

-- Actions (tool calls)
CREATE TABLE actions (
    id UUID PRIMARY KEY,
    decision_id UUID,
    action_name VARCHAR(100),  -- "open_pr", "run_tests", "merge", etc.
    input_params JSONB,
    output_result JSONB,
    status VARCHAR(50),  -- PENDING, EXECUTING, SUCCESS, FAILED
    executed_at TIMESTAMP
);

-- Artifacts (outputs from actions)
CREATE TABLE artifacts (
    id UUID PRIMARY KEY,
    action_id UUID,
    artifact_type VARCHAR(50),  -- PR, TEST_REPORT, BUILD_LOG, etc.
    artifact_url TEXT,
    metadata JSONB
);

-- Audit Log (immutable)
CREATE TABLE audit_log (
    id BIGSERIAL PRIMARY KEY,
    event_type VARCHAR(100),
    agent_id VARCHAR(255),
    resource_type VARCHAR(50),
    resource_id VARCHAR(255),
    action_taken TEXT,
    previous_state JSONB,
    new_state JSONB,
    created_at TIMESTAMP,
    hash VARCHAR(64),
    prev_hash VARCHAR(64),
    signature TEXT
);

-- RLS: All queries filtered by tenant_id
ALTER TABLE tasks ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Tasks filtered by tenant" ON tasks
    FOR ALL USING (tenant_id = current_setting('app.current_tenant_id'));
```

### 3.3 Orchestrator (Heartbeat)

**Cycle**: Every 10-60 seconds (configurable)

```python
class Orchestrator:
    async def run_cycle(self):
        """Main orchestration loop"""
        
        # Phase 1: OBSERVE
        state = await self.observe_state()
        # - Check GitHub issues (unassigned)
        # - Check failed CI jobs
        # - Check Linear backlog
        # - Check Notion specs
        
        # Phase 2: DELIBERATE
        decisions = await self.deliberate(state)
        # - Match issues to agent capabilities
        # - Determine next action (plan, build, test, deploy)
        # - Estimate costs (XP, $)
        
        # Phase 3: GATE (Policy)
        verdicts = await self.policy_gate.evaluate(decisions)
        # - ALLOW (execute), REVIEW (escalate), DENY (log & skip)
        
        # Phase 4: ACT
        for verdict in verdicts:
            if verdict.verdict == 'ALLOW':
                await self.execute_action(verdict.action)
                # - Create PR, run tests, merge, deploy
                # - Update Linear, Notion, Slack
        
        # Phase 5: REFLECT
        await self.reflect(verdicts)
        # - Record metrics
        # - Update trust scores
        # - Award XP
        # - Store in audit log
        
        # Loop again
        await asyncio.sleep(self.cycle_interval)
```

### 3.4 Policy Gate (Simple v0)

```yaml
# policies/core_gates.yaml
version: "1.0"

gates:
  # Gate 1: Standard PR creation
  - name: "standard_pr_creation"
    trigger: "ingest.github.pr.opened"
    rules:
      - condition: "actor == citadel-builder-bot"
        action: "ALLOW"
        reason: "Authorized agent opening PR"
      - condition: "pr.labels contains 'experimental'"
        action: "REVIEW"
        reason: "Experimental feature requires manual approval"
      - condition: "pr.title matches 'DELETE|DROP|TRUNCATE'"
        action: "DENY"
        reason: "Destructive operations blocked"

  # Gate 2: Production deployment
  - name: "production_deployment"
    trigger: "task.type == DEPLOY and task.target == PRODUCTION"
    rules:
      - condition: "all_tests_passed and code_reviewed"
        action: "ALLOW"
        reason: "All gates passed"
      - condition: "time_of_day > 22:00 or time_of_day < 08:00"
        action: "DENY"
        reason: "No deployments outside business hours"
      - condition: "agent.caps_grade >= 'A'"
        action: "ALLOW"
        reason: "High-grade agent authorized"

  # Gate 3: Exporting to public
  - name: "export_to_public"
    trigger: "export.lite.generated"
    rules:
      - condition: "no_secrets_detected and no_proprietary_code"
        action: "ALLOW"
        reason: "Export safe for public"
      - condition: "license_valid and copyright_headers_present"
        action: "ALLOW"
        reason: "Licensing requirements met"
      - condition: "build_passes_public_ci"
        action: "ALLOW"
        reason: "Public tests passed"
```

---

## 4. AGENT IDENTITIES & PERMISSIONS MODEL

### 4.1 GitHub Apps (Public Integrations)

Create 6 bot accounts (each with limited scopes):

```yaml
# GitHub Apps Configuration

citadel-triage-bot:
  scopes:
    - issues: read/write        # Label, comment
    - pull_requests: read       # See PRs
    - metadata: read            # Standard
  permissions:
    - Cannot: Merge, delete, modify secrets
    - Can: Assign labels, comment, create tickets

citadel-planner-bot:
  scopes:
    - issues: read/write        # Create tasks, comment plans
    - pull_requests: read
  permissions:
    - Cannot: Merge, deploy
    - Can: Create plans, attach specs, comment

citadel-builder-bot:
  scopes:
    - contents: read            # Clone repo
    - pull_requests: read/write # Open/update PRs
    - checks: read              # See CI results
  permissions:
    - Cannot: Merge, push to main, access secrets
    - Can: Open PRs, update PR description

citadel-qa-bot:
  scopes:
    - pull_requests: read/write # Comment test results
    - checks: read              # Read CI status
  permissions:
    - Cannot: Merge, deploy
    - Can: Comment results, request changes

citadel-docs-bot:
  scopes:
    - contents: read/write      # Push docs commits
    - pull_requests: read
  permissions:
    - Cannot: Merge code
    - Can: Commit doc updates, open PRs

citadel-release-bot:
  scopes:
    - contents: read/write      # Create tags
    - releases: read/write      # Create releases
  permissions:
    - Cannot: Merge code, delete
    - Can: Create releases, tag commits, generate changelogs
```

### 4.2 GitLab (Private)

Similar bots for internal CI/CD:

```yaml
# GitLab CI User Tokens (Restricted)
citadel-builder-internal:
  api_scopes:
    - api                       # Full API access
    - read_api
  project_scopes:
    - developer                 # Can merge
  rules:
    - Can push to: feature/*, develop
    - Cannot push to: main (protected branch)

citadel-release-internal:
  api_scopes:
    - api
  project_scopes:
    - maintainer               # Can push to main
  rules:
    - Can push release tags
    - Can trigger CI/CD pipelines
```

### 4.3 Linear Integration

```yaml
# Linear Automation
citadel-linear-sync:
  api_key: "stored in Stripe vault"
  permissions:
    - Create/update issues
    - Update status
    - Add labels
    - Post comments
  automation:
    on_github_pr_opened:
      - Move Linear ticket to "In Progress"
      - Add label "Has Open PR"
      - Comment with PR link
    on_github_pr_merged:
      - Move Linear ticket to "Ready for Deploy"
    on_deployment_complete:
      - Move Linear ticket to "Done"
```

---

## 5. INTEGRATION LAYER BLUEPRINT (Your Stack)

### 5.1 GitLab (Private Authoritative)

**Repository Structure**:
```
citadel-nexus/
├── README.md                          # Org overview
├── .gitlab-ci.yml                     # CI/CD pipeline
├── policies/
│   ├── core_gates.yaml               # Policy rules
│   ├── policy_graph.yaml             # 481 routes
│   └── authority_matrix.yaml         # CAPS/permissions
├── agents/
│   ├── planner/
│   │   ├── prompts.yaml
│   │   ├── tools.yaml
│   │   └── skills.yaml
│   ├── builder/
│   ├── qa/
│   ├── docs/
│   └── release/
├── templates/
│   ├── project_scaffold/
│   ├── service_scaffold/
│   └── api_scaffold/
├── export/
│   ├── lite_assembly_pipeline.py    # Export orchestrator
│   ├── license_check.py
│   ├── secret_scan.py
│   ├── copyright_generator.py
│   └── assembly_rules.yaml
├── infra/
│   ├── docker-compose.yml           # Local dev
│   ├── k8s/
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   └── ingress.yaml
│   └── terraform/
└── src/
    ├── citadel_nexus/              # Core platform code (proprietary)
    ├── integrations/               # 11+ platform connectors
    └── tests/
```

**CI/CD Pipeline** (.gitlab-ci.yml):
```yaml
stages:
  - test
  - build
  - export
  - deploy

test:
  stage: test
  script:
    - pytest src/tests/
    - black --check src/
    - mypy src/

build:nexus:
  stage: build
  script:
    - docker build -t citadel-nexus:latest .
    - docker push registry.gitlab.com/citadel-nexus:latest

export:lite:
  stage: export
  trigger:
    project: citadel-nexus/export-pipeline
    branch: main
  only:
    - main

deploy:staging:
  stage: deploy
  environment:
    name: staging
  script:
    - kubectl apply -f infra/k8s/ -n staging
```

### 5.2 GitHub (Public Artifact)

**Repository Structure**:
```
citadel-lite/
├── README.md                    # Public docs
├── LICENSE                      # MIT or Apache
├── CONTRIBUTING.md              # Dev guidelines
├── .github/
│   ├── workflows/
│   │   ├── test.yml            # Run tests on PR
│   │   ├── security-scan.yml   # SAST, dep check
│   │   └── release.yml         # Auto-publish releases
│   └── ISSUE_TEMPLATE.md
├── src/
│   ├── citadel_lite/           # Public code (subset of nexus)
│   ├── cli/
│   ├── api/
│   └── integrations/
├── docs/
│   ├── getting-started.md
│   ├── architecture.md
│   └── api-reference.md
├── examples/
│   ├── basic_usage.py
│   ├── custom_agents.py
│   └── deployment.yaml
└── tests/
```

**GitHub Actions** (.github/workflows/test.yml):
```yaml
name: Tests

on:
  pull_request:
    branches: [main, develop]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: "3.10"
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Run tests
        run: pytest tests/
      - name: Lint
        run: black --check src/ && mypy src/
      - name: Security scan
        uses: aquasecurity/trivy-action@master
        with:
          scan-type: 'fs'
          scan-ref: '.'
```

### 5.3 Export Pipeline (GitLab → GitHub)

**Orchestrator** (Python):
```python
# citadel-nexus/export/lite_assembly_pipeline.py

class ExportOrchestrator:
    async def assemble_and_publish(self):
        """
        1. Assemble Citadel-Lite from Citadel-Nexus
        2. Strip proprietary code
        3. Run checks (secrets, licensing, tests)
        4. Open PR to GitHub
        """
        
        # Step 1: Clone Nexus
        nexus_code = await self.clone_repo("citadel-nexus")
        
        # Step 2: Extract public code
        lite_code = self.filter_code(nexus_code, rules={
            'include': [
                'src/citadel_lite/',
                'src/api/',
                'src/cli/',
                'docs/',
                'LICENSE'
            ],
            'exclude': [
                'src/citadel_nexus/',  # Proprietary
                'infra/secrets/',
                '*.key',
                '*.env'
            ]
        })
        
        # Step 3: License checks
        assert not self.detect_proprietary_licenses(lite_code)
        assert self.copyright_headers_present(lite_code)
        
        # Step 4: Secret scan
        assert not self.detect_secrets(lite_code)
        
        # Step 5: Tests
        await self.run_public_tests(lite_code)
        
        # Step 6: Generate artifacts
        changelog = self.generate_changelog()
        readme = self.generate_readme()
        
        # Step 7: Open PR to GitHub
        pr = await self.open_pr_to_github(
            title=f"Release: v{self.current_version()}",
            body=f"Automated export from Citadel-Nexus\n\n{changelog}",
            files=lite_code,
            branch=f"export/{self.current_version()}"
        )
        
        return pr
```

**Assembly Rules** (YAML):
```yaml
# citadel-nexus/export/assembly_rules.yaml
version: "1.0"

filters:
  include_paths:
    - src/citadel_lite/
    - src/api/
    - src/cli/
    - docs/
    - examples/
    - tests/
    - LICENSE
    - README.md

  exclude_paths:
    - src/citadel_nexus/
    - .env*
    - secrets/
    - infra/private/

license_requirements:
  - type: MIT
    files: "**/*.py"
  - type: Apache-2.0
    files: "docs/**"

secret_scan:
  blocked_patterns:
    - "PRIVATE_KEY"
    - "API_SECRET"
    - "DATABASE_URL"

copyright_headers:
  - pattern: "# Copyright 2026 Citadel Inc."
    required_for: "**/*.py"
```

### 5.4 Linear (Project Management)

**Sync Rules**:
```python
# Integration: GitHub ↔ Linear

class LinearSync:
    async def on_github_issue_created(self, issue):
        """Create Linear ticket when GitHub issue filed"""
        ticket = await linear.create_issue(
            title=issue.title,
            description=issue.body,
            team_key="CL",  # Citadel-Lite team
            labels=[issue.labels],
            metadata={
                "github_issue_id": issue.number,
                "github_url": issue.html_url
            }
        )
        return ticket

    async def on_github_pr_opened(self, pr):
        """Update Linear ticket when PR opened"""
        ticket = await linear.find_issue_by_github_pr(pr.id)
        if ticket:
            await ticket.update(
                state="In Progress",
                status="In Review"
            )
            await ticket.comment(f"PR: {pr.html_url}")

    async def on_github_pr_merged(self, pr):
        """Update Linear when PR merged"""
        ticket = await linear.find_issue_by_github_pr(pr.id)
        if ticket:
            await ticket.update(state="Done")
```

### 5.5 Notion (Specs & Runbooks)

**Structure**:
```
Citadel-Lite Database (Notion)
├── Release Notes (DB)
│   ├─ Version: v1.2.3
│   ├─ Date: 2026-01-24
│   ├─ Changes: [auto-generated from changelog]
│   └─ Artifacts: [links to GCS/AWS artifacts]
├── Architecture Specs (Pages)
│   ├─ System Design
│   ├─ API Reference
│   ├─ Database Schema
│   └─ Deployment Guide
├── Runbooks (Pages)
│   ├─ Incident Response
│   ├─ Rollback Procedures
│   ├─ Scaling Guide
│   └─ Security Audit
└── Performance Metrics (DB)
    ├─ Latency (p50, p99)
    ├─ Error Rate
    ├─ Uptime %
    └─ Resource Usage
```

**Automation**:
```python
# On release publish:
async def on_release_published(release):
    await notion.create_page_in_database(
        database_id="citadel-lite-releases",
        properties={
            "Version": release.tag_name,
            "Date": datetime.utcnow(),
            "Changelog": release.body,
            "Status": "Published",
            "Artifacts": [
                f"AWS: {artifact.url}",
                f"GCS: {artifact.url}"
            ]
        }
    )
```

### 5.6 Slack (Operations & Governance)

**Channels**:
```
#citadel-lite-dev       # PRs, builds, tests
#citadel-governance     # Approvals, policy changes
#citadel-ops            # System health, errors
#citadel-releases       # Release announcements
```

**Commands**:
```bash
/citadel status             # Show current build/deploy status
/citadel approve <pr>       # Human approves PR
/citadel freeze             # Stop deployments (emergency)
/citadel release <version>  # Trigger release
/citadel rollback <version> # Rollback to version
/citadel audit <date>       # Show audit log for date
```

### 5.7 Stripe (Metering & Monetization)

**Usage Events**:
```python
# Track autonomous actions for billing

class StripeMetering:
    async def on_agent_action_complete(self, action, result):
        """Report usage to Stripe"""
        await stripe.reporting.metered_usage.create(
            customer_id=self.get_tenant_stripe_id(),
            timestamp=datetime.utcnow(),
            quantity=1,
            usage_type=f"agent_action_{action.type}"  # e.g., "agent_action_deployment"
        )

    # Pricing
    # - $0.01 per agent action
    # - $0.05 per API call
    # - $1.00 per deployment (reflects risk)
    # - $5.00 per export to public (reflects value)
```

### 5.8 Supabase (Ledger & Audit)

**Schema**:
```sql
-- Already covered above, but key tables:
-- tasks, decisions, actions, artifacts, audit_log
-- Plus: agents, ledger_transactions, guardian_logs

CREATE TABLE agents (
    agent_id VARCHAR(255) PRIMARY KEY,
    agent_name VARCHAR(255),
    agent_type VARCHAR(50),  -- planner, builder, qa, docs, release, triage
    caps_grade VARCHAR(10),  -- D, C, B, A, S
    xp INTEGER DEFAULT 0,
    trust_score FLOAT DEFAULT 0.5,
    created_at TIMESTAMP
);

CREATE TABLE guardian_logs (
    id BIGSERIAL PRIMARY KEY,
    event_timestamp TIMESTAMP,
    agent_id VARCHAR(255),
    action VARCHAR(100),
    result_status VARCHAR(50),  -- SUCCESS, FAILURE
    policy_verdict VARCHAR(20),  -- ALLOW, DENY, REVIEW
    event_hash VARCHAR(64),
    prev_hash VARCHAR(64),
    metadata JSONB
);
```

---

## 6. AUTONOMOUS DEVELOPMENT WORKFLOWS

### 6.1 Issue → PR → Merge → Release Loop

```
Step 1: PUBLIC ISSUE (GitHub)
────────────────────────────
User files issue: "Fix: Payment timeout on prod"
Issue ID: #456

CITADEL-TRIAGE-BOT (automatic):
  ✅ Validates issue format
  ✅ Adds labels: ["bug", "payment", "high-priority"]
  ✅ Creates Linear ticket: CL-123
  ✅ Comments: "I'm on it! Planning..."

────────────────────────────────────

Step 2: PLANNING (Autonomous)
─────────────────────────────
CITADEL-PLANNER-BOT:
  ✅ Analyzes issue description
  ✅ Searches codebase for payment module
  ✅ Identifies root cause (hardcoded 30s timeout, DB slowness)
  ✅ Creates implementation plan:
     - Add exponential backoff retry logic
     - Make timeout configurable (env var)
     - Add unit tests
     - Update README
  ✅ Comments plan on GitHub issue
  ✅ Updates Linear: CL-123 → Status: Planned

────────────────────────────────

Step 3: IMPLEMENTATION (Autonomous)
────────────────────────────────────
CITADEL-BUILDER-BOT:
  ✅ Clones citadel-nexus repo (private)
  ✅ Creates feature branch: fix/payment-timeout-456
  ✅ Generates code:
     ```python
     # src/payment/retry_handler.py
     MAX_RETRIES = int(os.getenv("PAYMENT_MAX_RETRIES", 3))
     TIMEOUT_SECONDS = int(os.getenv("PAYMENT_TIMEOUT", 60))
     
     async def process_payment_with_retry(transaction):
         for attempt in range(MAX_RETRIES):
             try:
                 return await process_payment(
                     transaction,
                     timeout=TIMEOUT_SECONDS
                 )
             except TimeoutError:
                 if attempt == MAX_RETRIES - 1:
                     raise
                 await asyncio.sleep(2 ** attempt)  # Exponential backoff
     ```
  ✅ Commits: "PLAN: Add payment retry logic"
  ✅ Adds test:
     ```python
     # tests/test_payment_retry.py
     @pytest.mark.asyncio
     async def test_retry_on_timeout():
         with patch('payment.process_payment', side_effect=TimeoutError):
             with pytest.raises(TimeoutError):
                 await process_payment_with_retry(tx)
     ```
  ✅ Commits: "TEST: Payment retry test"
  ✅ Opens PR to GitHub (from export pipeline)
  ✅ PR title: "Fix: Payment processing timeout with retry logic"
  ✅ PR links to issue #456
  ✅ Updates Linear: CL-123 → Status: In Review

────────────────────────────────

Step 4: QUALITY ASSURANCE (Autonomous)
───────────────────────────────────────
CITADEL-QA-BOT:
  ✅ GitHub Actions triggered
  ✅ Runs tests:
     - Unit tests: 23/23 ✅
     - Integration tests: 8/8 ✅
     - Lint (black): ✅
     - Type check (mypy): ✅
     - Security scan (bandit): ✅
     - Coverage: 95% ✅
  ✅ Comments on PR:
     ```
     ✅ All checks passed!
     - Tests: 31/31 passing
     - Coverage: 95%
     - No security issues
     Ready to merge.
     ```
  ✅ Updates Linear: CL-123 → Status: Ready for Deploy

────────────────────────────────

Step 5: POLICY GATE EVALUATION (Deterministic)
───────────────────────────────────────────────
COUNCIL (via policy_gate.yaml):
  ✅ Rule: standard_pr_merge
  ✅ Conditions met:
     - All tests passed: ✅
     - Code review approved: ✅
     - No breaking changes: ✅
     - XP cost: 50 (acceptable)
  ✅ Verdict: ALLOW
  ✅ Record in Supabase audit_log (hash-chained)

────────────────────────────────

Step 6: MERGE & RELEASE (Autonomous)
─────────────────────────────────────
CITADEL-RELEASE-BOT:
  ✅ Merges PR to main
  ✅ Updates version: v1.2.3
  ✅ Generates changelog:
     ```
     ## v1.2.3 (2026-01-24)
     ### Fixes
     - Fix: Payment processing timeout with exponential backoff retry
     ```
  ✅ Tags commit: git tag v1.2.3
  ✅ Creates GitHub Release
  ✅ Updates Notion: Citadel-Lite Releases DB
  ✅ Posts Slack announcement:
     ```
     🚀 Released v1.2.3 (Payment fixes)
     - Fixed payment timeout issue
     - Added retry logic with exponential backoff
     Deployment in progress...
     ```
  ✅ Updates Linear: CL-123 → Status: Done

────────────────────────────────

Step 7: DEPLOYMENT (Continuous)
────────────────────────────────
GITHUB ACTIONS (.github/workflows/release.yml):
  ✅ Build container
  ✅ Push to registry
  ✅ Deploy to staging
  ✅ Run smoke tests
  ✅ Deploy to production
  ✅ Health checks (200 OK, latency <200ms)
  ✅ Slack notification: "✅ Deployed to production"

────────────────────────────────

Step 8: AUDIT TRAIL (Immutable)
────────────────────────────────
All steps recorded in Supabase:
  - guardian_logs (cryptographically chained)
  - Event: PLANNER_CREATED_PLAN (agent: citadel-planner-bot)
  - Event: BUILDER_OPENED_PR (agent: citadel-builder-bot)
  - Event: QA_APPROVED (agent: citadel-qa-bot)
  - Event: COUNCIL_ALLOWED (verdict: ALLOW, policy: standard_pr_merge)
  - Event: RELEASE_TAGGED (agent: citadel-release-bot, tag: v1.2.3)
  - Event: DEPLOYED_PRODUCTION (status: SUCCESS)

Each event is hash-chained and immutable.
```

### 6.2 Regression Failure Loop

```
1. CI Fails on PR or main
   Error: test_payment_timeout.py::test_retry_logic FAILED

2. CITADEL-QA-BOT files issue
   GitHub issue: "Regression: Payment retry test failing"
   Comments: "Analyzing failure..."

3. CITADEL-PLANNER-BOT diagnoses
   Issue: Timeout exception not being caught
   Suggests: Check exception type, verify backoff logic

4. CITADEL-BUILDER-BOT fixes
   Opens new PR: "Fix: Catch correct exception type in retry"
   Code review: ✅
   Tests: ✅

5. Loop until green
   All tests pass → Merge → Release
```

---

## 7. PROOF OF AUTONOMY ARTIFACTS

### 7.1 Commit Taxonomy

**Enforce via git hooks**:

```bash
# Commit message format:
# [AGENT-TYPE] [ACTION] [OBJECT]: [Description]
#
# Examples:
# PLAN: Create task breakdown for payment-timeout-456
# BUILD: Implement retry logic for payment processor
# TEST: Add unit tests for retry handler
# DOCS: Update README with timeout configuration
# REL: Tag release v1.2.3
# QA: Run tests and security scan
```

**Machine-readable footer** (git-trailer):

```
Commit-Footer: agent=citadel-builder-bot
Commit-Footer: task_id=task-456-fix-payment
Commit-Footer: policy_verdict=ALLOWED
Commit-Footer: xp_awarded=50
Commit-Footer: trust_delta=+0.01
```

### 7.2 Audit Log Evidence

```sql
-- Query: All actions by autonomous agents in January 2026

SELECT 
  id,
  event_timestamp,
  agent_id,
  action,
  result_status,
  policy_verdict
FROM guardian_logs
WHERE agent_id LIKE 'citadel-%'
  AND event_timestamp >= '2026-01-01'
  AND event_timestamp < '2026-02-01'
ORDER BY event_timestamp DESC;

-- Result: 1,247 autonomous actions in January
-- - 342 PRs opened (citadel-builder-bot)
-- - 289 tests run (citadel-qa-bot)
-- - 156 releases (citadel-release-bot)
-- - 201 documents updated (citadel-docs-bot)
-- - All policy verdicts logged
-- - Zero human interventions for automated tasks
```

### 7.3 Reproducible Build Evidence

```yaml
# citadel-lite-build-report-v1.2.3.yaml
version: 1.2.3
build_date: 2026-01-24T14:32:15Z
build_commit: sha256-abc123def456
build_agent: citadel-release-bot

artifacts:
  - name: citadel-lite-1.2.3.tar.gz
    sha256: abc123def456...
    size_bytes: 1024000
    provenance:
      built_by: GitHub Actions
      triggered_by: citadel-release-bot
      policy_verdict: ALLOWED
      policy_gate: standard_release

dependencies_pinned:
  - python 3.10.2
  - postgres 14.1
  - redis 7.0.4
  
tests_passed:
  unit: 31/31
  integration: 8/8
  security: passed
  coverage: 95%
```

---

## 8. REPO TOPOLOGY (Detailed Directory Structure)

### 8.1 GitLab (citadel-nexus)

```
citadel-nexus/
│
├── README.md                                # Project overview
├── LICENSE                                  # License headers
├── .gitlab-ci.yml                          # CI/CD pipeline
├── .gitignore
│
├── policies/                                # Governance
│   ├── core_gates.yaml                     # Policy rules (ALLOW/DENY/REVIEW)
│   ├── policy_graph.yaml                   # 481 routes for 481 ENUMSPEAK categories
│   ├── authority_matrix.yaml               # CAPS grades → permissions
│   ├── roles/
│   │   ├── admin.yaml
│   │   ├── developer.yaml
│   │   └── agent.yaml
│   └── approval_workflows.yaml
│
├── agents/                                 # Agent specifications
│   ├── planner/
│   │   ├── README.md
│   │   ├── system_prompt.md               # Planner instructions
│   │   ├── tools.yaml                      # Available tools
│   │   ├── skills.yaml                     # Learned skills
│   │   ├── examples/
│   │   │   ├── plan_payment_fix.md
│   │   │   └── plan_api_refactor.md
│   │   └── test_planner.py
│   ├── builder/
│   │   ├── README.md
│   │   ├── system_prompt.md
│   │   ├── codegen_templates/
│   │   │   ├── python_module.j2
│   │   │   ├── api_endpoint.j2
│   │   │   └── test_module.j2
│   │   ├── tools.yaml
│   │   └── test_builder.py
│   ├── qa/
│   │   ├── README.md
│   │   ├── system_prompt.md
│   │   ├── test_runners/
│   │   │   ├── pytest_runner.py
│   │   │   ├── security_scanner.py
│   │   │   └── coverage_checker.py
│   │   └── test_qa.py
│   ├── docs/
│   │   ├── README.md
│   │   ├── system_prompt.md
│   │   ├── templates/
│   │   │   ├── api_reference.md.j2
│   │   │   ├── getting_started.md.j2
│   │   │   └── changelog.md.j2
│   │   └── test_docs.py
│   ├── release/
│   │   ├── README.md
│   │   ├── system_prompt.md
│   │   ├── changelog_generator.py
│   │   ├── versioning_rules.yaml
│   │   └── test_release.py
│   └── triage/
│       ├── README.md
│       ├── system_prompt.md
│       ├── label_taxonomy.yaml
│       └── test_triage.py
│
├── templates/                               # Code scaffolds
│   ├── project_scaffold/
│   │   ├── .github/workflows/test.yml
│   │   ├── src/
│   │   ├── tests/
│   │   ├── docs/
│   │   ├── README.md
│   │   └── requirements.txt
│   ├── service_scaffold/
│   │   ├── Dockerfile
│   │   ├── docker-compose.yml
│   │   ├── src/main.py
│   │   └── infra/k8s/
│   └── api_scaffold/
│       ├── src/main.py (FastAPI)
│       ├── src/routes/
│       ├── src/models/
│       └── tests/
│
├── export/                                  # Export to Citadel-Lite
│   ├── lite_assembly_pipeline.py            # Main orchestrator
│   ├── assembly_rules.yaml                  # What to include/exclude
│   ├── license_check.py                     # License validation
│   ├── secret_scan.py                       # Secret detection
│   ├── copyright_generator.py               # Add copyright headers
│   ├── changelog_generator.py               # Generate CHANGELOG.md
│   ├── tests/
│   │   ├── test_assembly.py
│   │   └── test_secret_scan.py
│   └── .gitlab-ci.yml                       # Export pipeline
│
├── infra/                                   # Infrastructure
│   ├── docker/
│   │   ├── Dockerfile.nexus
│   │   ├── Dockerfile.runner
│   │   └── docker-compose.yml               # Local dev
│   ├── kubernetes/
│   │   ├── namespace.yaml
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   ├── ingress.yaml
│   │   ├── configmap.yaml
│   │   ├── secrets/
│   │   │   ├── api-keys.yaml (encrypted)
│   │   │   └── db-credentials.yaml (encrypted)
│   │   └── rbac/
│   │       ├── role.yaml
│   │       └── rolebinding.yaml
│   ├── terraform/
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   ├── aws/
│   │   │   ├── eks.tf
│   │   │   ├── rds.tf
│   │   │   └── s3.tf
│   │   └── gcp/
│   │       ├── gke.tf
│   │       └── cloud-sql.tf
│   └── monitoring/
│       ├── prometheus.yml
│       ├── grafana-dashboards/
│       └── alerts.yaml
│
├── src/                                     # Source code
│   ├── citadel_nexus/                       # PROPRIETARY: Keep in GitLab only
│   │   ├── __init__.py
│   │   ├── orchestrator.py                  # Main heartbeat loop
│   │   ├── policy_gate.py                   # Policy evaluation
│   │   ├── council.py                       # 4-stage compilation pipeline
│   │   ├── supabase_client.py               # DB interface
│   │   ├── event_bus.py                     # n8n/NATS integration
│   │   └── utils/
│   │       ├── crypto.py
│   │       ├── logging.py
│   │       └── metrics.py
│   │
│   ├── citadel_lite/                        # PUBLIC: Export to GitHub
│   │   ├── __init__.py
│   │   ├── cli/
│   │   │   ├── main.py
│   │   │   ├── commands/
│   │   │   └── formatters.py
│   │   ├── api/
│   │   │   ├── main.py (FastAPI)
│   │   │   ├── routes/
│   │   │   ├── models/
│   │   │   └── middleware/
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   └── logger.py
│   │   └── integrations/
│   │       ├── github.py
│   │       ├── gitlab.py
│   │       ├── slack.py
│   │       └── linear.py
│   │
│   └── integrations/                        # PUBLIC: Export to GitHub
│       ├── github_client.py
│       ├── gitlab_client.py
│       ├── slack_client.py
│       ├── linear_client.py
│       ├── stripe_client.py
│       ├── supabase_client.py
│       ├── notion_client.py
│       └── tests/
│
├── tests/                                   # Test suite
│   ├── unit/
│   │   ├── test_orchestrator.py
│   │   ├── test_policy_gate.py
│   │   ├── test_council.py
│   │   └── test_agents/
│   ├── integration/
│   │   ├── test_github_integration.py
│   │   ├── test_gitlab_integration.py
│   │   └── test_export_pipeline.py
│   ├── e2e/
│   │   ├── test_issue_to_release.py
│   │   └── test_autonomous_deployment.py
│   └── fixtures/
│       ├── mock_events.json
│       ├── mock_policies.yaml
│       └── test_data.sql
│
├── docs/                                    # Internal documentation
│   ├── ARCHITECTURE.md                      # System design
│   ├── DEPLOYMENT.md                        # How to deploy
│   ├── DEVELOPMENT.md                       # Dev setup
│   ├── AGENTS.md                            # Agent documentation
│   ├── POLICIES.md                          # Policy system
│   └── API.md                               # Internal APIs
│
└── scripts/                                 # Utility scripts
    ├── init_database.py                     # Bootstrap DB schema
    ├── seed_policies.py                     # Load policies
    ├── export_to_github.py                  # Export pipeline trigger
    ├── run_tests.sh
    └── deploy.sh
```

### 8.2 GitHub (citadel-lite)

```
citadel-lite/
│
├── README.md                                # Public overview
├── LICENSE                                  # MIT or Apache 2.0
├── CONTRIBUTING.md                         # Dev guidelines
├── CODE_OF_CONDUCT.md
├── CHANGELOG.md                            # Auto-generated
├── .github/
│   ├── ISSUE_TEMPLATE/
│   │   ├── bug_report.md
│   │   ├── feature_request.md
│   │   └── question.md
│   ├── PULL_REQUEST_TEMPLATE.md
│   ├── workflows/
│   │   ├── test.yml                        # Run on PR
│   │   ├── security-scan.yml               # SAST, deps
│   │   ├── release.yml                     # On version tag
│   │   └── pages.yml                       # Deploy docs
│   └── dependabot.yml
│
├── src/                                     # PUBLIC CODE ONLY
│   ├── citadel_lite/
│   │   ├── __init__.py
│   │   ├── cli/
│   │   │   ├── main.py
│   │   │   ├── commands/
│   │   │   │   ├── init.py
│   │   │   │   ├── deploy.py
│   │   │   │   └── status.py
│   │   │   └── formatters.py
│   │   ├── api/
│   │   │   ├── main.py
│   │   │   ├── routes/
│   │   │   │   ├── agents.py
│   │   │   │   ├── policies.py
│   │   │   │   └── health.py
│   │   │   ├── models/
│   │   │   │   ├── agent.py
│   │   │   │   ├── policy.py
│   │   │   │   └── verdict.py
│   │   │   └── middleware/
│   │   │       ├── auth.py
│   │   │       └── logging.py
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   ├── logger.py
│   │   │   └── exceptions.py
│   │   └── integrations/
│   │       ├── github.py
│   │       ├── slack.py
│   │       └── linear.py
│   └── __init__.py
│
├── docs/                                    # PUBLIC DOCS
│   ├── index.md
│   ├── getting-started.md
│   ├── installation.md
│   ├── quick-start.md
│   ├── architecture.md
│   ├── api-reference.md
│   ├── cli-reference.md
│   ├── deployment/
│   │   ├── docker.md
│   │   ├── kubernetes.md
│   │   └── aws-ecs.md
│   ├── examples/
│   │   ├── basic-usage.md
│   │   ├── custom-agents.md
│   │   └── policy-configuration.md
│   ├── contributing/
│   │   ├── development.md
│   │   ├── testing.md
│   │   └── submitting-prs.md
│   ├── troubleshooting.md
│   └── faq.md
│
├── examples/                                # PUBLIC EXAMPLES
│   ├── basic_usage/
│   │   ├── main.py
│   │   ├── requirements.txt
│   │   └── README.md
│   ├── custom_agents/
│   │   ├── my_agent.py
│   │   ├── tools.yaml
│   │   └── README.md
│   └── docker-compose.yml
│
├── tests/                                   # PUBLIC TESTS
│   ├── unit/
│   │   ├── test_cli.py
│   │   ├── test_api.py
│   │   └── test_models.py
│   ├── integration/
│   │   ├── test_github_integration.py
│   │   └── test_slack_integration.py
│   ├── e2e/
│   │   └── test_basic_workflow.py
│   ├── conftest.py
│   └── fixtures/
│
├── .gitignore
├── pyproject.toml                          # Project metadata
├── setup.py                                # Package setup
├── requirements.txt                        # Dependencies
├── requirements-dev.txt
└── Makefile                                # Common commands
```

---

## 9. MINIMAL MVP SCOPE (V0) - What You Actually Ship in Week 13

### Must-Have (Critical Path)

✅ **Orchestrator running** (even slow): 10-60 second cycle  
✅ **GitLab → GitHub export pipeline**: Automated PR to GitHub  
✅ **3-5 agent roles**: Planner, Builder, QA, Release, Triage  
✅ **Policy gate v0**: YAML rules (no Z3 solver)  
✅ **Supabase ledger**: Task tracking + audit logs  
✅ **GitHub bots**: Create PRs, comment results, merge  
✅ **Slack notifications**: Status, approvals  
✅ **Linear sync**: Create/update tickets  
✅ **Basic docs**: README, deployment guide  
✅ **Stripe metering**: Track usage for billing  

### Explicitly Defer (Post-MVP)

❌ Advanced policy solver (Z3)  
❌ Complex scheduling (OR-Tools)  
❌ Multi-model LLM routing  
❌ Advanced UI/Dashboard  
❌ Marketplace  
❌ Advanced analytics  
❌ Kubernetes auto-scaling  

---

## 10. IMPLEMENTATION TIMELINE (13 Weeks)

### Week 1-2: Foundation & Wiring
- [ ] Set up Supabase (PostgreSQL, RLS, auth)
- [ ] Set up Redis (for caching, short-lived state)
- [ ] Initialize FAISS vector store
- [ ] Create GitLab repo structure
- [ ] Create GitHub repo structure
- [ ] Configure n8n event bus (or NATS)
- [ ] Set up monitoring (Datadog, Prometheus)

**Deliverable**: Infrastructure running, empty repos, CI/CD pipelines configured

### Week 3-4: Core Orchestration
- [ ] Implement Orchestrator (main heartbeat loop)
- [ ] Implement Policy Gate (YAML rule evaluation)
- [ ] Implement Council (4-stage compilation: Generator → Definer → FATE → Archivist)
- [ ] Implement Guardian Logs (hash-chained audit trail)
- [ ] Create Supabase schema for tasks, decisions, audit

**Deliverable**: Orchestrator running, can evaluate policies, audit trails working

### Week 5-6: Agent Roles & GitHub Integration
- [ ] Create GitHub Apps (6 bots: planner, builder, qa, docs, release, triage)
- [ ] Implement Triage Bot (labels, creates Linear tickets)
- [ ] Implement Planner Bot (analyzes issues, creates task plans)
- [ ] Implement Builder Bot (opens PRs with code)
- [ ] GitHub webhook ingestion

**Deliverable**: Agents creating issues/PRs/comments, GitHub events flowing

### Week 7-8: QA & Automation
- [ ] Implement QA Bot (runs tests, reports results)
- [ ] Set up GitHub Actions (test runner)
- [ ] Implement Release Bot (creates releases, generates changelogs)
- [ ] Create Docs Bot (updates docs, commits)
- [ ] GitLab CI pipeline for private builds

**Deliverable**: Full CI/CD loop working end-to-end

### Week 9-10: Integrations & Export
- [ ] Linear integration (create/update tickets)
- [ ] Slack integration (commands, notifications)
- [ ] Notion integration (docs, release notes)
- [ ] Export pipeline (GitLab → GitHub, strip proprietary code)
- [ ] Stripe metering (track usage)

**Deliverable**: Coordinated updates across all platforms

### Week 11-12: Deployment & Testing
- [ ] Docker containerization
- [ ] Kubernetes manifests
- [ ] Integration tests (end-to-end workflows)
- [ ] Load testing
- [ ] Security audit
- [ ] Performance optimization (<500ms Council latency target)

**Deliverable**: Production-ready containers, passing all tests

### Week 13: Launch & Documentation
- [ ] Final security review
- [ ] Performance optimization
- [ ] Public documentation (GitHub docs/)
- [ ] Blog post (proof of autonomy)
- [ ] Investor pitch deck (with commit history evidence)
- [ ] Go live

**Deliverable**: Launched, documented, proven

---

## 11. GO-TO-MARKET & MONETIZATION

### Pricing Model

**SaaS Subscription**:
- **Starter**: $1K/month (2 agents, 1K tasks/month)
- **Professional**: $5K/month (10 agents, 50K tasks/month, Linear sync)
- **Enterprise**: $50K+/month (unlimited, dedicated ops, custom integrations)

**Usage-Based** (on top of subscription):
- $0.01 per task execution (beyond monthly allotment)
- $0.05 per agent action
- $1.00 per production deployment (reflects risk)
- $5.00 per export to public (reflects IP value)

**License Keys** (self-host):
- Enterprise Policy Packs: $10K-50K
- Premium Agent Roles: $5K-20K
- Integration Connectors: $1K-5K

### Proof Points for Investors

1. **Commit History**: Show actual GitHub commits from bot accounts
   ```
   citadel-builder-bot opened 342 PRs in January 2026
   citadel-qa-bot ran 289 test suites
   citadel-release-bot created 156 releases
   Zero human intervention for automated workflows
   ```

2. **Audit Trail**: Export immutable ledger from Supabase
   ```sql
   SELECT COUNT(*) as autonomous_actions FROM guardian_logs
   WHERE event_timestamp >= '2026-01-01' AND agent_id LIKE 'citadel-%';
   -- Result: 1,247 autonomous actions in January
   ```

3. **Policy Verdicts**: Show all decisions were governed
   ```sql
   SELECT policy_verdict, COUNT(*) FROM council_verdicts
   GROUP BY policy_verdict;
   -- ALLOW: 1,150 (92%)
   -- REVIEW: 87 (7%)
   -- DENY: 10 (1%)
   ```

4. **Cost Efficiency**: Compare to hiring developers
   - Cost: $300K/year (Citadel-Nexus SaaS)
   - Traditional: 4 developers @ $150K each = $600K/year
   - **ROI**: Break-even in 6 months

---

## 12. QUICK START COMMANDS

```bash
# Clone repositories
git clone git@github.com:citadel-org/citadel-nexus.git
git clone git@github.com:citadel-org/citadel-lite.git

# Local dev setup
cd citadel-nexus
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Initialize database
python scripts/init_database.py
python scripts/seed_policies.py

# Start services (docker-compose)
docker-compose up -d

# Run tests
make test
make test-integration
make test-e2e

# Start orchestrator
python -m citadel_nexus.orchestrator

# Deploy export pipeline
git push origin main  # Triggers .gitlab-ci.yml
# Waits for PR to GitHub...

# Monitor
tail -f logs/orchestrator.log
# Check Slack #citadel-ops
# Check Datadog dashboard
```

---

## 13. SUCCESS CRITERIA

**Week 13 Launch Checklist**:

- [ ] Citadel-Nexus is running autonomously
- [ ] At least 10 issues → PRs → releases completed by agents
- [ ] Zero human code changes for automated workflows
- [ ] GitHub commit history shows agent names
- [ ] Supabase audit trail has 500+ events
- [ ] All policy verdicts logged and verifiable
- [ ] Slack announcements for every action
- [ ] Citadel-Lite repo updated automatically from Citadel-Nexus
- [ ] GitHub Actions tests passing
- [ ] Docs are auto-generated
- [ ] Stripe metering data flowing
- [ ] No security vulnerabilities
- [ ] <500ms Council latency (p99)
- [ ] <0.1% error rate
- [ ] Investor demo ready (commit history + audit trail)

---

## 14. WHAT MAKES THIS "AUTONOMOUS SOFTWARE DEVELOPMENT" (Not Sci-Fi)

**You are NOT claiming**:
- AI builds software without humans
- No humans ever involved
- AI decides business strategy

**You ARE claiming** (and proving):
✅ AI operates the software factory within explicit constraints  
✅ Agents propose actions (PRs, tests, deployments)  
✅ Governance gates decide (policy rules, CAPS grades, human approval)  
✅ Humans own outcomes (they pick which features to prioritize)  
✅ Everything is auditable (cryptographic audit trail)  
✅ Economic incentives self-regulate (XP/TP/Trust system)  
✅ Proof is empirical (git commits, audit logs, metrics)  

This is the only version that:
- ✅ Ships (production-ready)
- ✅ Sells (enterprises buy it)
- ✅ Scales (adds agents, not headcount)
- ✅ Survives audits (compliant by design)
- ✅ Wins customers (competitive advantage)

---

## 15. NEXT STEPS

1. **This Week**: Review this blueprint with your team
2. **Next Week**: Start Week 1 infrastructure setup
3. **Week 3**: Begin core Council implementation
4. **Week 13**: Launch to production
5. **Post-Launch**: Start monetization, enterprise sales

---

**Blueprint Complete. Ready to build. Ready to ship. Ready to prove autonomy.**

**Status**: IMPLEMENTATION READY ✅

