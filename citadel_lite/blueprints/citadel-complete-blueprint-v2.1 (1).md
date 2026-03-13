# CITADEL-NEXUS → CITADEL-LITE: COMPLETE AUTONOMOUS FACTORY BLUEPRINT
## v2.1 Engineering-Ready Implementation Specification

**Date**: January 24, 2026  
**Status**: IMPLEMENTATION READY  
**Organization**: Citadel-Nexus (Private GitLab) → Citadel-Lite (Public GitHub)  
**Tech Stack**: GitLab, GitHub, Notion, Slack, Linear, Perplexity, OpenAI, Supabase, AWS/GCS, Stripe, n8n  
**Timeline**: 5-week MVP + 13-week full build  

---

## TABLE OF CONTENTS

1. [Executive Summary](#1-executive-summary)
2. [Non-Negotiable Principles](#2-non-negotiable-principles)
3. [Architecture Decisions (Gap Resolutions)](#3-architecture-decisions)
4. [System Architecture Overview](#4-system-architecture-overview)
5. [Core Components Specifications](#5-core-components-specifications)
6. [Agent Identities & Permissions Model](#6-agent-identities--permissions-model)
7. [Integration Layer Blueprint](#7-integration-layer-blueprint)
8. [Autonomous Development Workflows](#8-autonomous-development-workflows)
9. [Security & Governance Hardening](#9-security--governance-hardening)
10. [Runtime Architecture](#10-runtime-architecture)
11. [Product Boundary & Licensing](#11-product-boundary--licensing)
12. [Evaluation Harness (Proof of Autonomy)](#12-evaluation-harness)
13. [Repository Topology](#13-repository-topology)
14. [Implementation Timeline](#14-implementation-timeline)
15. [5-Week MVP Track](#15-5-week-mvp-track)
16. [Go-to-Market & Monetization](#16-go-to-market--monetization)
17. [Quick Start Commands](#17-quick-start-commands)
18. [Success Criteria](#18-success-criteria)
19. [Complete Checklists](#19-complete-checklists)

---

## 1. EXECUTIVE SUMMARY

### What You're Building

A **governed autonomous software factory** where:
- **Citadel-Nexus** (GitLab private) = authoritative core, proprietary orchestration
- **Citadel-Lite** (GitHub public) = continuously-updated OSS artifact (compiled from Nexus)
- **Agents** (planner, builder, qa, docs, release, triage) = operate with explicit constraints
- **Governance** = Council (4-stage policy pipeline) + YAML policy gates
- **Proof** = Empirical commit history, audit trails, cryptographic evidence
- **Monetization** = Stripe-measured usage + subscription tiers

### Critical Outcomes

You will demonstrate:

✅ **Continuous Change Generation**: Issues → PRs → Merges → Releases (all agent-driven)  
✅ **Autonomous Execution Within Governance**: Agents propose; policy gates decide; humans override  
✅ **Autonomous QA Loop**: Failures → tickets; agents patch; rerun; resolve  
✅ **Autonomous Documentation**: README, API docs, changelogs auto-generated  
✅ **Autonomous Project Management**: Linear, Notion updated in real-time  
✅ **Hard Boundaries**: Private ≠ Public (proprietary code stays in GitLab)  
✅ **Proof Artifacts**: Commit taxonomy, audit logs, runbooks, reproducible builds  

### What Makes This Real (Not Sci-Fi)

**You are NOT claiming**:
- AI builds software without humans
- No humans ever involved
- AI decides business strategy

**You ARE claiming** (and proving):
- ✅ AI operates the software factory within explicit constraints  
- ✅ Agents propose actions (PRs, tests, deployments)  
- ✅ Governance gates decide (policy rules, CAPS grades, human approval)  
- ✅ Humans own outcomes (they pick which features to prioritize)  
- ✅ Everything is auditable (cryptographic audit trail)  
- ✅ Economic incentives self-regulate (XP/TP/Trust system)  
- ✅ Proof is empirical (git commits, audit logs, metrics)  

---

## 2. NON-NEGOTIABLE PRINCIPLES

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
- Merge their own PRs

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

## 3. ARCHITECTURE DECISIONS

### 3.1 DECISION: GitHub's Role (RESOLVED)

**Original Problem**: "GitHub is NEVER written to directly" vs "bots commit/tag"

**CHOSEN MODEL: A (Compiled-Artifact)** ✅

GitHub is a **pure compiled artifact**. Only one actor writes: `citadel-export-bot` (via pull_request).

**Permission Matrix**:
```
citadel-export-bot:     contents:write, pull_requests:write
                        (can open PRs, push to export/* branches ONLY)
                        
citadel-release-bot:    pull_requests:write (comments only, NO MERGE)
citadel-docs-bot:       pull_requests:write (comments only, NO COMMITS)
citadel-qa-bot:         pull_requests:write (review comments only)
citadel-builder-bot:    pull_requests:write (comments only)
citadel-triage-bot:     issues:write (labels, comments)
```

**Action Flow**:
```
1. GitLab (private) has all code changes
   - Builder-bot pushes to feature branches IN GITLAB
   - Developers push to GitLab
   - All merges happen in GitLab

2. Export pipeline triggered (on main merge in GitLab)
   - Scheduled: Every 6 hours OR on-demand via `/citadel export`
   
3. Export/Bridge Service (private VM):
   a. Pulls latest from citadel-nexus/main (GitLab)
   b. Strips proprietary code (via assembly_rules.yaml)
   c. Runs secret scan (truffleHog, gitleaks)
   d. Runs license check (ensures MIT/Apache only)
   e. Creates PR to GitHub: export/v{version}
   
4. GitHub Actions tests PR (public CI)
   - Unit tests
   - Integration tests
   - Security scan
   - Lint + type check
   
5. citadel-export-bot merges PR to main (if all checks pass)
   - Auto-merge enabled (branch protection allows)
   
6. GitHub Actions workflow (triggered on main push):
   - Creates git tag: v{version}
   - Creates GitHub Release
   - Uploads artifacts (tarball, wheel, SBOM)
   - Signs with cosign
```

**Why this works**:
- ✅ GitHub is objectively a compiled artifact (provenance chain is clear)
- ✅ Export pipeline is your audit point (all secrets/proprietary code filtered there)
- ✅ No bot can bypass; only deterministic CI can promote code
- ✅ Investors see: "GitHub was generated from GitLab, we can prove it"
- ✅ Licensing: Can enforce (OSS-only code in GitHub, proprietary stays private)
- ✅ Clear separation: Private work → Public artifact

**Tradeoff**: Release/changelog creation happens in GitHub Actions (not bot). More reliable, slightly less "agent autonomy" appearance.

---

### 3.2 DECISION: Cross-Domain Access (RESOLVED)

**Original Problem**: How do agents/pipeline access private GitLab to build GitHub PRs?

**SOLUTION: Export/Bridge Service**

Create a **dedicated, audited service** that:
1. Runs in private infrastructure (GitLab Runner, or dedicated VM)
2. Has **separate, scoped credentials** for each domain
3. Only does one thing: clone → filter → push → open PR
4. Logs every action to Supabase audit trail

**Architecture Diagram**:

```
┌─────────────────────────────────────┐
│  GitLab CI (Private)                │
│  Trigger: main branch merge         │
│  Job: export-to-github              │
└──────────────┬──────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────┐
│  Export/Bridge Service (Private VM/Container)            │
│  ┌────────────────────────────────────────────────────┐  │
│  │ Credentials (from Secrets Manager):                │  │
│  │ - GITLAB_TOKEN (project-scoped, read-only)         │  │
│  │ - GITHUB_APP_PRIVATE_KEY (for JWT generation)      │  │
│  │ - GITHUB_APP_ID                                    │  │
│  │ - GITHUB_INSTALLATION_ID                           │  │
│  └────────────────────────────────────────────────────┘  │
│                                                          │
│  Execution Steps:                                        │
│  1. Clone citadel-nexus (GITLAB_TOKEN)                  │
│  2. Load assembly_rules.yaml                            │
│  3. Filter code:                                        │
│     - Remove src/citadel_nexus/ (proprietary)          │
│     - Remove infra/secrets/                            │
│     - Keep src/citadel_lite/                           │
│     - Keep docs/, examples/, tests/                    │
│  4. Secret scan (truffleHog):                           │
│     - Scan for API keys, tokens, passwords             │
│     - FAIL if any found                                │
│  5. License check:                                      │
│     - Verify all files have MIT/Apache headers         │
│     - FAIL if proprietary licenses found               │
│  6. Authenticate to GitHub (OIDC JWT):                  │
│     - Generate JWT from GITHUB_APP_PRIVATE_KEY          │
│     - Request installation access token (expires 1h)   │
│  7. Push to GitHub:                                     │
│     - Create branch: export/v{version}                 │
│     - Push filtered code                               │
│  8. Create PR:                                          │
│     - Title: "Release: v{version}"                     │
│     - Body: Auto-generated changelog                   │
│     - Link to GitLab commits                           │
│  9. Log to Supabase:                                    │
│     - event_type: EXPORT_TO_GITHUB                     │
│     - pr_id, pr_url                                    │
│     - cryptographic hash of filtered code              │
│  10. Notify Slack:                                      │
│      - Channel: #citadel-ops                           │
│      - Message: "✅ Export v{version} → GitHub PR #123" │
└──────────────────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  GitHub (Public)                    │
│  Repo: citadel-lite                 │
│  PR: export/v1.2.3 → main           │
│  Status: Awaiting CI checks         │
└─────────────────────────────────────┘
```

**Implementation** (Python):

```python
# citadel-nexus/export/bridge_service.py

import os
import hashlib
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
import yaml
import jwt

class ExportBridgeService:
    def __init__(self):
        self.gitlab_token = os.getenv('GITLAB_TOKEN')
        self.github_app_id = os.getenv('GITHUB_APP_ID')
        self.github_private_key = os.getenv('GITHUB_PRIVATE_KEY')
        self.github_installation_id = os.getenv('GITHUB_INSTALLATION_ID')
        self.supabase_url = os.getenv('SUPABASE_URL')
        self.supabase_key = os.getenv('SUPABASE_KEY')
        
    async def export_to_github(self, version: str):
        """Main export orchestration."""
        
        print(f"[EXPORT] Starting export for version {version}")
        
        # Step 1: Clone GitLab repo
        print("[1/10] Cloning citadel-nexus from GitLab...")
        nexus_path = await self.clone_gitlab_repo(
            repo='citadel-org/citadel-nexus',
            token=self.gitlab_token,
            branch='main'
        )
        
        # Step 2: Load assembly rules
        print("[2/10] Loading assembly rules...")
        rules = self.load_assembly_rules(f'{nexus_path}/export/assembly_rules.yaml')
        
        # Step 3: Filter code
        print("[3/10] Filtering proprietary code...")
        lite_path = await self.filter_code(nexus_path, rules)
        
        # Step 4: Secret scan
        print("[4/10] Scanning for secrets...")
        secrets_found = self.scan_for_secrets(lite_path)
        if secrets_found:
            raise SecurityError(f"Secrets detected: {secrets_found}")
        
        # Step 5: License check
        print("[5/10] Checking licenses...")
        license_violations = self.check_licenses(lite_path, rules)
        if license_violations:
            raise LicenseError(f"License violations: {license_violations}")
        
        # Step 6: Generate changelog
        print("[6/10] Generating changelog...")
        changelog = self.generate_changelog(nexus_path, version)
        
        # Step 7: Authenticate to GitHub
        print("[7/10] Authenticating to GitHub...")
        github_token = self.generate_github_jwt_token()
        
        # Step 8: Push to GitHub
        print("[8/10] Pushing to GitHub export branch...")
        branch_name = f'export/{version}'
        await self.push_to_github(
            repo='citadel-org/citadel-lite',
            branch=branch_name,
            source_path=lite_path,
            token=github_token
        )
        
        # Step 9: Create PR
        print("[9/10] Creating GitHub PR...")
        pr = await self.create_github_pr(
            repo='citadel-org/citadel-lite',
            title=f'Release: v{version}',
            body=f"""## Automated Export from Citadel-Nexus

**Version**: {version}  
**Date**: {datetime.utcnow().isoformat()}  
**Source Commit**: {self.get_git_commit(nexus_path)}

### Changelog

{changelog}

### Verification

- ✅ Proprietary code removed
- ✅ No secrets detected
- ✅ License headers verified
- ✅ Tests will run automatically

---

*This PR was automatically generated by the Export/Bridge Service.*
*Manual review is not required unless CI fails.*
""",
            head=branch_name,
            base='main',
            token=github_token
        )
        
        # Step 10: Audit log
        print("[10/10] Logging to audit trail...")
        await self.supabase_log({
            'event_type': 'EXPORT_TO_GITHUB',
            'version': version,
            'pr_id': pr['id'],
            'pr_number': pr['number'],
            'pr_url': pr['html_url'],
            'source_commit': self.get_git_commit(nexus_path),
            'timestamp': datetime.utcnow().isoformat(),
            'code_hash': self.hash_directory(lite_path)
        })
        
        # Step 11: Notify Slack
        await self.slack_notify(
            channel='#citadel-ops',
            text=f"✅ Export v{version} → GitHub PR #{pr['number']}\n{pr['html_url']}"
        )
        
        print(f"[EXPORT] Complete! PR: {pr['html_url']}")
        return pr
    
    async def clone_gitlab_repo(self, repo: str, token: str, branch: str) -> Path:
        """Clone GitLab repository."""
        clone_url = f"https://oauth2:{token}@gitlab.com/{repo}.git"
        dest_path = Path(f'/tmp/nexus-{datetime.utcnow().timestamp()}')
        
        subprocess.run([
            'git', 'clone',
            '--depth', '1',
            '--branch', branch,
            clone_url,
            str(dest_path)
        ], check=True)
        
        return dest_path
    
    def load_assembly_rules(self, rules_path: str) -> dict:
        """Load YAML assembly rules."""
        with open(rules_path) as f:
            return yaml.safe_load(f)
    
    async def filter_code(self, source_path: Path, rules: dict) -> Path:
        """Filter code according to assembly rules."""
        dest_path = Path(f'/tmp/lite-{datetime.utcnow().timestamp()}')
        dest_path.mkdir(parents=True)
        
        # Copy only allowed paths
        for include_pattern in rules['filters']['include_paths']:
            for file_path in source_path.glob(include_pattern):
                if file_path.is_file():
                    # Check if excluded
                    excluded = False
                    for exclude_pattern in rules['filters']['exclude_paths']:
                        if file_path.match(exclude_pattern):
                            excluded = True
                            break
                    
                    if not excluded:
                        # Copy file
                        rel_path = file_path.relative_to(source_path)
                        dest_file = dest_path / rel_path
                        dest_file.parent.mkdir(parents=True, exist_ok=True)
                        dest_file.write_bytes(file_path.read_bytes())
        
        return dest_path
    
    def scan_for_secrets(self, path: Path) -> list:
        """Scan for secrets using truffleHog."""
        result = subprocess.run([
            'trufflehog',
            'filesystem',
            str(path),
            '--json',
            '--fail'
        ], capture_output=True)
        
        if result.returncode != 0:
            # Secrets found
            return result.stdout.decode().split('\n')
        
        return []
    
    def check_licenses(self, path: Path, rules: dict) -> list:
        """Check license headers."""
        violations = []
        
        required_licenses = rules['license_requirements']
        
        for req in required_licenses:
            license_type = req['type']
            file_pattern = req['files']
            
            for file_path in path.glob(file_pattern):
                if file_path.is_file():
                    content = file_path.read_text()
                    
                    # Check for license header
                    if license_type not in content[:500]:  # Check first 500 chars
                        violations.append(f"{file_path}: Missing {license_type} license")
        
        return violations
    
    def generate_changelog(self, repo_path: Path, version: str) -> str:
        """Generate changelog from git commits."""
        # Get commits since last release
        result = subprocess.run([
            'git', '-C', str(repo_path),
            'log', '--oneline', '--no-merges',
            f'v{self.get_previous_version(version)}..HEAD'
        ], capture_output=True, text=True)
        
        commits = result.stdout.strip().split('\n')
        
        # Group by type (feat, fix, docs, etc.)
        features = []
        fixes = []
        docs = []
        other = []
        
        for commit in commits:
            if 'feat:' in commit.lower():
                features.append(commit)
            elif 'fix:' in commit.lower():
                fixes.append(commit)
            elif 'docs:' in commit.lower():
                docs.append(commit)
            else:
                other.append(commit)
        
        changelog = f"## v{version}\n\n"
        
        if features:
            changelog += "### Features\n\n"
            for feat in features:
                changelog += f"- {feat}\n"
            changelog += "\n"
        
        if fixes:
            changelog += "### Fixes\n\n"
            for fix in fixes:
                changelog += f"- {fix}\n"
            changelog += "\n"
        
        if docs:
            changelog += "### Documentation\n\n"
            for doc in docs:
                changelog += f"- {doc}\n"
            changelog += "\n"
        
        return changelog
    
    def generate_github_jwt_token(self) -> str:
        """Generate GitHub App JWT and exchange for installation access token."""
        # Step 1: Create JWT
        now = datetime.utcnow()
        payload = {
            'iat': now,
            'exp': now + timedelta(minutes=10),
            'iss': self.github_app_id
        }
        
        jwt_token = jwt.encode(payload, self.github_private_key, algorithm='RS256')
        
        # Step 2: Exchange for installation access token
        import httpx
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f'https://api.github.com/app/installations/{self.github_installation_id}/access_tokens',
                headers={
                    'Authorization': f'Bearer {jwt_token}',
                    'Accept': 'application/vnd.github.v3+json'
                }
            )
            response.raise_for_status()
            return response.json()['token']
    
    async def push_to_github(self, repo: str, branch: str, source_path: Path, token: str):
        """Push code to GitHub branch."""
        # Initialize git in source directory
        subprocess.run(['git', '-C', str(source_path), 'init'], check=True)
        subprocess.run(['git', '-C', str(source_path), 'add', '.'], check=True)
        subprocess.run([
            'git', '-C', str(source_path),
            'commit', '-m', f'Export: {branch}'
        ], check=True)
        
        # Add remote and push
        remote_url = f"https://x-access-token:{token}@github.com/{repo}.git"
        subprocess.run([
            'git', '-C', str(source_path),
            'remote', 'add', 'github', remote_url
        ], check=True)
        
        subprocess.run([
            'git', '-C', str(source_path),
            'push', '-f', 'github', f'HEAD:{branch}'
        ], check=True)
    
    async def create_github_pr(self, repo: str, title: str, body: str, 
                               head: str, base: str, token: str) -> dict:
        """Create GitHub PR."""
        import httpx
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f'https://api.github.com/repos/{repo}/pulls',
                headers={
                    'Authorization': f'token {token}',
                    'Accept': 'application/vnd.github.v3+json'
                },
                json={
                    'title': title,
                    'body': body,
                    'head': head,
                    'base': base
                }
            )
            response.raise_for_status()
            return response.json()
    
    def hash_directory(self, path: Path) -> str:
        """Generate SHA256 hash of directory contents."""
        hasher = hashlib.sha256()
        
        for file_path in sorted(path.rglob('*')):
            if file_path.is_file():
                hasher.update(file_path.read_bytes())
        
        return hasher.hexdigest()
    
    def get_git_commit(self, repo_path: Path) -> str:
        """Get current git commit hash."""
        result = subprocess.run([
            'git', '-C', str(repo_path),
            'rev-parse', 'HEAD'
        ], capture_output=True, text=True)
        
        return result.stdout.strip()
    
    async def supabase_log(self, data: dict):
        """Log to Supabase audit trail."""
        import httpx
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f'{self.supabase_url}/rest/v1/audit_log',
                headers={
                    'apikey': self.supabase_key,
                    'Authorization': f'Bearer {self.supabase_key}',
                    'Content-Type': 'application/json'
                },
                json=data
            )
            response.raise_for_status()
    
    async def slack_notify(self, channel: str, text: str):
        """Send Slack notification."""
        slack_webhook = os.getenv('SLACK_WEBHOOK_URL')
        
        import httpx
        
        async with httpx.AsyncClient() as client:
            await client.post(slack_webhook, json={
                'channel': channel,
                'text': text
            })
```

**Credentials Management**:

```yaml
# Stored in AWS Secrets Manager or GCP Secret Manager

citadel/export-service/gitlab-token:
  value: "glpat-xxxxxxxxxxxxxxxxxxxx"
  scope: "read_repository"
  expires: "2026-04-24"
  rotation_policy: "90 days"

citadel/export-service/github-app-key:
  value: |
    -----BEGIN RSA PRIVATE KEY-----
    ...
    -----END RSA PRIVATE KEY-----
  algorithm: "RS256"
  rotation_policy: "180 days"

citadel/export-service/github-app-id:
  value: "123456"
  public: true

citadel/export-service/github-installation-id:
  value: "789012"
  public: true
```

**Why this works**:
- ✅ Cross-domain access is isolated in one service
- ✅ Credentials are scoped (GitLab token read-only, GitHub uses short-lived JWT)
- ✅ All actions logged to Supabase (immutable audit)
- ✅ Can be tested independently
- ✅ If compromised, blast radius is limited (can only create PRs, not merge)
- ✅ No bot has direct access to both GitLab and GitHub

---

### 3.3 DECISION: Bot Permissions — Push vs Pull Request (RESOLVED)

**Original Problem**: "Agents never push to main" but described release-bot tagging and merging.

**SOLUTION: Separate Release from Merge**

```
NEVER:
- citadel-release-bot pushes commits to main
- citadel-release-bot merges PRs
- Any bot has admin:write on the repo

INSTEAD:
- GitHub Actions workflow (triggered by PR merge) creates tags/releases
- Workflow runs with GITHUB_TOKEN (ephemeral, workflow-scoped)
- citadel-release-bot can comment on PRs saying "ready to release"
- Human OR policy gate approves merge
- On merge, GitHub Actions automatically creates tag + release
```

**Implementation** (.github/workflows/release.yml):

```yaml
name: Auto-Release on Main Push

on:
  push:
    branches: [main]

permissions:
  contents: write
  releases: write

jobs:
  check-release:
    runs-on: ubuntu-latest
    outputs:
      should_release: ${{ steps.check.outputs.should_release }}
      version: ${{ steps.check.outputs.version }}
    steps:
      - uses: actions/checkout@v3
        with:
          fetch-depth: 0
      
      - name: Check if release needed
        id: check
        run: |
          # Check if PR commit message contains [release] tag
          COMMIT_MSG=$(git log -1 --pretty=%B)
          
          if echo "$COMMIT_MSG" | grep -q "\[release\]"; then
            echo "should_release=true" >> $GITHUB_OUTPUT
            
            # Extract version from VERSION file
            VERSION=$(cat VERSION)
            echo "version=$VERSION" >> $GITHUB_OUTPUT
          else
            echo "should_release=false" >> $GITHUB_OUTPUT
          fi
  
  create-release:
    needs: check-release
    if: needs.check-release.outputs.should_release == 'true'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Create git tag
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          
          VERSION="${{ needs.check-release.outputs.version }}"
          git tag -a "v$VERSION" -m "Release v$VERSION"
          git push origin "v$VERSION"
      
      - name: Generate release notes
        id: notes
        run: |
          # Get commits since last release
          LAST_TAG=$(git describe --tags --abbrev=0 HEAD^ 2>/dev/null || echo "")
          
          if [ -z "$LAST_TAG" ]; then
            # First release
            COMMITS=$(git log --oneline --no-merges)
          else
            # Get commits since last tag
            COMMITS=$(git log --oneline --no-merges $LAST_TAG..HEAD)
          fi
          
          # Format changelog
          echo "## What's Changed" > RELEASE_NOTES.md
          echo "" >> RELEASE_NOTES.md
          
          # Group by type
          echo "### Features" >> RELEASE_NOTES.md
          echo "$COMMITS" | grep -i "feat:" | sed 's/^/* /' >> RELEASE_NOTES.md || echo "- No new features" >> RELEASE_NOTES.md
          echo "" >> RELEASE_NOTES.md
          
          echo "### Fixes" >> RELEASE_NOTES.md
          echo "$COMMITS" | grep -i "fix:" | sed 's/^/* /' >> RELEASE_NOTES.md || echo "- No bug fixes" >> RELEASE_NOTES.md
          echo "" >> RELEASE_NOTES.md
          
          echo "### Other Changes" >> RELEASE_NOTES.md
          echo "$COMMITS" | grep -v -i "feat:\|fix:" | sed 's/^/* /' >> RELEASE_NOTES.md || echo "- No other changes" >> RELEASE_NOTES.md
          
          cat RELEASE_NOTES.md
      
      - name: Create GitHub Release
        uses: softprops/action-gh-release@v1
        with:
          tag_name: v${{ needs.check-release.outputs.version }}
          name: Release v${{ needs.check-release.outputs.version }}
          body_path: RELEASE_NOTES.md
          draft: false
          prerelease: false
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
      
      - name: Build artifacts
        run: |
          python -m build
          tar -czf citadel-lite-${{ needs.check-release.outputs.version }}.tar.gz dist/
      
      - name: Upload artifacts to release
        uses: softprops/action-gh-release@v1
        with:
          tag_name: v${{ needs.check-release.outputs.version }}
          files: |
            citadel-lite-${{ needs.check-release.outputs.version }}.tar.gz
            dist/*.whl
            dist/*.tar.gz
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
      
      - name: Notify completion
        run: |
          echo "✅ Release v${{ needs.check-release.outputs.version }} created successfully"
```

**Why this works**:
- ✅ No bot has direct push/merge permissions
- ✅ All writes happen via GitHub Actions (auditable, easy to review)
- ✅ Workflow has minimal permissions (contents:write for tags, releases:write)
- ✅ Bot can still propose releases (via comments/PR labels)
- ✅ Human or policy gate controls merge (guardrail before release)
- ✅ Provenance is clear: PR merge → workflow triggered → release created

---

## 4. SYSTEM ARCHITECTURE OVERVIEW

### 4.1 Control Plane vs Work Plane

```
┌─────────────────────────────────────────────────────────────┐
│                    CONTROL PLANE                            │
│  (Citadel-Nexus private, orchestration only)               │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ Orchestrator (heartbeat cycle: 30-60 sec)           │  │
│  │ Policy Gates (YAML-driven, deterministic)           │  │
│  │ Task Ledger (Supabase PostgreSQL)                   │  │
│  │ Event Bus (n8n for webhook orchestration)           │  │
│  │ Integration Routers (GitHub, Linear, Notion, Slack) │  │
│  │ Secrets Vault (AWS Secrets Manager)                 │  │
│  │ RBAC + Audit Trail (Supabase + hash chain)          │  │
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

### 4.2 Data Flow: Issue → PR → Release

```
┌──────────────────────────────────────────────────────────────────┐
│ 1. PUBLIC ISSUE (GitHub)                                         │
│    "Fix: Payment processing timeout on prod"                     │
│    Issue ID: #456                                                │
└──────────────────────┬───────────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────────┐
│ 2. CITADEL-TRIAGE-BOT (automatic, <5 sec)                       │
│    ✅ Validates issue format                                     │
│    ✅ Adds labels: ["bug", "payment", "high-priority"]          │
│    ✅ Creates Linear ticket: CL-123                             │
│    ✅ Comments: "I'm on it! Planning..."                        │
└──────────────────────┬───────────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────────┐
│ 3. CITADEL-PLANNER-BOT (Planning, ~30 sec)                      │
│    ✅ Analyzes issue description via Claude API                 │
│    ✅ Searches codebase for payment module                      │
│    ✅ Identifies root cause (hardcoded 30s timeout, DB slow)    │
│    ✅ Creates implementation plan:                              │
│       - Add exponential backoff retry logic                     │
│       - Make timeout configurable (env var)                     │
│       - Add unit tests                                          │
│       - Update README                                           │
│    ✅ Comments plan on GitHub issue                             │
│    ✅ Updates Linear: CL-123 → Status: Planned                  │
└──────────────────────┬───────────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────────┐
│ 4. CITADEL-BUILDER-BOT (Implementation, ~2 min)                 │
│    ✅ Clones citadel-nexus repo (private, in GitLab)            │
│    ✅ Creates feature branch: fix/payment-timeout-456           │
│    ✅ Generates code via Claude API:                            │
│       ```python                                                 │
│       MAX_RETRIES = int(os.getenv("PAYMENT_MAX_RETRIES", 3))   │
│       TIMEOUT_SECONDS = int(os.getenv("PAYMENT_TIMEOUT", 60))  │
│                                                                 │
│       async def process_payment_with_retry(transaction):       │
│           for attempt in range(MAX_RETRIES):                   │
│               try:                                             │
│                   return await process_payment(                │
│                       transaction, timeout=TIMEOUT_SECONDS     │
│                   )                                            │
│               except TimeoutError:                             │
│                   if attempt == MAX_RETRIES - 1:               │
│                       raise                                    │
│                   await asyncio.sleep(2 ** attempt)            │
│       ```                                                      │
│    ✅ Commits: "PLAN: Add payment retry logic"                 │
│    ✅ Adds test:                                               │
│       ```python                                                │
│       @pytest.mark.asyncio                                     │
│       async def test_retry_on_timeout():                       │
│           with patch('payment.process_payment',                │
│                      side_effect=TimeoutError):                │
│               with pytest.raises(TimeoutError):                │
│                   await process_payment_with_retry(tx)         │
│       ```                                                      │
│    ✅ Commits: "TEST: Payment retry test"                      │
│    ✅ Pushes to GitLab: feature/fix-payment-timeout-456        │
│    ✅ Waits for export pipeline (next scheduled run)           │
│    ✅ Updates Linear: CL-123 → Status: In Review               │
└──────────────────────┬───────────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────────┐
│ 5. EXPORT PIPELINE (Triggered every 6 hours OR on-demand)       │
│    ✅ Detects new commits in GitLab                             │
│    ✅ Runs Export/Bridge Service                                │
│    ✅ Strips proprietary code                                   │
│    ✅ Secret scan: PASS                                         │
│    ✅ License check: PASS                                       │
│    ✅ Opens PR to GitHub: export/fix-payment-timeout-456        │
│    ✅ PR title: "Fix: Payment processing timeout with retry"    │
│    ✅ PR links to original issue #456                           │
└──────────────────────┬───────────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────────┐
│ 6. CITADEL-QA-BOT (Quality Assurance, ~1 min)                   │
│    ✅ GitHub Actions triggered automatically                     │
│    ✅ Runs tests:                                               │
│       - Unit tests: 23/23 ✅                                    │
│       - Integration tests: 8/8 ✅                               │
│       - Lint (black): ✅                                        │
│       - Type check (mypy): ✅                                   │
│       - Security scan (bandit): ✅                              │
│       - Coverage: 95% ✅                                        │
│    ✅ Comments on PR:                                           │
│       ```                                                       │
│       ✅ All checks passed!                                     │
│       - Tests: 31/31 passing                                   │
│       - Coverage: 95%                                          │
│       - No security issues                                     │
│       Ready to merge.                                          │
│       ```                                                      │
│    ✅ Updates Linear: CL-123 → Status: Ready for Deploy        │
└──────────────────────┬───────────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────────┐
│ 7. POLICY GATE EVALUATION (Deterministic, <100ms)               │
│    Council (via policy_gate.yaml):                              │
│    ✅ Rule: standard_pr_merge                                   │
│    ✅ Conditions met:                                           │
│       - All tests passed: ✅                                    │
│       - Security scan clean: ✅                                 │
│       - No breaking changes: ✅                                 │
│       - XP cost: 50 (acceptable for budget)                    │
│    ✅ Verdict: ALLOW                                            │
│    ✅ Record in Supabase audit_log (hash-chained)              │
│    ✅ Trigger auto-merge                                        │
└──────────────────────┬───────────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────────┐
│ 8. MERGE & RELEASE (Autonomous, <30 sec)                        │
│    GitHub Actions (triggered by auto-merge):                    │
│    ✅ Merges PR to main                                         │
│    ✅ Updates version: v1.2.3 (from VERSION file)               │
│    ✅ Generates changelog:                                      │
│       ```                                                       │
│       ## v1.2.3 (2026-01-24)                                   │
│       ### Fixes                                                │
│       - Fix: Payment processing timeout with exponential       │
│         backoff retry (#456)                                   │
│       ```                                                      │
│    ✅ Tags commit: git tag v1.2.3                              │
│    ✅ Creates GitHub Release                                    │
│    ✅ Updates Notion: Citadel-Lite Releases DB                 │
│    ✅ Posts Slack announcement:                                │
│       ```                                                       │
│       🚀 Released v1.2.3 (Payment fixes)                       │
│       - Fixed payment timeout issue                            │
│       - Added retry logic with exponential backoff             │
│       Deployment in progress...                                │
│       ```                                                      │
│    ✅ Updates Linear: CL-123 → Status: Done                    │
└──────────────────────┬───────────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────────┐
│ 9. DEPLOYMENT (Continuous, ~3 min)                              │
│    GitHub Actions (.github/workflows/deploy.yml):               │
│    ✅ Build container                                           │
│    ✅ Push to registry (ghcr.io/citadel-org/citadel-lite)      │
│    ✅ Deploy to staging                                         │
│    ✅ Run smoke tests                                           │
│    ✅ Deploy to production                                      │
│    ✅ Health checks (200 OK, latency <200ms)                   │
│    ✅ Slack notification: "✅ Deployed to production"           │
└──────────────────────┬───────────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────────┐
│ 10. AUDIT TRAIL (Immutable, cryptographically chained)          │
│     All steps recorded in Supabase guardian_logs:               │
│     - Event: TRIAGE_CREATED_TICKET (agent: citadel-triage-bot) │
│     - Event: PLANNER_CREATED_PLAN (agent: citadel-planner-bot) │
│     - Event: BUILDER_OPENED_PR (agent: citadel-builder-bot)    │
│     - Event: QA_APPROVED (agent: citadel-qa-bot)               │
│     - Event: COUNCIL_ALLOWED (verdict: ALLOW, policy: std_pr)  │
│     - Event: EXPORT_TO_GITHUB (service: export-bridge)         │
│     - Event: PR_MERGED (actor: github-actions)                 │
│     - Event: RELEASE_TAGGED (tag: v1.2.3)                      │
│     - Event: DEPLOYED_PRODUCTION (status: SUCCESS)             │
│                                                                 │
│     Each event is hash-chained and immutable.                  │
│     Proof: sha256(event_N) includes sha256(event_N-1)          │
└──────────────────────────────────────────────────────────────────┘

Total time from issue filed to production: ~8 minutes (fully autonomous)
```

---

## 5. CORE COMPONENTS SPECIFICATIONS

### 5.1 Event Backbone (n8n)

Your stack supports n8n natively. Use it for webhook orchestration and event routing.

**Core Subjects** (n8n workflows):

```yaml
# n8n Workflows

ingest.github.issue.created:
  trigger: GitHub webhook (issues)
  actions:
    - Parse issue payload
    - Route to citadel-triage-bot
    - Log to Supabase

ingest.github.pr.opened:
  trigger: GitHub webhook (pull_request)
  actions:
    - Parse PR payload
    - Route to citadel-qa-bot
    - Update Linear ticket
    - Log to Supabase

ingest.github.pr.merged:
  trigger: GitHub webhook (pull_request closed + merged)
  actions:
    - Check if release candidate
    - Trigger release workflow
    - Update Linear to "Done"
    - Post Slack announcement

ingest.gitlab.mr.merged:
  trigger: GitLab webhook (merge_request)
  actions:
    - Log to Supabase
    - Check if export needed
    - Trigger export pipeline (if main branch)

ingest.linear.issue.updated:
  trigger: Linear webhook (issue)
  actions:
    - Parse status change
    - Update GitHub issue labels
    - Log to Supabase

ingest.slack.command:
  trigger: Slack slash command (/citadel)
  actions:
    - Parse command
    - Check RBAC permissions
    - Execute action (status, freeze, approve, etc.)
    - Respond to Slack

ingest.stripe.webhook:
  trigger: Stripe webhook (invoice, payment, usage)
  actions:
    - Parse event
    - Update tenant quotas
    - Log to Supabase
    - Notify if quota exceeded

orchestrator.cycle.tick:
  trigger: Schedule (every 30-60 sec)
  actions:
    - Wake orchestrator
    - Check for new tasks
    - Execute cycle (observe → deliberate → gate → act)

task.created:
  trigger: Supabase insert (tasks table)
  actions:
    - Assign to agent
    - Estimate XP cost
    - Check budget
    - Route to agent queue

policy.gate.result:
  trigger: Policy evaluation complete
  actions:
    - Log verdict (ALLOW/DENY/REVIEW)
    - If ALLOW: execute action
    - If DENY: close task with reason
    - If REVIEW: escalate to Slack

qa.test.failed:
  trigger: GitHub Actions failure
  actions:
    - Create issue (if not exists)
    - Assign to planner-bot
    - Label: "regression"
    - Update Linear ticket

release.ready:
  trigger: Policy gate + tests passed
  actions:
    - Merge PR (via GitHub API)
    - Wait for GitHub Actions to create release
    - Update Notion release notes

export.lite.generated:
  trigger: Export pipeline complete
  actions:
    - PR opened to GitHub
    - Notify Slack
    - Log to Supabase audit
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
  "hash": "sha256(json.dumps(payload, sort_keys=True))",
  "prev_hash": "sha256(...)",
  "signature": "ed25519(...)"
}
```

---

### 5.2 Task Ledger (Supabase PostgreSQL)

**Core Tables**:

```sql
-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Enable Row-Level Security
ALTER DATABASE postgres SET app.current_tenant_id TO '';

-- ============================================================================
-- TASKS TABLE
-- ============================================================================
CREATE TABLE tasks (
    task_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id VARCHAR(255) NOT NULL,
    type VARCHAR(50) NOT NULL,  -- PLAN, BUILD, TEST, DEPLOY, DOCS, RELEASE
    status VARCHAR(50) NOT NULL DEFAULT 'CREATED',  -- CREATED, ASSIGNED, IN_PROGRESS, COMPLETED, FAILED
    priority INTEGER DEFAULT 5,  -- 1 (highest) to 10 (lowest)
    owner_agent VARCHAR(255),  -- agent assigned to this task
    required_agents TEXT[],  -- agents needed for approval
    input_refs JSONB,  -- links to issue/pr/doc pointers
    result_refs JSONB,  -- output artifacts
    cost_xp INTEGER DEFAULT 0,  -- XP required
    cost_budget NUMERIC DEFAULT 0.0,  -- $ cost (for metering)
    created_at TIMESTAMP DEFAULT NOW(),
    assigned_at TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    deadline TIMESTAMP,
    error_message TEXT,
    metadata JSONB DEFAULT '{}',
    
    CONSTRAINT valid_status CHECK (status IN ('CREATED', 'ASSIGNED', 'IN_PROGRESS', 'COMPLETED', 'FAILED', 'CANCELLED')),
    CONSTRAINT valid_type CHECK (type IN ('PLAN', 'BUILD', 'TEST', 'DEPLOY', 'DOCS', 'RELEASE', 'TRIAGE', 'REVIEW'))
);

CREATE INDEX idx_tasks_tenant ON tasks(tenant_id);
CREATE INDEX idx_tasks_status ON tasks(status);
CREATE INDEX idx_tasks_owner ON tasks(owner_agent);
CREATE INDEX idx_tasks_created ON tasks(created_at);

-- Row-Level Security
ALTER TABLE tasks ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Tasks filtered by tenant" ON tasks
    FOR ALL
    USING (tenant_id = current_setting('app.current_tenant_id', true));

-- ============================================================================
-- DECISIONS TABLE
-- ============================================================================
CREATE TABLE decisions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    task_id UUID REFERENCES tasks(task_id),
    decided_at TIMESTAMP DEFAULT NOW(),
    decision VARCHAR(20) NOT NULL,  -- ALLOW, REVIEW, DENY
    reason TEXT NOT NULL,
    policy_gate_name VARCHAR(255),
    policy_version VARCHAR(50),
    required_approvals TEXT[],
    approvers JSONB DEFAULT '[]',  -- list of who approved
    metadata JSONB DEFAULT '{}',
    
    CONSTRAINT valid_decision CHECK (decision IN ('ALLOW', 'REVIEW', 'DENY'))
);

CREATE INDEX idx_decisions_task ON decisions(task_id);
CREATE INDEX idx_decisions_decided ON decisions(decided_at);

-- ============================================================================
-- ACTIONS TABLE
-- ============================================================================
CREATE TABLE actions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    decision_id UUID REFERENCES decisions(id),
    task_id UUID REFERENCES tasks(task_id),
    action_name VARCHAR(100) NOT NULL,  -- "open_pr", "run_tests", "merge", etc.
    idempotency_key VARCHAR(64) UNIQUE,  -- sha256 hash for deduplication
    input_params JSONB,
    output_result JSONB,
    status VARCHAR(50) DEFAULT 'PENDING',  -- PENDING, EXECUTING, SUCCESS, FAILED
    started_at TIMESTAMP,
    executed_at TIMESTAMP,
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    
    CONSTRAINT valid_status CHECK (status IN ('PENDING', 'EXECUTING', 'SUCCESS', 'FAILED'))
);

CREATE INDEX idx_actions_task ON actions(task_id);
CREATE INDEX idx_actions_status ON actions(status);
CREATE INDEX idx_actions_idempotency ON actions(idempotency_key);

-- ============================================================================
-- ARTIFACTS TABLE
-- ============================================================================
CREATE TABLE artifacts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    action_id UUID REFERENCES actions(id),
    task_id UUID REFERENCES tasks(task_id),
    artifact_type VARCHAR(50) NOT NULL,  -- PR, TEST_REPORT, BUILD_LOG, etc.
    artifact_url TEXT,
    artifact_hash VARCHAR(64),  -- sha256 of artifact
    size_bytes BIGINT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_artifacts_task ON artifacts(task_id);
CREATE INDEX idx_artifacts_type ON artifacts(artifact_type);

-- ============================================================================
-- AUDIT LOG (Immutable, Hash-Chained)
-- ============================================================================
CREATE TABLE audit_log (
    id BIGSERIAL PRIMARY KEY,
    event_id UUID DEFAULT uuid_generate_v4(),
    event_type VARCHAR(100) NOT NULL,
    tenant_id VARCHAR(255) NOT NULL,
    agent_id VARCHAR(255),
    resource_type VARCHAR(50),
    resource_id VARCHAR(255),
    action_taken TEXT NOT NULL,
    previous_state JSONB,
    new_state JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    hash VARCHAR(64) NOT NULL,  -- sha256 of this event
    prev_hash VARCHAR(64),  -- sha256 of previous event (chain)
    signature TEXT,  -- ed25519 signature
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX idx_audit_tenant ON audit_log(tenant_id);
CREATE INDEX idx_audit_created ON audit_log(created_at);
CREATE INDEX idx_audit_agent ON audit_log(agent_id);
CREATE INDEX idx_audit_hash ON audit_log(hash);

-- Immutability: Prevent updates/deletes
CREATE OR REPLACE FUNCTION prevent_audit_modification()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'Audit log is immutable. Cannot modify or delete entries.';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER audit_log_immutable_update
    BEFORE UPDATE ON audit_log
    FOR EACH ROW
    EXECUTE FUNCTION prevent_audit_modification();

CREATE TRIGGER audit_log_immutable_delete
    BEFORE DELETE ON audit_log
    FOR EACH ROW
    EXECUTE FUNCTION prevent_audit_modification();

-- Hash chain validation function
CREATE OR REPLACE FUNCTION validate_audit_chain()
RETURNS BOOLEAN AS $$
DECLARE
    current_record RECORD;
    prev_record RECORD;
    computed_hash VARCHAR(64);
BEGIN
    FOR current_record IN 
        SELECT * FROM audit_log ORDER BY id
    LOOP
        -- Compute hash of current event
        computed_hash := encode(
            digest(
                current_record.event_type || 
                current_record.action_taken || 
                current_record.created_at::TEXT ||
                COALESCE(current_record.prev_hash, ''),
                'sha256'
            ),
            'hex'
        );
        
        -- Verify hash matches
        IF current_record.hash != computed_hash THEN
            RAISE NOTICE 'Hash mismatch at id=%', current_record.id;
            RETURN FALSE;
        END IF;
        
        -- Verify chain (prev_hash matches previous event's hash)
        IF current_record.prev_hash IS NOT NULL THEN
            SELECT * INTO prev_record 
            FROM audit_log 
            WHERE id = current_record.id - 1;
            
            IF prev_record.hash != current_record.prev_hash THEN
                RAISE NOTICE 'Chain broken at id=%', current_record.id;
                RETURN FALSE;
            END IF;
        END IF;
    END LOOP;
    
    RETURN TRUE;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- AGENTS TABLE
-- ============================================================================
CREATE TABLE agents (
    agent_id VARCHAR(255) PRIMARY KEY,
    agent_name VARCHAR(255) NOT NULL,
    agent_type VARCHAR(50) NOT NULL,  -- planner, builder, qa, docs, release, triage
    caps_grade VARCHAR(10) DEFAULT 'C',  -- D, C, B, A, S
    xp INTEGER DEFAULT 0,
    trust_score FLOAT DEFAULT 0.5,
    total_tasks_completed INTEGER DEFAULT 0,
    total_tasks_failed INTEGER DEFAULT 0,
    last_active TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    metadata JSONB DEFAULT '{}',
    
    CONSTRAINT valid_caps_grade CHECK (caps_grade IN ('D', 'C', 'B', 'A', 'S')),
    CONSTRAINT valid_agent_type CHECK (agent_type IN ('planner', 'builder', 'qa', 'docs', 'release', 'triage'))
);

CREATE INDEX idx_agents_type ON agents(agent_type);
CREATE INDEX idx_agents_caps ON agents(caps_grade);

-- ============================================================================
-- GUARDIAN LOGS (Cryptographic Event Chain)
-- ============================================================================
CREATE TABLE guardian_logs (
    id BIGSERIAL PRIMARY KEY,
    event_timestamp TIMESTAMP DEFAULT NOW(),
    agent_id VARCHAR(255),
    action VARCHAR(100) NOT NULL,
    result_status VARCHAR(50) NOT NULL,  -- SUCCESS, FAILURE
    policy_verdict VARCHAR(20),  -- ALLOW, DENY, REVIEW
    event_hash VARCHAR(64) NOT NULL,
    prev_hash VARCHAR(64),
    metadata JSONB DEFAULT '{}',
    
    CONSTRAINT valid_result_status CHECK (result_status IN ('SUCCESS', 'FAILURE')),
    CONSTRAINT valid_policy_verdict CHECK (policy_verdict IN ('ALLOW', 'DENY', 'REVIEW', NULL))
);

CREATE INDEX idx_guardian_timestamp ON guardian_logs(event_timestamp);
CREATE INDEX idx_guardian_agent ON guardian_logs(agent_id);

-- ============================================================================
-- FAILED ACTIONS (Dead-Letter Queue)
-- ============================================================================
CREATE TABLE failed_actions (
    id BIGSERIAL PRIMARY KEY,
    task_id UUID REFERENCES tasks(task_id),
    action_name VARCHAR(100),
    error_message TEXT,
    retry_count INT DEFAULT 0,
    max_retries INT DEFAULT 3,
    next_retry_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    
    CONSTRAINT retry_backoff CHECK (next_retry_at > created_at)
);

CREATE INDEX idx_failed_retry ON failed_actions(next_retry_at);

-- Automatic escalation: if retry_count >= max_retries, create incident
CREATE OR REPLACE FUNCTION escalate_failed_action()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.retry_count >= NEW.max_retries THEN
        -- Create incident (you'd implement this table separately)
        INSERT INTO incidents (type, description, severity, metadata)
        VALUES (
            'FAILED_ACTION_ESCALATION',
            'Action failed after ' || NEW.max_retries || ' retries',
            'HIGH',
            json_build_object(
                'task_id', NEW.task_id,
                'action_name', NEW.action_name,
                'error', NEW.error_message
            )
        );
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER escalate_on_max_retries
AFTER UPDATE ON failed_actions
FOR EACH ROW
WHEN (NEW.retry_count >= NEW.max_retries)
EXECUTE FUNCTION escalate_failed_action();

-- ============================================================================
-- LEASES (For Orchestrator Leader Election)
-- ============================================================================
CREATE TABLE leases (
    lease_name VARCHAR(255) PRIMARY KEY,
    holder_id UUID NOT NULL,
    acquired_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP NOT NULL,
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX idx_leases_expires ON leases(expires_at);

-- ============================================================================
-- USAGE EVENTS (For Stripe Metering)
-- ============================================================================
CREATE TABLE usage_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id VARCHAR(255) NOT NULL,
    event_type VARCHAR(100) NOT NULL,  -- agent_action_completed, api_call, deployment, export_to_public
    quantity INTEGER DEFAULT 1,
    recorded_at TIMESTAMP DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX idx_usage_tenant ON usage_events(tenant_id);
CREATE INDEX idx_usage_recorded ON usage_events(recorded_at);
CREATE INDEX idx_usage_type ON usage_events(event_type);

-- ============================================================================
-- SYSTEM STATE (For Global Configuration)
-- ============================================================================
CREATE TABLE system_state (
    key VARCHAR(255) PRIMARY KEY,
    value JSONB NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW(),
    updated_by VARCHAR(255)
);

-- Insert default freeze_enabled = false
INSERT INTO system_state (key, value, updated_by)
VALUES ('freeze_enabled', 'false', 'system')
ON CONFLICT (key) DO NOTHING;

-- ============================================================================
-- APPROVALS (For Governance)
-- ============================================================================
CREATE TABLE approvals (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    approval_type VARCHAR(50) NOT NULL,  -- 'pr_merge', 'release', 'export_public', 'emergency_deploy'
    resource_id VARCHAR(255) NOT NULL,   -- PR #, release tag, export version
    approver_id VARCHAR(255),   -- Slack user ID or agent ID
    expires_at TIMESTAMP,       -- Approval expires after 24h
    created_at TIMESTAMP DEFAULT NOW(),
    status VARCHAR(50) DEFAULT 'PENDING',  -- 'PENDING', 'APPROVED', 'DENIED', 'EXPIRED'
    reason TEXT,
    
    CONSTRAINT valid_approval_type CHECK (approval_type IN ('pr_merge', 'release', 'export_public', 'emergency_deploy', 'policy_change')),
    CONSTRAINT valid_status CHECK (status IN ('PENDING', 'APPROVED', 'DENIED', 'EXPIRED'))
);

CREATE INDEX idx_approvals_expires ON approvals(expires_at);
CREATE INDEX idx_approvals_status ON approvals(status);
CREATE INDEX idx_approvals_resource ON approvals(resource_id);

-- ============================================================================
-- INCIDENTS (For Break-Glass Scenarios)
-- ============================================================================
CREATE TABLE incidents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    type VARCHAR(50) NOT NULL,
    description TEXT,
    severity VARCHAR(20) DEFAULT 'MEDIUM',  -- LOW, MEDIUM, HIGH, CRITICAL
    status VARCHAR(50) DEFAULT 'OPEN',  -- OPEN, INVESTIGATING, RESOLVED, CLOSED
    created_at TIMESTAMP DEFAULT NOW(),
    resolved_at TIMESTAMP,
    metadata JSONB DEFAULT '{}',
    
    CONSTRAINT valid_severity CHECK (severity IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    CONSTRAINT valid_status CHECK (status IN ('OPEN', 'INVESTIGATING', 'RESOLVED', 'CLOSED'))
);

CREATE INDEX idx_incidents_severity ON incidents(severity);
CREATE INDEX idx_incidents_status ON incidents(status);
CREATE INDEX idx_incidents_created ON incidents(created_at);
```

---

### 5.3 Orchestrator (Heartbeat)

**Cycle**: Every 30-60 seconds (configurable)

```python
# src/citadel_nexus/orchestrator.py

import asyncio
import os
from datetime import datetime, timedelta
from typing import List, Dict, Any
import logging
from uuid import uuid4

from .supabase_client import SupabaseClient
from .policy_gate import PolicyGate
from .github_client import GitHubClient
from .linear_client import LinearClient
from .slack_client import SlackClient
from .notion_client import NotionClient

logger = logging.getLogger(__name__)


class Orchestrator:
    """Main orchestration loop: observe → deliberate → gate → act → reflect"""
    
    def __init__(self):
        self.cycle_interval = int(os.getenv('CYCLE_INTERVAL_SECONDS', '30'))
        self.lease_id = uuid4()
        self.is_leader = False
        
        # Clients
        self.supabase = SupabaseClient()
        self.policy_gate = PolicyGate()
        self.github = GitHubClient()
        self.linear = LinearClient()
        self.slack = SlackClient()
        self.notion = NotionClient()
        
        logger.info(f"Orchestrator initialized (cycle: {self.cycle_interval}s)")
    
    async def run(self):
        """Main loop with leader election."""
        while True:
            try:
                # Attempt to acquire leader lease
                is_leader = await self.try_acquire_lease()
                
                if is_leader:
                    self.is_leader = True
                    logger.debug("Leader lease acquired, running cycle...")
                    
                    try:
                        await self.run_cycle()
                    except Exception as e:
                        logger.error(f"Cycle failed: {e}", exc_info=True)
                        # Don't crash, just log and continue
                else:
                    self.is_leader = False
                    logger.debug("Standby mode (another orchestrator is leader)")
                    await asyncio.sleep(5)  # Wait before retrying
                
            except Exception as e:
                logger.error(f"Fatal error in orchestrator loop: {e}", exc_info=True)
                await asyncio.sleep(10)  # Back off before retry
    
    async def try_acquire_lease(self) -> bool:
        """Attempt to acquire leader lease (30-second TTL)."""
        expires_at = datetime.utcnow() + timedelta(seconds=30)
        
        result = await self.supabase.client.from_('leases').upsert({
            'lease_name': 'orchestrator',
            'holder_id': str(self.lease_id),
            'expires_at': expires_at.isoformat()
        }, on_conflict='lease_name').execute()
        
        # Check if we got the lease
        lease = result.data[0] if result.data else None
        return lease and lease['holder_id'] == str(self.lease_id)
    
    async def run_cycle(self):
        """Main orchestration cycle."""
        cycle_start = datetime.utcnow()
        logger.info("=== CYCLE START ===")
        
        # Phase 1: OBSERVE
        state = await self.observe_state()
        logger.info(f"Observed: {len(state['unassigned_issues'])} issues, "
                   f"{len(state['open_prs'])} PRs, {len(state['failed_tests'])} failures")
        
        # Phase 2: DELIBERATE
        decisions = await self.deliberate(state)
        logger.info(f"Generated {len(decisions)} decisions")
        
        # Phase 3: GATE (Policy)
        verdicts = await self.policy_gate.evaluate(decisions)
        logger.info(f"Policy verdicts: {self.summarize_verdicts(verdicts)}")
        
        # Phase 4: ACT
        for verdict in verdicts:
            if verdict['verdict'] == 'ALLOW':
                try:
                    await self.execute_action(verdict)
                except Exception as e:
                    logger.error(f"Action failed: {e}", exc_info=True)
                    # Log to failed_actions table
                    await self.log_failed_action(verdict, str(e))
        
        # Phase 5: REFLECT
        await self.reflect(verdicts)
        
        cycle_duration = (datetime.utcnow() - cycle_start).total_seconds()
        logger.info(f"=== CYCLE END ({cycle_duration:.2f}s) ===")
        
        # Sleep until next cycle
        sleep_time = max(0, self.cycle_interval - cycle_duration)
        await asyncio.sleep(sleep_time)
    
    async def observe_state(self) -> Dict[str, Any]:
        """Phase 1: Observe current system state."""
        
        # Check GitHub issues (unassigned, no Linear ticket)
        unassigned_issues = await self.github.get_unassigned_issues()
        
        # Check open PRs (pending review/tests)
        open_prs = await self.github.get_open_prs()
        
        # Check failed CI jobs
        failed_tests = await self.github.get_failed_ci_jobs()
        
        # Check Linear backlog (unstarted)
        linear_backlog = await self.linear.get_backlog_items()
        
        # Check Notion specs (pending implementation)
        notion_specs = await self.notion.get_pending_specs()
        
        # Check freeze mode
        freeze_enabled = await self.get_freeze_mode()
        
        return {
            'unassigned_issues': unassigned_issues,
            'open_prs': open_prs,
            'failed_tests': failed_tests,
            'linear_backlog': linear_backlog,
            'notion_specs': notion_specs,
            'freeze_enabled': freeze_enabled,
            'timestamp': datetime.utcnow().isoformat()
        }
    
    async def deliberate(self, state: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Phase 2: Generate decisions based on state."""
        decisions = []
        
        # Freeze mode: only allow monitoring, no actions
        if state['freeze_enabled']:
            logger.warning("Freeze mode enabled, skipping action generation")
            return decisions
        
        # Decision 1: Triage new issues
        for issue in state['unassigned_issues']:
            decisions.append({
                'type': 'TRIAGE',
                'action': 'triage_issue',
                'target': issue,
                'agent': 'citadel-triage-bot',
                'reason': 'New issue needs labeling and Linear ticket',
                'cost_xp': 5
            })
        
        # Decision 2: Plan issues (if triaged, no plan yet)
        for issue in state['unassigned_issues']:
            if issue.get('labels') and not issue.get('has_plan'):
                decisions.append({
                    'type': 'PLAN',
                    'action': 'create_plan',
                    'target': issue,
                    'agent': 'citadel-planner-bot',
                    'reason': 'Issue is triaged but has no implementation plan',
                    'cost_xp': 20
                })
        
        # Decision 3: Build implementations (if planned, no PR yet)
        for issue in state['unassigned_issues']:
            if issue.get('has_plan') and not issue.get('has_pr'):
                decisions.append({
                    'type': 'BUILD',
                    'action': 'implement_fix',
                    'target': issue,
                    'agent': 'citadel-builder-bot',
                    'reason': 'Issue has plan but no PR yet',
                    'cost_xp': 50
                })
        
        # Decision 4: Review PRs (if tests passed, no review yet)
        for pr in state['open_prs']:
            if pr.get('tests_passed') and not pr.get('has_review'):
                decisions.append({
                    'type': 'REVIEW',
                    'action': 'review_pr',
                    'target': pr,
                    'agent': 'citadel-qa-bot',
                    'reason': 'PR tests passed, ready for review',
                    'cost_xp': 15
                })
        
        # Decision 5: Merge PRs (if reviewed + approved)
        for pr in state['open_prs']:
            if pr.get('has_review') and pr.get('approved'):
                decisions.append({
                    'type': 'MERGE',
                    'action': 'merge_pr',
                    'target': pr,
                    'agent': 'citadel-release-bot',
                    'reason': 'PR approved and ready to merge',
                    'cost_xp': 10
                })
        
        # Decision 6: Fix failed tests (create regression issue)
        for failure in state['failed_tests']:
            decisions.append({
                'type': 'FIX_REGRESSION',
                'action': 'create_regression_issue',
                'target': failure,
                'agent': 'citadel-qa-bot',
                'reason': 'Test failure detected, needs investigation',
                'cost_xp': 5
            })
        
        return decisions
    
    async def execute_action(self, verdict: Dict[str, Any]):
        """Phase 4: Execute allowed action."""
        action = verdict['action']
        target = verdict['target']
        agent = verdict['agent']
        
        logger.info(f"Executing: {action} by {agent}")
        
        # Create task record
        task = await self.supabase.client.from_('tasks').insert({
            'tenant_id': 'citadel-org',  # TODO: dynamic tenant
            'type': verdict['type'],
            'status': 'IN_PROGRESS',
            'owner_agent': agent,
            'input_refs': target,
            'cost_xp': verdict.get('cost_xp', 0)
        }).execute()
        
        task_id = task.data[0]['task_id']
        
        # Dispatch to agent
        if action == 'triage_issue':
            await self.triage_issue(task_id, target)
        elif action == 'create_plan':
            await self.create_plan(task_id, target)
        elif action == 'implement_fix':
            await self.implement_fix(task_id, target)
        elif action == 'review_pr':
            await self.review_pr(task_id, target)
        elif action == 'merge_pr':
            await self.merge_pr(task_id, target)
        elif action == 'create_regression_issue':
            await self.create_regression_issue(task_id, target)
        else:
            logger.warning(f"Unknown action: {action}")
        
        # Update task status
        await self.supabase.client.from_('tasks').update({
            'status': 'COMPLETED',
            'completed_at': datetime.utcnow().isoformat()
        }).eq('task_id', task_id).execute()
    
    async def triage_issue(self, task_id: str, issue: Dict[str, Any]):
        """Triage: Label issue + create Linear ticket."""
        issue_number = issue['number']
        
        # Label issue
        labels = self.determine_labels(issue)
        await self.github.add_labels(issue_number, labels)
        
        # Create Linear ticket
        linear_ticket = await self.linear.create_issue({
            'title': issue['title'],
            'description': issue['body'],
            'team_key': 'CL',
            'labels': labels,
            'metadata': {'github_issue_id': issue_number}
        })
        
        # Comment on GitHub
        await self.github.comment_on_issue(
            issue_number,
            f"I'm on it! Created Linear ticket: {linear_ticket['url']}"
        )
        
        # Log to audit
        await self.audit_log('TRIAGE_CREATED_TICKET', {
            'agent_id': 'citadel-triage-bot',
            'github_issue': issue_number,
            'linear_ticket': linear_ticket['id']
        })
    
    async def create_plan(self, task_id: str, issue: Dict[str, Any]):
        """Planner: Analyze issue and create implementation plan."""
        # Call Claude API to generate plan
        plan = await self.call_claude_for_plan(issue)
        
        # Comment plan on GitHub
        await self.github.comment_on_issue(
            issue['number'],
            f"## Implementation Plan\n\n{plan}"
        )
        
        # Update Linear ticket
        await self.linear.update_issue_status(
            issue['linear_ticket_id'],
            'Planned'
        )
        
        await self.audit_log('PLANNER_CREATED_PLAN', {
            'agent_id': 'citadel-planner-bot',
            'github_issue': issue['number'],
            'plan_length': len(plan)
        })
    
    async def implement_fix(self, task_id: str, issue: Dict[str, Any]):
        """Builder: Generate code and open PR."""
        # This would call Claude to generate code
        # For now, placeholder
        logger.info(f"Builder: Implementing fix for issue #{issue['number']}")
        
        # In reality:
        # 1. Clone GitLab repo
        # 2. Create feature branch
        # 3. Generate code via Claude
        # 4. Commit to GitLab
        # 5. Wait for export pipeline (or trigger it)
        
        await self.audit_log('BUILDER_STARTED_IMPLEMENTATION', {
            'agent_id': 'citadel-builder-bot',
            'github_issue': issue['number']
        })
    
    async def review_pr(self, task_id: str, pr: Dict[str, Any]):
        """QA: Review PR and comment results."""
        # Check CI status
        ci_status = await self.github.get_ci_status(pr['number'])
        
        if ci_status['all_passed']:
            await self.github.approve_pr(pr['number'])
            await self.github.comment_on_pr(
                pr['number'],
                "✅ All checks passed! Ready to merge."
            )
        else:
            await self.github.request_changes(pr['number'])
            await self.github.comment_on_pr(
                pr['number'],
                f"❌ Some checks failed:\n{ci_status['failures']}"
            )
        
        await self.audit_log('QA_REVIEWED_PR', {
            'agent_id': 'citadel-qa-bot',
            'pr_number': pr['number'],
            'approved': ci_status['all_passed']
        })
    
    async def merge_pr(self, task_id: str, pr: Dict[str, Any]):
        """Merge approved PR (via GitHub API, triggers release workflow)."""
        await self.github.merge_pr(pr['number'])
        
        # Update Linear
        await self.linear.update_issue_status(
            pr['linear_ticket_id'],
            'Done'
        )
        
        await self.audit_log('PR_MERGED', {
            'actor': 'citadel-release-bot',
            'pr_number': pr['number']
        })
    
    async def create_regression_issue(self, task_id: str, failure: Dict[str, Any]):
        """QA: Create issue for test failure."""
        issue = await self.github.create_issue({
            'title': f"Regression: {failure['test_name']} failing",
            'body': f"Test failure detected:\n\n```\n{failure['error']}\n```",
            'labels': ['bug', 'regression', 'high-priority']
        })
        
        await self.audit_log('QA_CREATED_REGRESSION_ISSUE', {
            'agent_id': 'citadel-qa-bot',
            'issue_number': issue['number'],
            'test_name': failure['test_name']
        })
    
    async def reflect(self, verdicts: List[Dict[str, Any]]):
        """Phase 5: Update metrics, trust scores, XP."""
        # Count outcomes
        allowed = sum(1 for v in verdicts if v['verdict'] == 'ALLOW')
        denied = sum(1 for v in verdicts if v['verdict'] == 'DENY')
        review = sum(1 for v in verdicts if v['verdict'] == 'REVIEW')
        
        # Log metrics
        logger.info(f"Cycle metrics: {allowed} allowed, {denied} denied, {review} review")
        
        # Award XP to agents
        for verdict in verdicts:
            if verdict['verdict'] == 'ALLOW':
                agent_id = verdict['agent']
                xp_awarded = verdict.get('cost_xp', 0)
                
                await self.supabase.client.from_('agents').update({
                    'xp': self.supabase.client.from_('agents').select('xp').eq('agent_id', agent_id).single().data['xp'] + xp_awarded,
                    'total_tasks_completed': self.supabase.client.from_('agents').select('total_tasks_completed').eq('agent_id', agent_id).single().data['total_tasks_completed'] + 1
                }).eq('agent_id', agent_id).execute()
    
    def summarize_verdicts(self, verdicts: List[Dict[str, Any]]) -> str:
        """Summarize policy verdicts for logging."""
        allowed = sum(1 for v in verdicts if v['verdict'] == 'ALLOW')
        denied = sum(1 for v in verdicts if v['verdict'] == 'DENY')
        review = sum(1 for v in verdicts if v['verdict'] == 'REVIEW')
        return f"{allowed} allowed, {denied} denied, {review} review"
    
    def determine_labels(self, issue: Dict[str, Any]) -> List[str]:
        """Determine labels for issue (simple keyword matching)."""
        body_lower = (issue.get('body') or '').lower()
        title_lower = issue['title'].lower()
        text = title_lower + ' ' + body_lower
        
        labels = []
        
        if 'bug' in text or 'fix' in text or 'error' in text:
            labels.append('bug')
        if 'feature' in text or 'add' in text:
            labels.append('enhancement')
        if 'docs' in text or 'documentation' in text:
            labels.append('documentation')
        if 'payment' in text:
            labels.append('payment')
        if 'api' in text:
            labels.append('api')
        if 'urgent' in text or 'critical' in text:
            labels.append('high-priority')
        
        return labels or ['needs-triage']
    
    async def call_claude_for_plan(self, issue: Dict[str, Any]) -> str:
        """Call Claude API to generate implementation plan."""
        # Placeholder
        return f"""### Problem Statement
{issue['title']}

### Solution Approach
1. Identify root cause
2. Implement fix
3. Add tests
4. Update docs

### Implementation Steps
1. [ ] Investigate code path
2. [ ] Write test case
3. [ ] Implement solution
4. [ ] Run tests
5. [ ] Open PR
"""
    
    async def get_freeze_mode(self) -> bool:
        """Check if freeze mode is enabled."""
        result = await self.supabase.client.from_('system_state').select('value').eq('key', 'freeze_enabled').single().execute()
        return result.data['value'] == 'true' if result.data else False
    
    async def audit_log(self, event_type: str, metadata: Dict[str, Any]):
        """Write to audit log with hash chaining."""
        # Get previous hash
        prev_result = await self.supabase.client.from_('audit_log').select('hash').order('id', desc=True).limit(1).execute()
        prev_hash = prev_result.data[0]['hash'] if prev_result.data else None
        
        # Compute hash
        import hashlib
        import json
        
        event_data = json.dumps({
            'event_type': event_type,
            'metadata': metadata,
            'timestamp': datetime.utcnow().isoformat(),
            'prev_hash': prev_hash
        }, sort_keys=True)
        
        event_hash = hashlib.sha256(event_data.encode()).hexdigest()
        
        # Insert
        await self.supabase.client.from_('audit_log').insert({
            'event_type': event_type,
            'tenant_id': 'citadel-org',
            'agent_id': metadata.get('agent_id'),
            'action_taken': json.dumps(metadata),
            'hash': event_hash,
            'prev_hash': prev_hash
        }).execute()
    
    async def log_failed_action(self, verdict: Dict[str, Any], error: str):
        """Log failed action to DLQ."""
        await self.supabase.client.from_('failed_actions').insert({
            'action_name': verdict['action'],
            'error_message': error,
            'retry_count': 0,
            'next_retry_at': (datetime.utcnow() + timedelta(minutes=1)).isoformat()
        }).execute()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    orchestrator = Orchestrator()
    asyncio.run(orchestrator.run())
```

---

### 5.4 Policy Gate (Simple v0)

```yaml
# policies/core_gates.yaml

version: "1.0"

gates:
  # Gate 1: Standard PR creation
  - name: "standard_pr_creation"
    description: "Allow agents to create PRs with basic checks"
    trigger: "decision.type == 'BUILD'"
    rules:
      - condition: "agent_id == 'citadel-builder-bot'"
        verdict: "ALLOW"
        reason: "Authorized agent opening PR"
      
      - condition: "pr.title contains 'DELETE' or pr.title contains 'DROP' or pr.title contains 'TRUNCATE'"
        verdict: "DENY"
        reason: "Destructive operations blocked"
      
      - condition: "pr.labels contains 'experimental'"
        verdict: "REVIEW"
        reason: "Experimental feature requires manual approval"
      
      - condition: "cost_xp > 100"
        verdict: "REVIEW"
        reason: "High-cost action requires human oversight"

  # Gate 2: PR merge approval
  - name: "standard_pr_merge"
    description: "Allow merging if tests pass and approved"
    trigger: "decision.type == 'MERGE'"
    rules:
      - condition: "all_tests_passed == true and code_reviewed == true"
        verdict: "ALLOW"
        reason: "All gates passed"
      
      - condition: "security_scan_failed == true"
        verdict: "DENY"
        reason: "Security vulnerabilities detected"
      
      - condition: "coverage < 80"
        verdict: "REVIEW"
        reason: "Test coverage below threshold"
      
      - condition: "freeze_enabled == true"
        verdict: "DENY"
        reason: "Deployments frozen (freeze mode)"

  # Gate 3: Production deployment
  - name: "production_deployment"
    description: "Allow production deployments with strict checks"
    trigger: "decision.type == 'DEPLOY' and target == 'PRODUCTION'"
    rules:
      - condition: "time_of_day > 22:00 or time_of_day < 08:00"
        verdict: "DENY"
        reason: "No deployments outside business hours"
      
      - condition: "all_tests_passed and smoke_tests_passed and agent.caps_grade >= 'A'"
        verdict: "ALLOW"
        reason: "High-grade agent with passing tests"
      
      - condition: "agent.caps_grade < 'B'"
        verdict: "REVIEW"
        reason: "Low-grade agent requires human approval for prod deploy"

  # Gate 4: Export to public
  - name: "export_to_public"
    description: "Allow export to GitHub if security checks pass"
    trigger: "decision.type == 'EXPORT'"
    rules:
      - condition: "no_secrets_detected and no_proprietary_code"
        verdict: "ALLOW"
        reason: "Export safe for public"
      
      - condition: "license_valid and copyright_headers_present"
        verdict: "ALLOW"
        reason: "Licensing requirements met"
      
      - condition: "build_passes_public_ci"
        verdict: "ALLOW"
        reason: "Public tests passed"
      
      - condition: "secrets_detected == true"
        verdict: "DENY"
        reason: "Secrets found in code, blocking export"

  # Gate 5: Regression fix
  - name: "fix_regression"
    description: "Allow immediate fix for regressions"
    trigger: "decision.type == 'FIX_REGRESSION'"
    rules:
      - condition: "severity == 'HIGH' or severity == 'CRITICAL'"
        verdict: "ALLOW"
        reason: "Critical regression, fast-track fix"
      
      - condition: "severity == 'LOW'"
        verdict: "REVIEW"
        reason: "Low-severity regression can wait for review"
```

**Policy Gate Implementation** (Python):

```python
# src/citadel_nexus/policy_gate.py

import yaml
from typing import List, Dict, Any
from datetime import datetime


class PolicyGate:
    """Evaluates decisions against policy rules (YAML-driven)."""
    
    def __init__(self, policy_path: str = 'policies/core_gates.yaml'):
        with open(policy_path) as f:
            self.policy = yaml.safe_load(f)
    
    async def evaluate(self, decisions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Evaluate all decisions and return verdicts."""
        verdicts = []
        
        for decision in decisions:
            verdict = await self.evaluate_single(decision)
            verdicts.append({
                **decision,
                'verdict': verdict['verdict'],
                'verdict_reason': verdict['reason'],
                'policy_gate': verdict['gate_name']
            })
        
        return verdicts
    
    async def evaluate_single(self, decision: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate a single decision."""
        decision_type = decision['type']
        
        # Find matching gate
        gate = self.find_matching_gate(decision)
        
        if not gate:
            # No gate found, default DENY
            return {
                'verdict': 'DENY',
                'reason': 'No matching policy gate found',
                'gate_name': None
            }
        
        # Evaluate rules
        for rule in gate['rules']:
            if self.evaluate_condition(rule['condition'], decision):
                return {
                    'verdict': rule['verdict'],
                    'reason': rule['reason'],
                    'gate_name': gate['name']
                }
        
        # No rule matched, default DENY
        return {
            'verdict': 'DENY',
            'reason': 'No matching rule in policy gate',
            'gate_name': gate['name']
        }
    
    def find_matching_gate(self, decision: Dict[str, Any]) -> Dict[str, Any]:
        """Find policy gate that matches decision."""
        for gate in self.policy['gates']:
            trigger = gate['trigger']
            
            # Simple evaluation (can be extended with proper parser)
            if self.evaluate_trigger(trigger, decision):
                return gate
        
        return None
    
    def evaluate_trigger(self, trigger: str, decision: Dict[str, Any]) -> bool:
        """Evaluate trigger condition (simple string matching)."""
        # Example trigger: "decision.type == 'BUILD'"
        # This is simplified; in production, use a proper expression parser
        
        if 'decision.type ==' in trigger:
            expected_type = trigger.split("'")[1]
            return decision['type'] == expected_type
        
        if 'decision.type == \'DEPLOY\' and target == \'PRODUCTION\'' in trigger:
            return decision['type'] == 'DEPLOY' and decision.get('target') == {}'PRODUCTION'
        
        if 'decision.type == \'EXPORT\'' in trigger:
            return decision['type'] == 'EXPORT'
        
        if 'decision.type == \'FIX_REGRESSION\'' in trigger:
            return decision['type'] == 'FIX_REGRESSION'
        
        return False
    
    def evaluate_condition(self, condition: str, decision: Dict[str, Any]) -> bool:
        """Evaluate rule condition (simple logic)."""
        # This is simplified; in production, use a proper expression evaluator
        # like simpleeval or write a custom DSL parser
        
        context = {
            'agent_id': decision.get('agent'),
            'all_tests_passed': decision.get('target', {}).get('tests_passed', False),
            'code_reviewed': decision.get('target', {}).get('has_review', False),
            'cost_xp': decision.get('cost_xp', 0),
            'freeze_enabled': False,  # Would fetch from DB
            'security_scan_failed': decision.get('target', {}).get('security_failed', False),
            'coverage': decision.get('target', {}).get('coverage', 100),
            'time_of_day': datetime.utcnow().hour,
            'agent': {
                'caps_grade': 'B'  # Would fetch from agents table
            },
            'no_secrets_detected': decision.get('target', {}).get('no_secrets', True),
            'no_proprietary_code': decision.get('target', {}).get('no_proprietary', True),
            'license_valid': decision.get('target', {}).get('license_valid', True),
            'copyright_headers_present': decision.get('target', {}).get('copyright_present', True),
            'build_passes_public_ci': decision.get('target', {}).get('ci_passed', True),
            'secrets_detected': decision.get('target', {}).get('secrets_detected', False),
            'severity': decision.get('target', {}).get('severity', 'MEDIUM')
        }
        
        try:
            # Use safe eval (in production, use simpleeval library)
            return eval(condition, {"__builtins__": {}}, context)
        except Exception as e:
            print(f"Error evaluating condition '{condition}': {e}")
            return False
```

---

## 6. AGENT IDENTITIES & PERMISSIONS MODEL

### 6.1 GitHub Apps (Public Integrations)

Create 6 bot accounts (each with limited scopes):

```yaml
# GitHub Apps Configuration

citadel-triage-bot:
  app_id: "123456"
  installation_id: "789012"
  scopes:
    - issues: write         # Label, comment, create
    - metadata: read        # Repository metadata
  permissions:
    cannot:
      - Merge PRs
      - Delete issues
      - Modify secrets
      - Admin operations
    can:
      - Assign labels
      - Comment on issues
      - Create issues
      - Update issue descriptions

citadel-planner-bot:
  app_id: "123457"
  installation_id: "789013"
  scopes:
    - issues: write         # Comment plans
    - pull_requests: read   # See PRs
  permissions:
    cannot:
      - Merge PRs
      - Deploy
      - Modify code
    can:
      - Create plans
      - Attach specs
      - Comment on issues

citadel-builder-bot:
  app_id: "123458"
  installation_id: "789014"
  scopes:
    - contents: read        # Clone repo (NOT write)
    - pull_requests: write  # Comment on PRs (NOT open, since export-bot does that)
    - checks: read          # See CI results
  permissions:
    cannot:
      - Push code to GitHub (works in GitLab)
      - Merge PRs
      - Access secrets
    can:
      - Comment on PRs
      - Update PR descriptions
      - Request reviews

citadel-qa-bot:
  app_id: "123459"
  installation_id: "789015"
  scopes:
    - pull_requests: write  # Comment test results, approve/request changes
    - checks: read          # Read CI status
  permissions:
    cannot:
      - Merge PRs
      - Deploy
      - Modify code
    can:
      - Comment results
      - Approve PRs
      - Request changes

citadel-docs-bot:
  app_id: "123460"
  installation_id: "789016"
  scopes:
    - pull_requests: write  # Comment on docs PRs
  permissions:
    cannot:
      - Merge code PRs
      - Modify secrets
    can:
      - Comment on PRs
      - Suggest doc updates

citadel-release-bot:
  app_id: "123461"
  installation_id: "789017"
  scopes:
    - pull_requests: write  # Comment "ready to release"
  permissions:
    cannot:
      - Create tags (GitHub Actions does this)
      - Create releases (GitHub Actions does this)
      - Merge PRs
    can:
      - Comment on PRs
      - Generate changelog text

citadel-export-bot:
  app_id: "123462"
  installation_id: "789018"
  scopes:
    - contents: write       # Push to export/* branches
    - pull_requests: write  # Open PRs
  permissions:
    cannot:
      - Push to main (branch protection prevents)
      - Merge PRs (requires checks + approval)
      - Delete branches
    can:
      - Push to export/* branches only
      - Open PRs from export/* to main
      - Update PR descriptions
```

**GitHub App Authentication** (Python):

```python
# src/integrations/github_client.py

import os
import time
import jwt
import httpx
from datetime import datetime, timedelta


class GitHubClient:
    """GitHub API client using GitHub App authentication."""
    
    def __init__(self, app_id: str = None, private_key: str = None, installation_id: str = None):
        self.app_id = app_id or os.getenv('GITHUB_APP_ID')
        self.private_key = private_key or os.getenv('GITHUB_PRIVATE_KEY')
        self.installation_id = installation_id or os.getenv('GITHUB_INSTALLATION_ID')
        self.token = None
        self.token_expires_at = None
    
    async def get_token(self) -> str:
        """Get or refresh installation access token."""
        if self.token and self.token_expires_at and datetime.utcnow() < self.token_expires_at:
            return self.token
        
        # Generate JWT
        now = int(time.time())
        payload = {
            'iat': now,
            'exp': now + (10 * 60),  # Expires in 10 minutes
            'iss': self.app_id
        }
        
        jwt_token = jwt.encode(payload, self.private_key, algorithm='RS256')
        
        # Exchange for installation access token
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f'https://api.github.com/app/installations/{self.installation_id}/access_tokens',
                headers={
                    'Authorization': f'Bearer {jwt_token}',
                    'Accept': 'application/vnd.github.v3+json'
                }
            )
            response.raise_for_status()
            data = response.json()
            
            self.token = data['token']
            self.token_expires_at = datetime.fromisoformat(data['expires_at'].replace('Z', '+00:00'))
            
            return self.token
    
    async def get_unassigned_issues(self) -> list:
        """Get issues without Linear tickets."""
        token = await self.get_token()
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                'https://api.github.com/repos/citadel-org/citadel-lite/issues',
                headers={
                    'Authorization': f'token {token}',
                    'Accept': 'application/vnd.github.v3+json'
                },
                params={
                    'state': 'open',
                    'labels': '!has-linear-ticket'
                }
            )
            response.raise_for_status()
            return response.json()
    
    async def get_open_prs(self) -> list:
        """Get open pull requests."""
        token = await self.get_token()
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                'https://api.github.com/repos/citadel-org/citadel-lite/pulls',
                headers={
                    'Authorization': f'token {token}',
                    'Accept': 'application/vnd.github.v3+json'
                },
                params={'state': 'open'}
            )
            response.raise_for_status()
            return response.json()
    
    async def add_labels(self, issue_number: int, labels: list):
        """Add labels to issue."""
        token = await self.get_token()
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f'https://api.github.com/repos/citadel-org/citadel-lite/issues/{issue_number}/labels',
                headers={
                    'Authorization': f'token {token}',
                    'Accept': 'application/vnd.github.v3+json'
                },
                json={'labels': labels}
            )
            response.raise_for_status()
    
    async def comment_on_issue(self, issue_number: int, body: str):
        """Comment on GitHub issue."""
        token = await self.get_token()
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f'https://api.github.com/repos/citadel-org/citadel-lite/issues/{issue_number}/comments',
                headers={
                    'Authorization': f'token {token}',
                    'Accept': 'application/vnd.github.v3+json'
                },
                json={'body': body}
            )
            response.raise_for_status()
    
    async def comment_on_pr(self, pr_number: int, body: str):
        """Comment on GitHub PR."""
        await self.comment_on_issue(pr_number, body)  # PRs are issues
    
    async def approve_pr(self, pr_number: int):
        """Approve a PR."""
        token = await self.get_token()
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f'https://api.github.com/repos/citadel-org/citadel-lite/pulls/{pr_number}/reviews',
                headers={
                    'Authorization': f'token {token}',
                    'Accept': 'application/vnd.github.v3+json'
                },
                json={
                    'event': 'APPROVE',
                    'body': '✅ All checks passed! Ready to merge.'
                }
            )
            response.raise_for_status()
    
    async def request_changes(self, pr_number: int):
        """Request changes on a PR."""
        token = await self.get_token()
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f'https://api.github.com/repos/citadel-org/citadel-lite/pulls/{pr_number}/reviews',
                headers={
                    'Authorization': f'token {token}',
                    'Accept': 'application/vnd.github.v3+json'
                },
                json={
                    'event': 'REQUEST_CHANGES',
                    'body': '❌ Some checks failed. Please fix before merging.'
                }
            )
            response.raise_for_status()
    
    async def merge_pr(self, pr_number: int):
        """Merge a PR (requires permissions)."""
        token = await self.get_token()
        
        async with httpx.AsyncClient() as client:
            response = await client.put(
                f'https://api.github.com/repos/citadel-org/citadel-lite/pulls/{pr_number}/merge',
                headers={
                    'Authorization': f'token {token}',
                    'Accept': 'application/vnd.github.v3+json'
                },
                json={'merge_method': 'squash'}
            )
            response.raise_for_status()
    
    async def get_ci_status(self, pr_number: int) -> dict:
        """Get CI status for PR."""
        token = await self.get_token()
        
        # Get PR details
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f'https://api.github.com/repos/citadel-org/citadel-lite/pulls/{pr_number}',
                headers={
                    'Authorization': f'token {token}',
                    'Accept': 'application/vnd.github.v3+json'
                }
            )
            response.raise_for_status()
            pr = response.json()
            
            # Get commit statuses
            response = await client.get(
                f'https://api.github.com/repos/citadel-org/citadel-lite/commits/{pr["head"]["sha"]}/status',
                headers={
                    'Authorization': f'token {token}',
                    'Accept': 'application/vnd.github.v3+json'
                }
            )
            response.raise_for_status()
            status = response.json()
            
            return {
                'all_passed': status['state'] == 'success',
                'failures': [s['context'] for s in status['statuses'] if s['state'] == 'failure']
            }
    
    async def create_issue(self, data: dict) -> dict:
        """Create a new GitHub issue."""
        token = await self.get_token()
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                'https://api.github.com/repos/citadel-org/citadel-lite/issues',
                headers={
                    'Authorization': f'token {token}',
                    'Accept': 'application/vnd.github.v3+json'
                },
                json=data
            )
            response.raise_for_status()
            return response.json()
    
    async def get_failed_ci_jobs(self) -> list:
        """Get failed CI jobs from recent workflow runs."""
        token = await self.get_token()
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                'https://api.github.com/repos/citadel-org/citadel-lite/actions/runs',
                headers={
                    'Authorization': f'token {token}',
                    'Accept': 'application/vnd.github.v3+json'
                },
                params={'status': 'failure', 'per_page': 10}
            )
            response.raise_for_status()
            runs = response.json()['workflow_runs']
            
            failures = []
            for run in runs:
                failures.append({
                    'run_id': run['id'],
                    'name': run['name'],
                    'url': run['html_url'],
                    'created_at': run['created_at']
                })
            
            return failures
```

---

## 7. INTEGRATION LAYER BLUEPRINT

### 7.1 GitLab (Private Authoritative)

**Repository Structure**:
```
citadel-nexus/
├── README.md                          # Org overview
├── .gitlab-ci.yml                     # CI/CD pipeline
├── policies/
│   ├── core_gates.yaml                # Policy rules
│   ├── policy_graph.yaml              # 481 routes (optional, advanced)
│   └── authority_matrix.yaml          # CAPS/permissions
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
│   ├── bridge_service.py              # Export orchestrator
│   ├── assembly_rules.yaml            # What to include/exclude
│   ├── license_check.py
│   ├── secret_scan.py
│   └── copyright_generator.py
├── infra/
│   ├── docker-compose.yml             # Local dev
│   ├── kubernetes/
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   └── ingress.yaml
│   └── terraform/
└── src/
    ├── citadel_nexus/                 # PROPRIETARY (stays private)
    ├── citadel_lite/                  # PUBLIC (exported)
    └── integrations/
```

**CI/CD Pipeline** (.gitlab-ci.yml):

```yaml
stages:
  - test
  - build
  - export
  - deploy

variables:
  DOCKER_REGISTRY: "registry.gitlab.com/citadel-org"

# ==============================================================================
# STAGE: TEST
# ==============================================================================
test:
  stage: test
  image: python:3.10
  before_script:
    - pip install -r requirements.txt
    - pip install -r requirements-dev.txt
  script:
    - pytest src/tests/ -v --cov=src --cov-report=html
    - black --check src/
    - mypy src/
  artifacts:
    reports:
      coverage_report:
        coverage_format: cobertura
        path: coverage.xml
  only:
    - merge_requests
    - main

# ==============================================================================
# STAGE: BUILD
# ==============================================================================
build:nexus:
  stage: build
  image: docker:20.10
  services:
    - docker:20.10-dind
  before_script:
    - docker login -u $CI_REGISTRY_USER -p $CI_REGISTRY_PASSWORD $CI_REGISTRY
  script:
    - docker build -t $DOCKER_REGISTRY/citadel-nexus:$CI_COMMIT_SHA .
    - docker push $DOCKER_REGISTRY/citadel-nexus:$CI_COMMIT_SHA
    - |
      if [ "$CI_COMMIT_BRANCH" = "main" ]; then
        docker tag $DOCKER_REGISTRY/citadel-nexus:$CI_COMMIT_SHA $DOCKER_REGISTRY/citadel-nexus:latest
        docker push $DOCKER_REGISTRY/citadel-nexus:latest
      fi
  only:
    - main

# ==============================================================================
# STAGE: EXPORT (GitLab → GitHub)
# ==============================================================================
export:lite:
  stage: export
  image: python:3.10
  before_script:
    - pip install -r export/requirements.txt
    - apt-get update && apt-get install -y git
  script:
    - python export/bridge_service.py --version $(cat VERSION)
  only:
    - main
  when: on_success
  # Runs only when main branch changes pass all tests

# Manual trigger for export (via Slack /citadel export)
export:manual:
  stage: export
  image: python:3.10
  before_script:
    - pip install -r export/requirements.txt
  script:
    - python export/bridge_service.py --version $(cat VERSION)
  when: manual
  allow_failure: false

# ==============================================================================
# STAGE: DEPLOY
# ==============================================================================
deploy:staging:
  stage: deploy
  image: bitnami/kubectl:latest
  environment:
    name: staging
    url: https://staging.citadel.local
  script:
    - kubectl config use-context citadel-staging
    - kubectl set image deployment/citadel-nexus citadel-nexus=$DOCKER_REGISTRY/citadel-nexus:$CI_COMMIT_SHA -n citadel
    - kubectl rollout status deployment/citadel-nexus -n citadel
  only:
    - main

deploy:production:
  stage: deploy
  image: bitnami/kubectl:latest
  environment:
    name: production
    url: https://citadel.local
  script:
    - kubectl config use-context citadel-production
    - kubectl set image deployment/citadel-nexus citadel-nexus=$DOCKER_REGISTRY/citadel-nexus:$CI_COMMIT_SHA -n citadel
    - kubectl rollout status deployment/citadel-nexus -n citadel
  when: manual  # Require manual approval for production
  only:
    - main
```

---

### 7.2 GitHub (Public Artifact)

**Repository Structure**:
```
citadel-lite/
├── README.md                          # Public docs
├── LICENSE                            # MIT or Apache
├── CONTRIBUTING.md                    # Dev guidelines
├── .github/
│   ├── workflows/
│   │   ├── test.yml                   # Run tests on PR
│   │   ├── security-scan.yml          # SAST, dep check
│   │   ├── release.yml                # Auto-publish releases
│   │   └── auto-merge.yml             # Auto-merge export PRs
│   ├── ISSUE_TEMPLATE/
│   │   ├── bug_report.md
│   │   ├── feature_request.md
│   │   └── question.md
│   ├── PULL_REQUEST_TEMPLATE.md
│   └── CODEOWNERS
├── src/
│   └── citadel_lite/                  # PUBLIC CODE ONLY
│       ├── cli/
│       ├── api/
│       └── integrations/
├── docs/
│   ├── getting-started.md
│   ├── architecture.md
│   └── api-reference.md
├── examples/
│   ├── basic_usage.py
│   └── docker-compose.yml
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/
├── pyproject.toml
├── requirements.txt
└── Makefile
```

**GitHub Actions Workflows**:

```yaml
# .github/workflows/test.yml

name: Tests

on:
  pull_request:
    branches: [main, develop]
  push:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ['3.9', '3.10', '3.11']
    
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v4
        with:
          python-version: ${{ matrix.python-version }}
      
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements-dev.txt
      
      - name: Run tests
        run: |
          pytest tests/ -v --cov=src/citadel_lite --cov-report=xml
      
      - name: Upload coverage
        uses: codecov/codecov-action@v3
        with:
          files: ./coverage.xml
  
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      
      - name: Install dependencies
        run: pip install black mypy
      
      - name: Lint
        run: |
          black --check src/
          mypy src/
  
  security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Run Trivy vulnerability scanner
        uses: aquasecurity/trivy-action@master
        with:
          scan-type: 'fs'
          scan-ref: '.'
          format: 'sarif'
          output: 'trivy-results.sarif'
      
      - name: Upload Trivy results to GitHub Security
        uses: github/codeql-action/upload-sarif@v2
        with:
          sarif_file: 'trivy-results.sarif'
```

```yaml
# .github/workflows/release.yml

name: Release

on:
  push:
    branches: [main]

permissions:
  contents: write
  releases: write

jobs:
  check-release:
    runs-on: ubuntu-latest
    outputs:
      should_release: ${{ steps.check.outputs.should_release }}
      version: ${{ steps.check.outputs.version }}
    steps:
      - uses: actions/checkout@v3
        with:
          fetch-depth: 0
      
      - name: Check if release needed
        id: check
        run: |
          COMMIT_MSG=$(git log -1 --pretty=%B)
          
          if echo "$COMMIT_MSG" | grep -q "\[release\]"; then
            echo "should_release=true" >> $GITHUB_OUTPUT
            VERSION=$(cat VERSION)
            echo "version=$VERSION" >> $GITHUB_OUTPUT
          else
            echo "should_release=false" >> $GITHUB_OUTPUT
          fi
  
  create-release:
    needs: check-release
    if: needs.check-release.outputs.should_release == 'true'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Create git tag
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          
          VERSION="${{ needs.check-release.outputs.version }}"
          git tag -a "v$VERSION" -m "Release v$VERSION"
          git push origin "v$VERSION"
      
      - name: Build artifacts
        run: |
          python -m pip install build
          python -m build
          tar -czf citadel-lite-${{ needs.check-release.outputs.version }}.tar.gz dist/
      
      - name: Create GitHub Release
        uses: softprops/action-gh-release@v1
        with:
          tag_name: v${{ needs.check-release.outputs.version }}
          name: Release v${{ needs.check-release.outputs.version }}
          body: "Release notes will be auto-generated"
          draft: false
          prerelease: false
          files: |
            citadel-lite-${{ needs.check-release.outputs.version }}.tar.gz
            dist/*.whl
            dist/*.tar.gz
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

```yaml
# .github/workflows/auto-merge.yml

name: Auto-Merge Export PRs

on:
  pull_request:
    types: [opened, synchronize, labeled]

jobs:
  auto-merge:
    if: github.actor == 'citadel-export-bot[bot]' && startsWith(github.head_ref, 'export/')
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Wait for checks to complete
        uses: lewagon/wait-on-check-action@v1.3.1
        with:
          ref: ${{ github.event.pull_request.head.sha }}
          check-name: 'Tests'
          repo-token: ${{ secrets.GITHUB_TOKEN }}
          wait-interval: 10
      
      - name: Auto-merge if checks pass
        uses: pascalgn/automerge-action@v0.15.6
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          MERGE_LABELS: ""
          MERGE_METHOD: "squash"
          MERGE_COMMIT_MESSAGE: "pull-request-title-and-description"
```

---

## (Character limit reached - continuing in next message with remaining sections 8-19...)

This is Part 1 of the complete blueprint. The file is being generated and will include all sections. Let me create the complete file now.