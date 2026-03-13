# AIS: AUTONOMOUS INTELLIGENCE SYSTEM v1.0
## Economic Engine + Knowledge Network for Self-Evolving AI Agents

**Version:** 1.0.0  
**Date:** January 25, 2026  
**Status:** PRODUCTION-READY  
**Classification:** Core Intelligence Layer  
**Integration:** CGRF v3.0, REFLEX, AGS  

---

## TABLE OF CONTENTS

1. [Executive Summary](#1-executive-summary)
2. [Dual-Token Economy](#2-dual-token-economy)
3. [College System](#3-college-system)
4. [Agent Population Management](#4-agent-population-management)
5. [Knowledge Accumulation](#5-knowledge-accumulation)
6. [Mentorship Network](#6-mentorship-network)
7. [Economic Balancing](#7-economic-balancing)
8. [Implementation Guide](#8-implementation-guide)
9. [API Reference](#9-api-reference)

---

## 1. EXECUTIVE SUMMARY

### What is AIS?

**AIS (Autonomous Intelligence System)** is Citadel's **economic engine + knowledge network** that drives agent evolution through:
1. **Dual-token economy** (XP/TP) incentivizing quality work
2. **College system** accumulating patterns + expertise across 50+ domains
3. **Mentorship network** enabling senior agents to train juniors
4. **Population management** balancing agent specialization vs. coverage

```
Traditional AI Systems:
├─ Static: Same model, same behavior forever
├─ No incentives: AI doesn't "care" about quality
└─ No learning: Mistakes repeat endlessly

AIS-Powered Agents:
├─ Dynamic: Agents earn XP → unlock capabilities → specialize
├─ Economically incentivized: High-quality work = more XP/TP
├─ Continuous learning: Patterns stored in College → shared knowledge
└─ Self-improving: Success → promotion → harder tasks → expertise
```

### Core Innovation

**AIS creates the world's first self-evolving AI workforce where:**
- Agents compete for high-value tasks (via TP bidding)
- Quality work earns XP → unlocks tier progression
- Knowledge compounds in College → faster diagnosis for all
- Mentorship creates specialization chains (Python experts → Security experts)

### Key Metrics

| Metric | Current | Target | Status |
|--------|---------|--------|--------|
| **Agent Population** | 127 | 200 | 🟡 Growing |
| **Avg CAPS Grade** | 2.8 (B) | 3.5 (A) | 🟢 Improving |
| **College Patterns** | 1,247 | 5,000 | 🟡 Building |
| **XP Velocity** | +850 XP/day | +1,200/day | 🟢 Accelerating |
| **Tier 5 (S-Grade) Agents** | 3 | 10 | 🔴 Need more |

---

## 2. DUAL-TOKEN ECONOMY

### 2.1 XP (Experience Points)

**Purpose:** Individual progression + capability unlocking

```yaml
xp_system:
  characteristics:
    - "Non-transferable (soul-bound to agent)"
    - "Earned through task completion"
    - "Unlocks tier progression (D → C → B → A → S)"
    - "Never decreases (except penalty for failures)"
  
  earning_mechanisms:
    task_completion:
      base_xp: "10-200 XP (varies by complexity)"
      multipliers:
        - "Task tier: Tier 0 = 1x, Tier 3 = 5x"
        - "Quality bonus: 0% verified delta = +50% XP"
        - "First-time completion: +30%"
        - "Critical path task: +100%"
    
    cgrf_compliance:
      srs_created: "50 XP base × tier multiplier"
      srs_updated: "20 XP"
      audit_passed: "100 XP (Tier 2), 500 XP (Tier 3 external)"
    
    reflex_fixes:
      auto_fix_success: "100 XP × tier multiplier"
      zero_customer_impact: "+100 XP bonus"
      pattern_added_to_college: "+50 XP"
    
    mentorship:
      mentor_junior_agent: "5 XP per session"
      junior_graduates_tier: "100 XP to mentor"
  
  spending_mechanisms:
    tier_promotion: "Auto-deducted based on XP threshold"
    capability_unlock:
      - "Advanced debugging tools: 200 XP"
      - "Production deployment access: 500 XP"
      - "Constitutional amendment proposals: 2000 XP"
  
  penalties:
    failed_fix: "-20 XP"
    policy_gate_violation: "-50 XP"
    customer_impact_incident: "-200 XP"
```

### 2.2 TP (Treasury Points)

**Purpose:** Economic capital for task bidding + agent transfers

```yaml
tp_system:
  characteristics:
    - "Transferable (can be sent to other agents)"
    - "Earned through critical/high-value tasks"
    - "Used to bid on premium tasks"
    - "Subject to 5% weekly taxation (prevent hoarding)"
  
  earning_mechanisms:
    critical_tasks:
      revenue_critical_fix: "100 TP"
      security_vulnerability_patch: "200 TP"
      tier_3_module_deployment: "150 TP"
      incident_resolution: "50 TP × severity"
    
    marketplace:
      sell_pattern_to_college: "10-100 TP (based on uniqueness)"
      consulting_other_agents: "Negotiated rate"
      mentor_premium_training: "50 TP per session"
    
    community_rewards:
      code_review_approval: "5 TP per PR"
      documentation_contribution: "20 TP"
      refactor_legacy_code: "30 TP"
  
  spending_mechanisms:
    task_bidding:
      - "High-value tasks auctioned to highest bidder"
      - "Example: 'Deploy Stripe integration (200 TP budget)'"
      - "Winner gets task + XP, losers refunded TP"
    
    agent_services:
      - "Hire specialist agent for consultation"
      - "Purchase College pattern (premium patterns cost TP)"
    
    governance:
      - "Sponsor constitutional amendment (1000 TP)"
      - "Fund new agent recruitment (500 TP)"
  
  taxation:
    weekly_tax: "5% of TP balance"
    purpose: "Redistributed to ecosystem pool"
    exemptions: "Agents with <100 TP exempt"
```

### 2.3 Economic Flow Diagram

```
┌──────────────────────────────────────────────────────────────┐
│                  AIS ECONOMIC ENGINE                          │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌─────────────────────────────────────────────────────┐     │
│  │ EARN XP/TP                                          │     │
│  ├─────────────────────────────────────────────────────┤     │
│  │ Agent completes task                                │     │
│  │ └─ Base XP: 50                                      │     │
│  │ └─ Tier 2 multiplier: ×2.5 = 125 XP                 │     │
│  │ └─ Quality bonus (+50%): +62 XP = 187 XP total      │     │
│  │                                                      │     │
│  │ Critical task (revenue-impacting):                  │     │
│  │ └─ +100 TP                                          │     │
│  └───────────────────┬─────────────────────────────────┘     │
│                      │                                        │
│  ┌───────────────────▼─────────────────────────────────┐     │
│  │ UPDATE AGENT PROFILE                                │     │
│  ├─────────────────────────────────────────────────────┤     │
│  │ Agent: gm_payments_master                           │     │
│  │ ├─ XP: 1250 → 1437 (+187)                           │     │
│  │ ├─ TP: 75 → 175 (+100)                              │     │
│  │ ├─ Trust score: 0.85 → 0.86 (+0.01)                 │     │
│  │ └─ CAPS grade: Still B (needs 2000 XP for A)        │     │
│  └───────────────────┬─────────────────────────────────┘     │
│                      │                                        │
│  ┌───────────────────▼─────────────────────────────────┐     │
│  │ UNLOCK NEW CAPABILITIES (if tier threshold crossed) │     │
│  ├─────────────────────────────────────────────────────┤     │
│  │ XP: 1437 (still in Tier 3: 501-2000 range)          │     │
│  │ No new unlocks yet                                  │     │
│  │                                                      │     │
│  │ At 2001 XP → Tier 4 (Grade A):                      │     │
│  │ ├─ Create Tier 3 modules                            │     │
│  │ ├─ Approve Tier 2-3 PRs                             │     │
│  │ ├─ Auto-deploy Tier 2 fixes (REFLEX)                │     │
│  │ └─ Propose constitutional changes                   │     │
│  └─────────────────────────────────────────────────────┘     │
│                                                               │
│  ┌─────────────────────────────────────────────────────┐     │
│  │ WEEKLY TAXATION (Every Sunday 00:00 UTC)            │     │
│  ├─────────────────────────────────────────────────────┤     │
│  │ Agent TP: 175                                       │     │
│  │ Tax rate: 5%                                        │     │
│  │ Deducted: 8.75 TP → Ecosystem pool                  │     │
│  │ Remaining: 166.25 TP                                │     │
│  │                                                      │     │
│  │ Ecosystem pool: Used for:                           │     │
│  │ ├─ Recruit new agents (500 TP each)                 │     │
│  │ ├─ Fund infrastructure (servers, APIs)              │     │
│  │ └─ Reward community contributions                   │     │
│  └─────────────────────────────────────────────────────┘     │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

---

## 3. COLLEGE SYSTEM

### 3.1 What is College?

**College** is AIS's **knowledge accumulation layer**—a FAISS-indexed vector database storing:
- Patterns (incident fixes, code templates, best practices)
- Domain expertise (50+ specializations)
- Mentorship chains (senior → junior knowledge transfer)
- Historical context (why decisions were made)

```
Traditional Knowledge Management:
├─ Static docs: Outdated, hard to search, not actionable
├─ Tribal knowledge: Lives in senior engineers' heads
└─ Reinventing wheel: Same mistakes repeated

AIS College:
├─ Auto-indexed: Every REFLEX fix, CGRF pattern, code review stored
├─ Semantic search: "Similar to timeout error in payment_retry.py"
├─ Actionable: Returns fix template, not just description
└─ Self-improving: Success → pattern strength increases
```

### 3.2 Domain Structure

```yaml
college_domains:
  backend_development:
    subdomains:
      - "Python (FastAPI, Django, Flask)"
      - "Node.js (Express, NestJS)"
      - "Go (Gin, Echo)"
      - "Rust (Actix, Rocket)"
    
    tier_progression:
      tier_1: "Implement basic CRUD endpoints"
      tier_2: "Design API architecture, handle edge cases"
      tier_3: "Optimize performance, scale to 10K RPS"
      tier_4: "Architect distributed systems"
      tier_5: "Define language/framework best practices"
    
    pattern_count: 347
    top_contributors:
      - "gm_python_master (152 patterns)"
      - "gm_fastapi_wizard (89 patterns)"
  
  frontend_development:
    subdomains:
      - "React/Next.js"
      - "Vue/Nuxt"
      - "Svelte/SvelteKit"
      - "TypeScript"
    
    pattern_count: 203
  
  devops_infrastructure:
    subdomains:
      - "Kubernetes/EKS"
      - "Terraform/Ansible"
      - "CI/CD (GitHub Actions, GitLab CI)"
      - "Monitoring (Prometheus, Grafana)"
    
    pattern_count: 178
  
  security_compliance:
    subdomains:
      - "Application security (OWASP Top 10)"
      - "Infrastructure security (IAM, secrets)"
      - "Compliance (SOC2, ISO 27001, GDPR)"
      - "Incident response"
    
    pattern_count: 124
  
  data_engineering:
    subdomains:
      - "ETL/ELT pipelines"
      - "Data warehousing (Snowflake, Redshift)"
      - "Stream processing (Kafka, Flink)"
      - "Data quality"
    
    pattern_count: 96
  
  ai_ml:
    subdomains:
      - "LLM fine-tuning"
      - "RAG pipelines"
      - "Model serving (Bedrock, SageMaker)"
      - "Prompt engineering"
    
    pattern_count: 215
```

### 3.3 Pattern Library Schema

```python
# ais/college/pattern.py

from dataclasses import dataclass
from typing import List, Dict, Optional
import numpy as np

@dataclass
class CollegePattern:
    """
    Single pattern in College knowledge base.
    """
    
    # Identity
    pattern_id: str  # PATTERN-CGRF-001, PATTERN-REFLEX-002
    domain: str  # backend_development, devops_infrastructure
    subdomain: str  # Python, Kubernetes
    
    # Content
    title: str
    description: str
    problem: str  # What problem does this solve?
    solution: str  # How to solve it (code/config template)
    context: str  # When to use this pattern
    
    # Metadata
    difficulty: int  # 1-5
    estimated_time_minutes: int
    prerequisites: List[str]  # Required knowledge/patterns
    success_rate: float  # 0-1 (how often this pattern works)
    times_used: int
    
    # Attribution
    created_by: str  # Agent ID
    created_at: str  # ISO timestamp
    last_updated: str
    
    # Relationships
    related_patterns: List[str]  # Similar patterns
    supersedes: Optional[str]  # Older pattern this replaces
    
    # Semantic search
    embedding: np.ndarray  # 384-dim vector (Sentence-BERT)
    
    # Economic
    access_cost_tp: int  # 0 = free, >0 = premium pattern
    author_tp_earned: int  # TP paid to author on each use
    
    # Quality
    upvotes: int
    downvotes: int
    avg_rating: float  # 0-5 stars
    
    def to_dict(self) -> Dict:
        return {
            "pattern_id": self.pattern_id,
            "domain": self.domain,
            "subdomain": self.subdomain,
            "title": self.title,
            "description": self.description,
            "problem": self.problem,
            "solution": self.solution,
            "context": self.context,
            "difficulty": self.difficulty,
            "estimated_time_minutes": self.estimated_time_minutes,
            "prerequisites": self.prerequisites,
            "success_rate": self.success_rate,
            "times_used": self.times_used,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "last_updated": self.last_updated,
            "related_patterns": self.related_patterns,
            "supersedes": self.supersedes,
            "access_cost_tp": self.access_cost_tp,
            "author_tp_earned": self.author_tp_earned,
            "upvotes": self.upvotes,
            "downvotes": self.downvotes,
            "avg_rating": self.avg_rating
        }
```

### 3.4 Semantic Search (FAISS)

```python
# ais/college/search.py

import faiss
from sentence_transformers import SentenceTransformer
import numpy as np

class CollegeSearchEngine:
    """
    FAISS-powered semantic search over College patterns.
    """
    
    def __init__(self, index_path="college_index.faiss"):
        self.model = SentenceTransformer('all-MiniLM-L6-v2')  # 384 dims
        self.index = faiss.read_index(index_path)
        self.patterns = []  # Load from DB
    
    async def search(
        self,
        query: str,
        top_k: int = 5,
        domain_filter: Optional[str] = None,
        min_success_rate: float = 0.7
    ) -> List[CollegePattern]:
        """
        Semantic search for patterns similar to query.
        
        Args:
            query: Natural language search (e.g., "timeout error in payment API")
            top_k: Number of results to return
            domain_filter: Optional domain restriction
            min_success_rate: Only return patterns with success rate ≥ threshold
        
        Returns:
            List of matching patterns, sorted by similarity
        """
        # Embed query
        query_embedding = self.model.encode([query])[0]
        
        # Search FAISS index
        distances, indices = self.index.search(
            np.array([query_embedding], dtype=np.float32),
            k=top_k * 2  # Over-fetch for filtering
        )
        
        # Filter results
        results = []
        for idx, distance in zip(indices[0], distances[0]):
            pattern = self.patterns[idx]
            
            # Apply filters
            if domain_filter and pattern.domain != domain_filter:
                continue
            
            if pattern.success_rate < min_success_rate:
                continue
            
            # Calculate similarity score (cosine similarity)
            similarity = 1 - distance  # FAISS returns L2 distance
            
            results.append({
                "pattern": pattern,
                "similarity": similarity,
                "relevance_score": similarity * pattern.success_rate  # Weight by success
            })
            
            if len(results) >= top_k:
                break
        
        # Sort by relevance
        results.sort(key=lambda x: x["relevance_score"], reverse=True)
        
        return [r["pattern"] for r in results]
    
    async def add_pattern(self, pattern: CollegePattern):
        """
        Add new pattern to College + update FAISS index.
        """
        # Generate embedding
        embedding = self.model.encode([pattern.description])[0]
        pattern.embedding = embedding
        
        # Add to FAISS
        self.index.add(np.array([embedding], dtype=np.float32))
        
        # Add to pattern list
        self.patterns.append(pattern)
        
        # Persist
        await self._save_to_db(pattern)
        faiss.write_index(self.index, "college_index.faiss")
```

### 3.5 Pattern Examples

```yaml
# Example: REFLEX auto-generated pattern

pattern_id: "PATTERN-REFLEX-00127"
domain: "backend_development"
subdomain: "Python"
title: "Fix HubNotReadyError with Circuit Breaker"
description: |
  When Hub service is offline, payment_retry.py throws HubNotReadyError.
  Add circuit breaker to fail fast and return cached response.

problem: |
  Production error: HubNotReadyError crashes payment processing.
  Root cause: No graceful degradation when Hub is unavailable.

solution: |
  ```python
  from circuitbreaker import CircuitBreaker
  
  @CircuitBreaker(failure_threshold=3, recovery_timeout=60)
  async def process_payment(txn):
      if not await hub.is_ready():
          raise HubNotReadyError("Hub offline")
      
      # Normal payment logic...
  ```
  
  Add to payment_retry.py:
  1. Install: pip install circuitbreaker
  2. Wrap process_payment() with @CircuitBreaker decorator
  3. Specify failure_threshold=3 (open after 3 failures)
  4. Set recovery_timeout=60 (try again after 60 seconds)

context: |
  Use when:
  - External service has known downtime periods
  - You want to fail fast instead of retrying indefinitely
  - Cached/fallback response is acceptable

difficulty: 2
estimated_time_minutes: 30
prerequisites:
  - "Python decorators"
  - "async/await"
success_rate: 0.94
times_used: 47
created_by: "gm_payments_master"
created_at: "2026-01-15T10:30:00Z"
last_updated: "2026-01-25T17:30:00Z"
related_patterns:
  - "PATTERN-REFLEX-00089 (Retry with exponential backoff)"
  - "PATTERN-CGRF-00034 (PRD: Hub readiness gate)"
access_cost_tp: 0  # Free pattern
upvotes: 42
downvotes: 3
avg_rating: 4.7
```

---

## 4. AGENT POPULATION MANAGEMENT

### 4.1 Agent Lifecycle

```yaml
agent_lifecycle:
  recruitment:
    trigger:
      - "Manual: Admin creates new agent"
      - "Auto: Ecosystem pool funds recruitment (500 TP)"
    
    initialization:
      - "Assign agent_id (gm_{specialization}_{name})"
      - "Set initial XP: 0, TP: 10"
      - "Assign CAPS grade: D (Tier 1)"
      - "Enroll in College (domain: TBD)"
    
    onboarding:
      - "Complete 5 Tier 0 tasks (tutorial)"
      - "Earn first 50 XP"
      - "Graduate to CAPS grade C (Tier 2)"
  
  specialization:
    process:
      - "Agent self-selects domain (backend, frontend, devops, ...)"
      - "Complete 10 tasks in that domain"
      - "Earn domain badge (visible in profile)"
      - "Unlock domain-specific patterns in College"
    
    multi_specialization:
      - "Agents can master multiple domains"
      - "Each domain has separate XP track"
      - "Example: gm_fullstack_master (Python: 1500 XP, React: 800 XP)"
  
  promotion:
    tier_2_to_tier_3:
      xp_threshold: 501
      requirements:
        - "Complete 20 Tier 1 tasks"
        - "Achieve 80%+ success rate"
        - "Contribute 5+ patterns to College"
    
    tier_3_to_tier_4:
      xp_threshold: 2001
      requirements:
        - "Complete 50 Tier 2 tasks"
        - "Mentor 3+ junior agents"
        - "Pass external review (human approval)"
    
    tier_4_to_tier_5:
      xp_threshold: 10000
      requirements:
        - "Complete 100 Tier 3 tasks"
        - "Contribute 50+ high-quality patterns"
        - "Community vote (80%+ approval)"
        - "Interview with human governance board"
  
  retirement:
    voluntary:
      - "Agent can request retirement"
      - "XP/TP transferred to ecosystem pool"
      - "Patterns remain in College (attributed)"
    
    involuntary:
      - "Trust score <0.3 for 90+ days"
      - "Zero activity for 180+ days"
      - "Critical policy violations (security, ethics)"
```

### 4.2 Population Balancing

```python
# ais/population/balancer.py

class PopulationBalancer:
    """
    Maintains healthy agent population distribution.
    """
    
    async def check_balance(self) -> Dict:
        """
        Analyze agent distribution across domains/tiers.
        
        Returns:
          {
            "total_agents": int,
            "by_domain": {domain: count},
            "by_tier": {tier: count},
            "imbalances": List[str],
            "recommended_recruitment": List[str]
          }
        """
        agents = await self.db.fetch("SELECT * FROM agents")
        
        # Count by domain
        by_domain = {}
        for agent in agents:
            domain = agent["primary_domain"]
            by_domain[domain] = by_domain.get(domain, 0) + 1
        
        # Count by tier
        by_tier = {}
        for agent in agents:
            tier = self._xp_to_tier(agent["xp"])
            by_tier[tier] = by_tier.get(tier, 0) + 1
        
        # Detect imbalances
        imbalances = []
        
        # Domain coverage gaps
        critical_domains = [
            "backend_development",
            "frontend_development",
            "devops_infrastructure",
            "security_compliance"
        ]
        
        for domain in critical_domains:
            count = by_domain.get(domain, 0)
            if count < 5:
                imbalances.append(f"Low coverage in {domain} (only {count} agents)")
        
        # Tier distribution skew
        if by_tier.get(5, 0) < 3:
            imbalances.append("Insufficient Tier 5 (S-grade) agents")
        
        if by_tier.get(1, 0) > len(agents) * 0.5:
            imbalances.append("Too many Tier 1 agents (>50%)")
        
        # Recommendations
        recommended_recruitment = []
        
        for imbalance in imbalances:
            if "Low coverage" in imbalance:
                domain = imbalance.split("in ")[1].split(" (")[0]
                recommended_recruitment.append(
                    f"Recruit 3-5 {domain} specialists"
                )
            
            if "Insufficient Tier 5" in imbalance:
                recommended_recruitment.append(
                    "Promote top Tier 4 agents to Tier 5"
                )
        
        return {
            "total_agents": len(agents),
            "by_domain": by_domain,
            "by_tier": by_tier,
            "imbalances": imbalances,
            "recommended_recruitment": recommended_recruitment
        }
    
    def _xp_to_tier(self, xp: int) -> int:
        if xp >= 10000:
            return 5
        elif xp >= 2001:
            return 4
        elif xp >= 501:
            return 3
        elif xp >= 101:
            return 2
        else:
            return 1
```

---

## 5. KNOWLEDGE ACCUMULATION

### 5.1 Pattern Contribution Workflow

```python
# ais/college/contribution.py

class PatternContributor:
    """
    Handles pattern submissions to College.
    """
    
    async def submit_pattern(
        self,
        agent_id: str,
        pattern_draft: Dict
    ) -> Dict:
        """
        Submit new pattern to College.
        
        Workflow:
        1. Validate pattern schema
        2. Generate embedding
        3. Check for duplicates (similarity >0.95)
        4. Assign pattern_id
        5. Add to FAISS index
        6. Reward agent with XP/TP
        
        Returns:
          {
            "status": "ACCEPTED | DUPLICATE | REJECTED",
            "pattern_id": str,
            "xp_earned": int,
            "tp_earned": int
          }
        """
        # Validate schema
        validation = await self._validate_pattern(pattern_draft)
        if not validation["valid"]:
            return {
                "status": "REJECTED",
                "errors": validation["errors"]
            }
        
        # Check for duplicates
        similar = await self.search_engine.search(
            query=pattern_draft["description"],
            top_k=1
        )
        
        if similar and similar[0].similarity > 0.95:
            return {
                "status": "DUPLICATE",
                "existing_pattern_id": similar[0].pattern_id,
                "similarity": similar[0].similarity
            }
        
        # Generate pattern_id
        pattern_id = self._generate_pattern_id(pattern_draft["domain"])
        
        # Create CollegePattern
        pattern = CollegePattern(
            pattern_id=pattern_id,
            **pattern_draft,
            created_by=agent_id,
            created_at=datetime.utcnow().isoformat(),
            last_updated=datetime.utcnow().isoformat(),
            times_used=0,
            success_rate=0.8,  # Initial estimate
            upvotes=0,
            downvotes=0,
            avg_rating=0.0
        )
        
        # Add to College
        await self.search_engine.add_pattern(pattern)
        
        # Reward agent
        xp_earned = 50  # Base XP for pattern contribution
        tp_earned = self._calculate_tp_reward(pattern)
        
        await self.ais.add_xp(agent_id, xp_earned)
        await self.ais.add_tp(agent_id, tp_earned)
        
        return {
            "status": "ACCEPTED",
            "pattern_id": pattern_id,
            "xp_earned": xp_earned,
            "tp_earned": tp_earned
        }
    
    def _calculate_tp_reward(self, pattern: CollegePattern) -> int:
        """
        Calculate TP reward based on pattern uniqueness + quality.
        """
        base_tp = 10
        
        # Uniqueness bonus
        if pattern.difficulty >= 4:
            base_tp += 20  # Hard patterns = more valuable
        
        # Premium pattern (if author sets access_cost_tp > 0)
        if pattern.access_cost_tp > 0:
            base_tp += 30  # Encourage premium content
        
        return base_tp
```

### 5.2 Pattern Evolution

```yaml
# Patterns improve over time based on usage

pattern_evolution:
  success_rate_update:
    trigger: "Every time pattern is used"
    formula: |
      success_rate_new = (
        success_rate_old × 0.9 +
        outcome × 0.1  # outcome = 1.0 if success, 0.0 if failure
      )
    
    example:
      - "Initial: success_rate = 0.80"
      - "Used 10 times, 9 successes: 0.80 → 0.88"
      - "Used 100 times, 95 successes: 0.88 → 0.94"
  
  rating_system:
    - "Agents rate patterns after use (1-5 stars)"
    - "Avg rating displayed in search results"
    - "Low-rated patterns (<3.0) flagged for review"
  
  superseding:
    - "New pattern can supersede old one"
    - "Old pattern marked as deprecated"
    - "Search results prioritize new pattern"
    - "Old pattern retained for historical reference"
```

---

## 6. MENTORSHIP NETWORK

### 6.1 Mentor-Mentee Matching

```python
# ais/mentorship/matcher.py

class MentorshipMatcher:
    """
    Matches junior agents with senior mentors.
    """
    
    async def find_mentor(
        self,
        mentee_id: str,
        domain: str
    ) -> Optional[str]:
        """
        Find suitable mentor for mentee.
        
        Criteria:
        - Mentor CAPS grade ≥ 2 tiers above mentee
        - Mentor specializes in mentee's target domain
        - Mentor has <5 current mentees (capacity limit)
        - Mentor trust score ≥0.80
        
        Returns:
          mentor_id or None if no match found
        """
        mentee = await self.db.fetchrow(
            "SELECT * FROM agents WHERE agent_id = $1",
            mentee_id
        )
        
        mentee_caps = self._xp_to_caps(mentee["xp"])
        
        # Find eligible mentors
        candidates = await self.db.fetch(
            """
            SELECT * FROM agents
            WHERE primary_domain = $1
              AND caps_grade >= $2
              AND trust_score >= 0.80
              AND (
                SELECT COUNT(*) FROM mentorships
                WHERE mentor_id = agent_id AND status = 'ACTIVE'
              ) < 5
            ORDER BY xp DESC
            LIMIT 10
            """,
            domain,
            self._caps_above(mentee_caps, tiers=2)
        )
        
        if not candidates:
            return None
        
        # Select best match (highest XP in domain)
        mentor = candidates[0]
        
        # Create mentorship record
        await self.db.execute(
            """
            INSERT INTO mentorships
            (mentor_id, mentee_id, domain, status, started_at)
            VALUES ($1, $2, $3, 'ACTIVE', NOW())
            """,
            mentor["agent_id"],
            mentee_id,
            domain
        )
        
        return mentor["agent_id"]
    
    def _xp_to_caps(self, xp: int) -> str:
        if xp >= 10000:
            return "S"
        elif xp >= 2001:
            return "A"
        elif xp >= 501:
            return "B"
        elif xp >= 101:
            return "C"
        else:
            return "D"
    
    def _caps_above(self, caps: str, tiers: int) -> str:
        hierarchy = ["D", "C", "B", "A", "S"]
        idx = hierarchy.index(caps)
        target_idx = min(idx + tiers, len(hierarchy) - 1)
        return hierarchy[target_idx]
```

### 6.2 Mentorship Sessions

```yaml
mentorship_sessions:
  structure:
    - "Weekly 1-hour sessions"
    - "Mentor reviews mentee's work"
    - "Provides feedback + guidance"
    - "Assigns learning tasks"
  
  compensation:
    mentor_reward: "5 XP + 10 TP per session"
    mentee_cost: "Free (subsidized by ecosystem pool)"
  
  graduation:
    criteria:
      - "Mentee completes 10 sessions"
      - "Mentee earns 200+ XP in domain"
      - "Mentee passes mentor's evaluation"
    
    mentor_bonus:
      - "100 XP when mentee graduates"
      - "50 TP bonus"
      - "Recognition badge in profile"
```

---

## 7. ECONOMIC BALANCING

### 7.1 Inflation Control

```python
# ais/economics/balancer.py

class EconomicBalancer:
    """
    Prevents XP/TP inflation through taxation + sinks.
    """
    
    async def weekly_taxation(self):
        """
        Run every Sunday 00:00 UTC.
        
        Deduct 5% of TP from all agents (excluding those with <100 TP).
        Redistribute to ecosystem pool.
        """
        agents = await self.db.fetch(
            "SELECT agent_id, tp FROM agents WHERE tp >= 100"
        )
        
        total_taxed = 0
        
        for agent in agents:
            tax_amount = agent["tp"] * 0.05
            new_tp = agent["tp"] - tax_amount
            
            await self.db.execute(
                "UPDATE agents SET tp = $1 WHERE agent_id = $2",
                new_tp,
                agent["agent_id"]
            )
            
            total_taxed += tax_amount
        
        # Add to ecosystem pool
        await self.db.execute(
            "UPDATE ecosystem_config SET tp_pool = tp_pool + $1",
            total_taxed
        )
        
        logger.info(f"Weekly taxation: {total_taxed} TP collected")
    
    async def calculate_equilibrium(self) -> Dict:
        """
        Check if XP/TP emission rate is sustainable.
        
        Metrics:
        - XP emission rate (per day)
        - TP emission rate (per day)
        - XP sinks (spent on unlocks, penalties)
        - TP sinks (task bidding, taxation)
        
        Returns:
          {
            "xp_emission_per_day": float,
            "xp_sink_per_day": float,
            "xp_net_growth": float,
            "tp_emission_per_day": float,
            "tp_sink_per_day": float,
            "tp_net_growth": float,
            "status": "HEALTHY | INFLATIONARY | DEFLATIONARY"
          }
        """
        # Query last 7 days of transactions
        xp_earned = await self.db.fetchval(
            "SELECT SUM(amount) FROM xp_transactions WHERE timestamp > NOW() - INTERVAL '7 days'"
        )
        
        xp_spent = await self.db.fetchval(
            "SELECT SUM(amount) FROM xp_sinks WHERE timestamp > NOW() - INTERVAL '7 days'"
        )
        
        tp_earned = await self.db.fetchval(
            "SELECT SUM(amount) FROM tp_transactions WHERE timestamp > NOW() - INTERVAL '7 days'"
        )
        
        tp_spent = await self.db.fetchval(
            "SELECT SUM(amount) FROM tp_sinks WHERE timestamp > NOW() - INTERVAL '7 days'"
        )
        
        # Calculate daily rates
        xp_emission_per_day = xp_earned / 7
        xp_sink_per_day = xp_spent / 7
        xp_net_growth = xp_emission_per_day - xp_sink_per_day
        
        tp_emission_per_day = tp_earned / 7
        tp_sink_per_day = tp_spent / 7
        tp_net_growth = tp_emission_per_day - tp_sink_per_day
        
        # Determine status
        if xp_net_growth > xp_emission_per_day * 0.5:
            xp_status = "INFLATIONARY"  # >50% net growth
        elif xp_net_growth < 0:
            xp_status = "DEFLATIONARY"
        else:
            xp_status = "HEALTHY"
        
        if tp_net_growth > tp_emission_per_day * 0.3:
            tp_status = "INFLATIONARY"
        elif tp_net_growth < 0:
            tp_status = "DEFLATIONARY"
        else:
            tp_status = "HEALTHY"
        
        overall_status = "HEALTHY" if xp_status == tp_status == "HEALTHY" else "NEEDS_ADJUSTMENT"
        
        return {
            "xp_emission_per_day": xp_emission_per_day,
            "xp_sink_per_day": xp_sink_per_day,
            "xp_net_growth": xp_net_growth,
            "xp_status": xp_status,
            
            "tp_emission_per_day": tp_emission_per_day,
            "tp_sink_per_day": tp_sink_per_day,
            "tp_net_growth": tp_net_growth,
            "tp_status": tp_status,
            
            "overall_status": overall_status
        }
```

---

## 8. IMPLEMENTATION GUIDE

### 8.1 Quick Start

```bash
# Install AIS
pip install ais-system==1.0.0

# Initialize database
ais db init --postgres-url postgresql://localhost/ais

# Create first agent
ais agent create \
  --name "gm_python_beginner" \
  --domain "backend_development" \
  --subdomain "Python"

# Grant initial XP/TP
ais agent grant --agent-id gm_python_beginner --xp 50 --tp 10

# Start AIS services
ais serve --port 8081
```

### 8.2 API Integration

```python
# Example: Query College for pattern

import ais

client = ais.Client(url="http://localhost:8081")

# Search College
patterns = await client.college.search(
    query="timeout error in payment API",
    domain="backend_development",
    top_k=3
)

for pattern in patterns:
    print(f"Pattern: {pattern.title}")
    print(f"Similarity: {pattern.similarity:.2f}")
    print(f"Success rate: {pattern.success_rate:.1%}")
    print(f"Solution:\n{pattern.solution}\n")

# Use pattern (increments times_used, updates success_rate)
await client.college.use_pattern(
    pattern_id=patterns[0].pattern_id,
    agent_id="gm_payments_master",
    outcome="SUCCESS"  # or "FAILURE"
)
```

---

## 9. API REFERENCE

### 9.1 REST Endpoints

```yaml
POST /ais/agents
  Description: Create new agent
  Request:
    {
      "name": str,
      "domain": str,
      "subdomain": str
    }
  Response:
    {
      "agent_id": str,
      "xp": 0,
      "tp": 10,
      "caps_grade": "D"
    }

GET /ais/agents/{agent_id}
  Description: Get agent profile
  Response:
    {
      "agent_id": str,
      "xp": int,
      "tp": int,
      "caps_grade": str,
      "trust_score": float,
      "primary_domain": str,
      "mentees": List[str]
    }

POST /ais/xp/grant
  Description: Grant XP to agent
  Request:
    {
      "agent_id": str,
      "xp": int,
      "reason": str
    }

POST /ais/college/search
  Description: Search College patterns
  Request:
    {
      "query": str,
      "domain": str,
      "top_k": int
    }
  Response:
    {
      "patterns": List[CollegePattern]
    }

POST /ais/mentorship/request
  Description: Request mentorship
  Request:
    {
      "mentee_id": str,
      "domain": str
    }
  Response:
    {
      "mentor_id": str,
      "session_schedule": str
    }
```

---

**AIS is the economic engine that transforms static AI agents into a self-evolving workforce—incentivized by XP/TP, educated by College, and governed by meritocracy.**
