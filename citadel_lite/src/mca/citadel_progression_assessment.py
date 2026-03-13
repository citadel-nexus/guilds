#!/usr/bin/env python3
"""
CITADEL-NEXUS Progression Assessment Tool v1.0
===============================================
Comprehensive evaluation of project status across all components,
phases, deliverables, and readiness gates.

Usage:
    python citadel_progression_assessment.py [--output json|text|html]
    
Author: Citadel Operations Team
Date: January 10, 2026
"""

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, date
from enum import Enum
from typing import Dict, List, Optional, Tuple
from collections import defaultdict


# =============================================================================
# ENUMS & CONSTANTS
# =============================================================================

class Status(Enum):
    """Deliverable completion status"""
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    REVIEW = "review"
    COMPLETE = "complete"
    
    @property
    def weight(self) -> float:
        weights = {
            "not_started": 0.0,
            "in_progress": 0.4,
            "blocked": 0.2,
            "review": 0.8,
            "complete": 1.0
        }
        return weights[self.value]


class Priority(Enum):
    """Task priority levels"""
    CRITICAL = "critical"      # Blocks launch
    HIGH = "high"              # Core functionality
    MEDIUM = "medium"          # Important features
    LOW = "low"                # Nice to have
    

class ComponentType(Enum):
    """System component categories"""
    CORE = "core"              # Council, College, USO
    INFRASTRUCTURE = "infra"   # DB, Auth, Security
    INTEGRATION = "integration" # Webhooks, APIs
    FRONTEND = "frontend"      # IDE, Dashboard
    OPERATIONS = "operations"  # Discord, Monitoring
    BILLING = "billing"        # Subscriptions, Payments
    DOCUMENTATION = "docs"     # Specs, Guides


# =============================================================================
# DATA MODELS
# =============================================================================

@dataclass
class Deliverable:
    """Individual deliverable item"""
    id: str
    name: str
    description: str
    status: Status
    priority: Priority
    component: ComponentType
    phase: int
    estimated_hours: float
    actual_hours: float = 0.0
    owner: str = "unassigned"
    dependencies: List[str] = field(default_factory=list)
    blockers: List[str] = field(default_factory=list)
    notes: str = ""
    
    @property
    def completion_pct(self) -> float:
        return self.status.weight * 100
    
    @property
    def is_blocked(self) -> bool:
        return self.status == Status.BLOCKED or len(self.blockers) > 0


@dataclass
class Phase:
    """Project phase grouping"""
    number: int
    name: str
    description: str
    start_date: Optional[date]
    end_date: Optional[date]
    deliverables: List[str]  # Deliverable IDs
    go_criteria: List[str]
    
    
@dataclass
class Component:
    """System component"""
    id: str
    name: str
    type: ComponentType
    description: str
    deliverables: List[str]  # Deliverable IDs
    dependencies: List[str]  # Other component IDs
    spec_complete: bool = False
    code_complete: bool = False
    tests_complete: bool = False
    docs_complete: bool = False


# =============================================================================
# CITADEL PROJECT DEFINITION
# =============================================================================

class CitadelProjectDefinition:
    """
    Complete definition of the Citadel-Nexus project structure.
    This is the source of truth for all components, phases, and deliverables.
    """
    
    @staticmethod
    def get_components() -> Dict[str, Component]:
        """Define all system components"""
        return {
            # CORE SYSTEMS
            "council": Component(
                id="council",
                name="Council (S00-S03)",
                type=ComponentType.CORE,
                description="4-stage constitutional governance pipeline",
                deliverables=["CNL-001", "CNL-002", "CNL-003", "CNL-004", "CNL-005"],
                dependencies=[],
                spec_complete=True,
                code_complete=False,
                tests_complete=False,
                docs_complete=True
            ),
            "college": Component(
                id="college",
                name="College (28 Professors)",
                type=ComponentType.CORE,
                description="Specialized agents + FAISS vector knowledge graph",
                deliverables=["CLG-001", "CLG-002", "CLG-003", "CLG-004"],
                dependencies=["council"],
                spec_complete=True,
                code_complete=False,
                tests_complete=False,
                docs_complete=True
            ),
            "uso_economy": Component(
                id="uso_economy",
                name="USO SmartBank Economy",
                type=ComponentType.CORE,
                description="XP/TP/Trust scoring + CAPS grades",
                deliverables=["USO-001", "USO-002", "USO-003", "USO-004"],
                dependencies=["council"],
                spec_complete=True,
                code_complete=False,
                tests_complete=False,
                docs_complete=True
            ),
            "tavern": Component(
                id="tavern",
                name="TAVERN Memory",
                type=ComponentType.CORE,
                description="Document ingestion + retrieval + FAISS",
                deliverables=["TVN-001", "TVN-002", "TVN-003"],
                dependencies=[],
                spec_complete=True,
                code_complete=False,
                tests_complete=False,
                docs_complete=True
            ),
            "guardian": Component(
                id="guardian",
                name="Guardian Logs",
                type=ComponentType.CORE,
                description="Immutable SHA-256 hash chain audit trail",
                deliverables=["GDN-001", "GDN-002", "GDN-003"],
                dependencies=["council"],
                spec_complete=True,
                code_complete=False,
                tests_complete=False,
                docs_complete=True
            ),
            "genesis": Component(
                id="genesis",
                name="Genesis Architect",
                type=ComponentType.CORE,
                description="Metaprogramming - agents spawn agents",
                deliverables=["GEN-001", "GEN-002"],
                dependencies=["college", "uso_economy"],
                spec_complete=True,
                code_complete=False,
                tests_complete=False,
                docs_complete=False
            ),
            
            # INFRASTRUCTURE
            "database": Component(
                id="database",
                name="Database Layer",
                type=ComponentType.INFRASTRUCTURE,
                description="Supabase PostgreSQL + RLS policies",
                deliverables=["DB-001", "DB-002", "DB-003", "DB-004"],
                dependencies=[],
                spec_complete=True,
                code_complete=False,
                tests_complete=False,
                docs_complete=True
            ),
            "auth": Component(
                id="auth",
                name="Authentication",
                type=ComponentType.INFRASTRUCTURE,
                description="JWT + OAuth2 + CAPS-based authorization",
                deliverables=["AUTH-001", "AUTH-002", "AUTH-003"],
                dependencies=["database"],
                spec_complete=True,
                code_complete=False,
                tests_complete=False,
                docs_complete=True
            ),
            "security": Component(
                id="security",
                name="Security Infrastructure",
                type=ComponentType.INFRASTRUCTURE,
                description="WAF, rate limiting, encryption",
                deliverables=["SEC-001", "SEC-002", "SEC-003"],
                dependencies=["auth"],
                spec_complete=True,
                code_complete=False,
                tests_complete=False,
                docs_complete=True
            ),
            
            # INTEGRATIONS (NEXUS)
            "nexus_foundation": Component(
                id="nexus_foundation",
                name="Nexus Foundation",
                type=ComponentType.INTEGRATION,
                description="Adapter base, registry, dispatcher",
                deliverables=["NXS-001", "NXS-002", "NXS-003", "NXS-004"],
                dependencies=["database"],
                spec_complete=True,
                code_complete=False,
                tests_complete=False,
                docs_complete=True
            ),
            "nexus_adapters": Component(
                id="nexus_adapters",
                name="Nexus Adapters",
                type=ComponentType.INTEGRATION,
                description="8 SaaS adapters (GitLab, Stripe, etc.)",
                deliverables=["NXA-001", "NXA-002", "NXA-003", "NXA-004", 
                             "NXA-005", "NXA-006", "NXA-007", "NXA-008"],
                dependencies=["nexus_foundation"],
                spec_complete=True,
                code_complete=False,
                tests_complete=False,
                docs_complete=False
            ),
            "nexus_governance": Component(
                id="nexus_governance",
                name="Nexus Governance",
                type=ComponentType.INTEGRATION,
                description="Signal routing + handlers",
                deliverables=["NXG-001", "NXG-002", "NXG-003"],
                dependencies=["nexus_adapters", "council"],
                spec_complete=True,
                code_complete=False,
                tests_complete=False,
                docs_complete=False
            ),
            
            # FRONTEND
            "ide": Component(
                id="ide",
                name="CITADEL IDE",
                type=ComponentType.FRONTEND,
                description="Monaco editor + integrations panel",
                deliverables=["IDE-001", "IDE-002", "IDE-003", "IDE-004", "IDE-005"],
                dependencies=["auth", "nexus_foundation"],
                spec_complete=True,
                code_complete=False,
                tests_complete=False,
                docs_complete=True
            ),
            "dashboard": Component(
                id="dashboard",
                name="Admin Dashboard",
                type=ComponentType.FRONTEND,
                description="Monitoring, analytics, management",
                deliverables=["DSH-001", "DSH-002", "DSH-003"],
                dependencies=["auth", "database"],
                spec_complete=False,
                code_complete=False,
                tests_complete=False,
                docs_complete=False
            ),
            
            # OPERATIONS
            "discord": Component(
                id="discord",
                name="Discord Bot",
                type=ComponentType.OPERATIONS,
                description="Slash commands, memory, onboarding",
                deliverables=["DIS-001", "DIS-002", "DIS-003", "DIS-004"],
                dependencies=["tavern", "auth"],
                spec_complete=True,
                code_complete=False,
                tests_complete=False,
                docs_complete=True
            ),
            "monitoring": Component(
                id="monitoring",
                name="Observability",
                type=ComponentType.OPERATIONS,
                description="Datadog APM + PostHog analytics",
                deliverables=["MON-001", "MON-002", "MON-003"],
                dependencies=[],
                spec_complete=True,
                code_complete=False,
                tests_complete=False,
                docs_complete=True
            ),
            "reflex": Component(
                id="reflex",
                name="REFLEX System",
                type=ComponentType.OPERATIONS,
                description="Autonomous recovery triggers",
                deliverables=["RFX-001", "RFX-002"],
                dependencies=["guardian", "monitoring"],
                spec_complete=True,
                code_complete=False,
                tests_complete=False,
                docs_complete=False
            ),
            
            # BILLING
            "billing_core": Component(
                id="billing_core",
                name="Billing Core",
                type=ComponentType.BILLING,
                description="Subscriptions, plans, invoices",
                deliverables=["BIL-001", "BIL-002", "BIL-003", "BIL-004"],
                dependencies=["database", "auth"],
                spec_complete=True,
                code_complete=False,
                tests_complete=False,
                docs_complete=True
            ),
            "billing_payments": Component(
                id="billing_payments",
                name="Payment Processing",
                type=ComponentType.BILLING,
                description="Stripe/PayPal integration",
                deliverables=["PAY-001", "PAY-002", "PAY-003"],
                dependencies=["billing_core"],
                spec_complete=True,
                code_complete=False,
                tests_complete=False,
                docs_complete=True
            ),
            "billing_ledger": Component(
                id="billing_ledger",
                name="Billing Ledger",
                type=ComponentType.BILLING,
                description="Immutable audit trail for billing",
                deliverables=["BLD-001", "BLD-002"],
                dependencies=["billing_core", "guardian"],
                spec_complete=True,
                code_complete=False,
                tests_complete=False,
                docs_complete=True
            ),
        }
    
    @staticmethod
    def get_deliverables() -> Dict[str, Deliverable]:
        """Define all deliverables with current status"""
        deliverables = {
            # =====================================================================
            # COUNCIL DELIVERABLES
            # =====================================================================
            "CNL-001": Deliverable(
                id="CNL-001",
                name="S00 Generator Agent",
                description="Normalize intent, hash, seed with context",
                status=Status.NOT_STARTED,
                priority=Priority.CRITICAL,
                component=ComponentType.CORE,
                phase=1,
                estimated_hours=16,
                owner="backend_lead"
            ),
            "CNL-002": Deliverable(
                id="CNL-002",
                name="S01 Definer Agent",
                description="Schema validate, CAPS hydrate, cost calculate",
                status=Status.NOT_STARTED,
                priority=Priority.CRITICAL,
                component=ComponentType.CORE,
                phase=1,
                estimated_hours=16,
                dependencies=["CNL-001"]
            ),
            "CNL-003": Deliverable(
                id="CNL-003",
                name="S02 FATE Evaluator",
                description="Enforce gates, issue ALLOW/REVIEW/DENY verdict",
                status=Status.NOT_STARTED,
                priority=Priority.CRITICAL,
                component=ComponentType.CORE,
                phase=1,
                estimated_hours=20,
                dependencies=["CNL-002"]
            ),
            "CNL-004": Deliverable(
                id="CNL-004",
                name="S03 Archivist Agent",
                description="Immutable write, hash chain, trust update",
                status=Status.NOT_STARTED,
                priority=Priority.CRITICAL,
                component=ComponentType.CORE,
                phase=1,
                estimated_hours=12,
                dependencies=["CNL-003", "GDN-001"]
            ),
            "CNL-005": Deliverable(
                id="CNL-005",
                name="Council Service Orchestrator",
                description="Full pipeline orchestration + routing",
                status=Status.NOT_STARTED,
                priority=Priority.CRITICAL,
                component=ComponentType.CORE,
                phase=1,
                estimated_hours=16,
                dependencies=["CNL-001", "CNL-002", "CNL-003", "CNL-004"]
            ),
            
            # =====================================================================
            # COLLEGE DELIVERABLES
            # =====================================================================
            "CLG-001": Deliverable(
                id="CLG-001",
                name="Professor Base Class",
                description="Abstract professor with analyze/publish methods",
                status=Status.NOT_STARTED,
                priority=Priority.HIGH,
                component=ComponentType.CORE,
                phase=2,
                estimated_hours=8
            ),
            "CLG-002": Deliverable(
                id="CLG-002",
                name="28 Professor Implementations",
                description="Domain-specific professors (engineering, legal, etc.)",
                status=Status.NOT_STARTED,
                priority=Priority.HIGH,
                component=ComponentType.CORE,
                phase=2,
                estimated_hours=40,
                dependencies=["CLG-001"]
            ),
            "CLG-003": Deliverable(
                id="CLG-003",
                name="College Vector Store",
                description="FAISS integration for embeddings storage",
                status=Status.NOT_STARTED,
                priority=Priority.HIGH,
                component=ComponentType.CORE,
                phase=2,
                estimated_hours=12,
                dependencies=["TVN-002"]
            ),
            "CLG-004": Deliverable(
                id="CLG-004",
                name="Guildmaster System",
                description="Trait consumption + cross-pollination",
                status=Status.NOT_STARTED,
                priority=Priority.MEDIUM,
                component=ComponentType.CORE,
                phase=3,
                estimated_hours=20,
                dependencies=["CLG-002", "CLG-003"]
            ),
            
            # =====================================================================
            # USO ECONOMY DELIVERABLES
            # =====================================================================
            "USO-001": Deliverable(
                id="USO-001",
                name="XP/TP Service",
                description="Experience and Trust point management",
                status=Status.NOT_STARTED,
                priority=Priority.HIGH,
                component=ComponentType.CORE,
                phase=2,
                estimated_hours=12
            ),
            "USO-002": Deliverable(
                id="USO-002",
                name="CAPS Calculator",
                description="Grade calculation (S→F) across 4 dimensions",
                status=Status.NOT_STARTED,
                priority=Priority.HIGH,
                component=ComponentType.CORE,
                phase=2,
                estimated_hours=8,
                dependencies=["USO-001"]
            ),
            "USO-003": Deliverable(
                id="USO-003",
                name="Ledger Service",
                description="Economic transaction ledger",
                status=Status.NOT_STARTED,
                priority=Priority.HIGH,
                component=ComponentType.CORE,
                phase=2,
                estimated_hours=12,
                dependencies=["GDN-001"]
            ),
            "USO-004": Deliverable(
                id="USO-004",
                name="Nemesis Audit",
                description="Automatic underperformer detection",
                status=Status.NOT_STARTED,
                priority=Priority.MEDIUM,
                component=ComponentType.CORE,
                phase=3,
                estimated_hours=16,
                dependencies=["USO-002", "USO-003"]
            ),
            
            # =====================================================================
            # TAVERN DELIVERABLES
            # =====================================================================
            "TVN-001": Deliverable(
                id="TVN-001",
                name="Document Parser",
                description="Multi-format document parsing",
                status=Status.NOT_STARTED,
                priority=Priority.HIGH,
                component=ComponentType.CORE,
                phase=1,
                estimated_hours=12
            ),
            "TVN-002": Deliverable(
                id="TVN-002",
                name="FAISS Vector Store",
                description="Embedding storage + similarity search",
                status=Status.NOT_STARTED,
                priority=Priority.HIGH,
                component=ComponentType.CORE,
                phase=1,
                estimated_hours=16
            ),
            "TVN-003": Deliverable(
                id="TVN-003",
                name="Retrieval API",
                description="Context retrieval endpoints",
                status=Status.NOT_STARTED,
                priority=Priority.HIGH,
                component=ComponentType.CORE,
                phase=2,
                estimated_hours=8,
                dependencies=["TVN-001", "TVN-002"]
            ),
            
            # =====================================================================
            # GUARDIAN DELIVERABLES
            # =====================================================================
            "GDN-001": Deliverable(
                id="GDN-001",
                name="Hash Chain Service",
                description="SHA-256 hash chain implementation",
                status=Status.NOT_STARTED,
                priority=Priority.CRITICAL,
                component=ComponentType.CORE,
                phase=1,
                estimated_hours=12
            ),
            "GDN-002": Deliverable(
                id="GDN-002",
                name="Audit Log Writer",
                description="Immutable log insertion",
                status=Status.NOT_STARTED,
                priority=Priority.CRITICAL,
                component=ComponentType.CORE,
                phase=1,
                estimated_hours=8,
                dependencies=["GDN-001", "DB-001"]
            ),
            "GDN-003": Deliverable(
                id="GDN-003",
                name="Integrity Verifier",
                description="Hash chain verification",
                status=Status.NOT_STARTED,
                priority=Priority.HIGH,
                component=ComponentType.CORE,
                phase=2,
                estimated_hours=8,
                dependencies=["GDN-001"]
            ),
            
            # =====================================================================
            # GENESIS DELIVERABLES
            # =====================================================================
            "GEN-001": Deliverable(
                id="GEN-001",
                name="Genome Specification Parser",
                description="YAML agent genome parsing",
                status=Status.NOT_STARTED,
                priority=Priority.MEDIUM,
                component=ComponentType.CORE,
                phase=3,
                estimated_hours=12
            ),
            "GEN-002": Deliverable(
                id="GEN-002",
                name="Agent Spawner",
                description="Dynamic agent creation from genome",
                status=Status.NOT_STARTED,
                priority=Priority.MEDIUM,
                component=ComponentType.CORE,
                phase=3,
                estimated_hours=20,
                dependencies=["GEN-001", "CLG-002"]
            ),
            
            # =====================================================================
            # DATABASE DELIVERABLES
            # =====================================================================
            "DB-001": Deliverable(
                id="DB-001",
                name="Core Schema Migration",
                description="All core tables (agents, logs, etc.)",
                status=Status.COMPLETE,
                priority=Priority.CRITICAL,
                component=ComponentType.INFRASTRUCTURE,
                phase=1,
                estimated_hours=8,
                actual_hours=8,
                notes="Schema defined in billing_schema.md"
            ),
            "DB-002": Deliverable(
                id="DB-002",
                name="RLS Policies",
                description="Row-level security for all tables",
                status=Status.COMPLETE,
                priority=Priority.CRITICAL,
                component=ComponentType.INFRASTRUCTURE,
                phase=1,
                estimated_hours=8,
                actual_hours=8,
                notes="Defined in citadel-ops-v2-1.md"
            ),
            "DB-003": Deliverable(
                id="DB-003",
                name="Billing Schema",
                description="Subscriptions, invoices, payments tables",
                status=Status.COMPLETE,
                priority=Priority.CRITICAL,
                component=ComponentType.INFRASTRUCTURE,
                phase=1,
                estimated_hours=12,
                actual_hours=12,
                notes="Complete in billing_schema.md"
            ),
            "DB-004": Deliverable(
                id="DB-004",
                name="Index Optimization",
                description="Performance indexes for queries",
                status=Status.NOT_STARTED,
                priority=Priority.MEDIUM,
                component=ComponentType.INFRASTRUCTURE,
                phase=4,
                estimated_hours=4
            ),
            
            # =====================================================================
            # AUTH DELIVERABLES
            # =====================================================================
            "AUTH-001": Deliverable(
                id="AUTH-001",
                name="JWT Service",
                description="Token creation/verification",
                status=Status.NOT_STARTED,
                priority=Priority.CRITICAL,
                component=ComponentType.INFRASTRUCTURE,
                phase=1,
                estimated_hours=8
            ),
            "AUTH-002": Deliverable(
                id="AUTH-002",
                name="CAPS Authorization",
                description="Grade-based permission checking",
                status=Status.NOT_STARTED,
                priority=Priority.CRITICAL,
                component=ComponentType.INFRASTRUCTURE,
                phase=1,
                estimated_hours=8,
                dependencies=["AUTH-001", "USO-002"]
            ),
            "AUTH-003": Deliverable(
                id="AUTH-003",
                name="OAuth2 Integration",
                description="GitLab/GitHub OAuth",
                status=Status.NOT_STARTED,
                priority=Priority.HIGH,
                component=ComponentType.INFRASTRUCTURE,
                phase=2,
                estimated_hours=12
            ),
            
            # =====================================================================
            # SECURITY DELIVERABLES
            # =====================================================================
            "SEC-001": Deliverable(
                id="SEC-001",
                name="Rate Limiter",
                description="Redis-based rate limiting",
                status=Status.NOT_STARTED,
                priority=Priority.HIGH,
                component=ComponentType.INFRASTRUCTURE,
                phase=2,
                estimated_hours=8
            ),
            "SEC-002": Deliverable(
                id="SEC-002",
                name="Webhook Signature Verifier",
                description="HMAC verification for webhooks",
                status=Status.NOT_STARTED,
                priority=Priority.CRITICAL,
                component=ComponentType.INFRASTRUCTURE,
                phase=1,
                estimated_hours=6
            ),
            "SEC-003": Deliverable(
                id="SEC-003",
                name="Encryption Service",
                description="At-rest encryption helpers",
                status=Status.NOT_STARTED,
                priority=Priority.HIGH,
                component=ComponentType.INFRASTRUCTURE,
                phase=2,
                estimated_hours=6
            ),
            
            # =====================================================================
            # NEXUS FOUNDATION DELIVERABLES
            # =====================================================================
            "NXS-001": Deliverable(
                id="NXS-001",
                name="BaseAdapter Class",
                description="Abstract adapter with standard interface",
                status=Status.NOT_STARTED,
                priority=Priority.CRITICAL,
                component=ComponentType.INTEGRATION,
                phase=1,
                estimated_hours=8
            ),
            "NXS-002": Deliverable(
                id="NXS-002",
                name="Integration Registry",
                description="Adapter registration + discovery",
                status=Status.NOT_STARTED,
                priority=Priority.CRITICAL,
                component=ComponentType.INTEGRATION,
                phase=1,
                estimated_hours=6,
                dependencies=["NXS-001"]
            ),
            "NXS-003": Deliverable(
                id="NXS-003",
                name="WebhookEnvelope",
                description="Standardized webhook payload wrapper",
                status=Status.NOT_STARTED,
                priority=Priority.CRITICAL,
                component=ComponentType.INTEGRATION,
                phase=1,
                estimated_hours=6
            ),
            "NXS-004": Deliverable(
                id="NXS-004",
                name="WebhookDispatcher",
                description="Route webhooks to handlers",
                status=Status.NOT_STARTED,
                priority=Priority.CRITICAL,
                component=ComponentType.INTEGRATION,
                phase=1,
                estimated_hours=10,
                dependencies=["NXS-001", "NXS-002", "NXS-003"]
            ),
            
            # =====================================================================
            # NEXUS ADAPTER DELIVERABLES
            # =====================================================================
            "NXA-001": Deliverable(
                id="NXA-001",
                name="GitLab Adapter",
                description="Push, MR, pipeline, issue events",
                status=Status.NOT_STARTED,
                priority=Priority.CRITICAL,
                component=ComponentType.INTEGRATION,
                phase=2,
                estimated_hours=9,
                dependencies=["NXS-004"]
            ),
            "NXA-002": Deliverable(
                id="NXA-002",
                name="Stripe Adapter",
                description="Charges, subscriptions, invoices",
                status=Status.NOT_STARTED,
                priority=Priority.CRITICAL,
                component=ComponentType.INTEGRATION,
                phase=2,
                estimated_hours=9,
                dependencies=["NXS-004"]
            ),
            "NXA-003": Deliverable(
                id="NXA-003",
                name="Datadog Adapter",
                description="Alerts, events, metrics",
                status=Status.NOT_STARTED,
                priority=Priority.HIGH,
                component=ComponentType.INTEGRATION,
                phase=2,
                estimated_hours=9,
                dependencies=["NXS-004"]
            ),
            "NXA-004": Deliverable(
                id="NXA-004",
                name="PostHog Adapter",
                description="Feature flags, analytics",
                status=Status.NOT_STARTED,
                priority=Priority.HIGH,
                component=ComponentType.INTEGRATION,
                phase=2,
                estimated_hours=9,
                dependencies=["NXS-004"]
            ),
            "NXA-005": Deliverable(
                id="NXA-005",
                name="DocuSign Adapter",
                description="Envelope, signing, completion",
                status=Status.NOT_STARTED,
                priority=Priority.MEDIUM,
                component=ComponentType.INTEGRATION,
                phase=3,
                estimated_hours=9,
                dependencies=["NXS-004"]
            ),
            "NXA-006": Deliverable(
                id="NXA-006",
                name="Intercom Adapter",
                description="Users, conversations, messages",
                status=Status.NOT_STARTED,
                priority=Priority.MEDIUM,
                component=ComponentType.INTEGRATION,
                phase=3,
                estimated_hours=9,
                dependencies=["NXS-004"]
            ),
            "NXA-007": Deliverable(
                id="NXA-007",
                name="Slack Adapter",
                description="Messages, reactions, events",
                status=Status.NOT_STARTED,
                priority=Priority.HIGH,
                component=ComponentType.INTEGRATION,
                phase=3,
                estimated_hours=9,
                dependencies=["NXS-004"]
            ),
            "NXA-008": Deliverable(
                id="NXA-008",
                name="Email Adapter",
                description="Receives, bounces, opens, clicks",
                status=Status.NOT_STARTED,
                priority=Priority.MEDIUM,
                component=ComponentType.INTEGRATION,
                phase=3,
                estimated_hours=9,
                dependencies=["NXS-004"]
            ),
            
            # =====================================================================
            # NEXUS GOVERNANCE DELIVERABLES
            # =====================================================================
            "NXG-001": Deliverable(
                id="NXG-001",
                name="Signal Router",
                description="Route signals by class to handlers",
                status=Status.NOT_STARTED,
                priority=Priority.HIGH,
                component=ComponentType.INTEGRATION,
                phase=3,
                estimated_hours=8,
                dependencies=["NXS-004"]
            ),
            "NXG-002": Deliverable(
                id="NXG-002",
                name="Signal Handlers",
                description="6 handlers for signal classes",
                status=Status.NOT_STARTED,
                priority=Priority.HIGH,
                component=ComponentType.INTEGRATION,
                phase=3,
                estimated_hours=12,
                dependencies=["NXG-001", "CNL-005"]
            ),
            "NXG-003": Deliverable(
                id="NXG-003",
                name="Retry & Rate Limit",
                description="Exponential backoff + quotas",
                status=Status.NOT_STARTED,
                priority=Priority.HIGH,
                component=ComponentType.INTEGRATION,
                phase=3,
                estimated_hours=10,
                dependencies=["SEC-001"]
            ),
            
            # =====================================================================
            # IDE DELIVERABLES
            # =====================================================================
            "IDE-001": Deliverable(
                id="IDE-001",
                name="Monaco Editor Integration",
                description="Code editor with syntax highlighting",
                status=Status.NOT_STARTED,
                priority=Priority.HIGH,
                component=ComponentType.FRONTEND,
                phase=4,
                estimated_hours=20
            ),
            "IDE-002": Deliverable(
                id="IDE-002",
                name="File Tree Panel",
                description="Project file browser",
                status=Status.NOT_STARTED,
                priority=Priority.HIGH,
                component=ComponentType.FRONTEND,
                phase=4,
                estimated_hours=12,
                dependencies=["IDE-001"]
            ),
            "IDE-003": Deliverable(
                id="IDE-003",
                name="Git Integration Panel",
                description="Diff viewer, commit, push",
                status=Status.NOT_STARTED,
                priority=Priority.HIGH,
                component=ComponentType.FRONTEND,
                phase=4,
                estimated_hours=16,
                dependencies=["IDE-001", "NXA-001"]
            ),
            "IDE-004": Deliverable(
                id="IDE-004",
                name="Right Panel Integrations",
                description="Linear, Slack, Notion panels",
                status=Status.NOT_STARTED,
                priority=Priority.MEDIUM,
                component=ComponentType.FRONTEND,
                phase=5,
                estimated_hours=24,
                dependencies=["IDE-001"]
            ),
            "IDE-005": Deliverable(
                id="IDE-005",
                name="AI Code Assistance",
                description="Code generation from comments",
                status=Status.NOT_STARTED,
                priority=Priority.MEDIUM,
                component=ComponentType.FRONTEND,
                phase=5,
                estimated_hours=20,
                dependencies=["IDE-001"]
            ),
            
            # =====================================================================
            # DASHBOARD DELIVERABLES
            # =====================================================================
            "DSH-001": Deliverable(
                id="DSH-001",
                name="Dashboard Layout",
                description="Main dashboard structure",
                status=Status.NOT_STARTED,
                priority=Priority.MEDIUM,
                component=ComponentType.FRONTEND,
                phase=5,
                estimated_hours=16
            ),
            "DSH-002": Deliverable(
                id="DSH-002",
                name="Monitoring Widgets",
                description="Health, metrics, alerts",
                status=Status.NOT_STARTED,
                priority=Priority.MEDIUM,
                component=ComponentType.FRONTEND,
                phase=5,
                estimated_hours=20,
                dependencies=["DSH-001", "MON-001"]
            ),
            "DSH-003": Deliverable(
                id="DSH-003",
                name="Admin Management",
                description="Users, orgs, billing admin",
                status=Status.NOT_STARTED,
                priority=Priority.MEDIUM,
                component=ComponentType.FRONTEND,
                phase=5,
                estimated_hours=24,
                dependencies=["DSH-001", "BIL-001"]
            ),
            
            # =====================================================================
            # DISCORD DELIVERABLES
            # =====================================================================
            "DIS-001": Deliverable(
                id="DIS-001",
                name="Bot Framework",
                description="Discord.py bot setup",
                status=Status.COMPLETE,
                priority=Priority.HIGH,
                component=ComponentType.OPERATIONS,
                phase=1,
                estimated_hours=8,
                actual_hours=8,
                notes="Spec complete in citadel-ops-v2-1.md"
            ),
            "DIS-002": Deliverable(
                id="DIS-002",
                name="Slash Commands",
                description="/task, /memory, /context, /onboard",
                status=Status.REVIEW,
                priority=Priority.HIGH,
                component=ComponentType.OPERATIONS,
                phase=2,
                estimated_hours=16,
                actual_hours=12,
                dependencies=["DIS-001"],
                notes="Implementation in spec, needs code review"
            ),
            "DIS-003": Deliverable(
                id="DIS-003",
                name="Memory Integration",
                description="GCS + FAISS memory backend",
                status=Status.IN_PROGRESS,
                priority=Priority.HIGH,
                component=ComponentType.OPERATIONS,
                phase=2,
                estimated_hours=12,
                actual_hours=6,
                dependencies=["DIS-001", "TVN-002"]
            ),
            "DIS-004": Deliverable(
                id="DIS-004",
                name="Onboarding Flow",
                description="7-step user onboarding",
                status=Status.REVIEW,
                priority=Priority.MEDIUM,
                component=ComponentType.OPERATIONS,
                phase=2,
                estimated_hours=8,
                actual_hours=8,
                dependencies=["DIS-002"],
                notes="Spec complete, needs testing"
            ),
            
            # =====================================================================
            # MONITORING DELIVERABLES
            # =====================================================================
            "MON-001": Deliverable(
                id="MON-001",
                name="Datadog APM Setup",
                description="Distributed tracing configuration",
                status=Status.NOT_STARTED,
                priority=Priority.HIGH,
                component=ComponentType.OPERATIONS,
                phase=3,
                estimated_hours=8
            ),
            "MON-002": Deliverable(
                id="MON-002",
                name="PostHog Analytics",
                description="User analytics + feature flags",
                status=Status.NOT_STARTED,
                priority=Priority.HIGH,
                component=ComponentType.OPERATIONS,
                phase=3,
                estimated_hours=8
            ),
            "MON-003": Deliverable(
                id="MON-003",
                name="Alert Rules",
                description="Alerting for critical issues",
                status=Status.NOT_STARTED,
                priority=Priority.HIGH,
                component=ComponentType.OPERATIONS,
                phase=4,
                estimated_hours=6,
                dependencies=["MON-001"]
            ),
            
            # =====================================================================
            # REFLEX DELIVERABLES
            # =====================================================================
            "RFX-001": Deliverable(
                id="RFX-001",
                name="Trigger Engine",
                description="Pattern-based trigger detection",
                status=Status.NOT_STARTED,
                priority=Priority.MEDIUM,
                component=ComponentType.OPERATIONS,
                phase=4,
                estimated_hours=16,
                dependencies=["GDN-002", "MON-001"]
            ),
            "RFX-002": Deliverable(
                id="RFX-002",
                name="Recovery Actions",
                description="Automated recovery procedures",
                status=Status.NOT_STARTED,
                priority=Priority.MEDIUM,
                component=ComponentType.OPERATIONS,
                phase=4,
                estimated_hours=12,
                dependencies=["RFX-001"]
            ),
            
            # =====================================================================
            # BILLING CORE DELIVERABLES
            # =====================================================================
            "BIL-001": Deliverable(
                id="BIL-001",
                name="Subscription Service",
                description="Create, upgrade, downgrade, cancel",
                status=Status.NOT_STARTED,
                priority=Priority.CRITICAL,
                component=ComponentType.BILLING,
                phase=3,
                estimated_hours=16,
                dependencies=["DB-003"]
            ),
            "BIL-002": Deliverable(
                id="BIL-002",
                name="Invoice Generator",
                description="Monthly invoice generation",
                status=Status.NOT_STARTED,
                priority=Priority.CRITICAL,
                component=ComponentType.BILLING,
                phase=3,
                estimated_hours=12,
                dependencies=["BIL-001"]
            ),
            "BIL-003": Deliverable(
                id="BIL-003",
                name="Usage Tracker",
                description="API call / agent usage metering",
                status=Status.NOT_STARTED,
                priority=Priority.HIGH,
                component=ComponentType.BILLING,
                phase=3,
                estimated_hours=10,
                dependencies=["BIL-001"]
            ),
            "BIL-004": Deliverable(
                id="BIL-004",
                name="Dunning Manager",
                description="Failed payment retry logic",
                status=Status.NOT_STARTED,
                priority=Priority.MEDIUM,
                component=ComponentType.BILLING,
                phase=4,
                estimated_hours=8,
                dependencies=["PAY-001"]
            ),
            
            # =====================================================================
            # PAYMENT DELIVERABLES
            # =====================================================================
            "PAY-001": Deliverable(
                id="PAY-001",
                name="Stripe Integration",
                description="Payment processing via Stripe",
                status=Status.NOT_STARTED,
                priority=Priority.CRITICAL,
                component=ComponentType.BILLING,
                phase=3,
                estimated_hours=16,
                dependencies=["BIL-001"]
            ),
            "PAY-002": Deliverable(
                id="PAY-002",
                name="Webhook Handler",
                description="Stripe webhook processing",
                status=Status.NOT_STARTED,
                priority=Priority.CRITICAL,
                component=ComponentType.BILLING,
                phase=3,
                estimated_hours=8,
                dependencies=["PAY-001", "NXA-002"]
            ),
            "PAY-003": Deliverable(
                id="PAY-003",
                name="Refund Service",
                description="Refund request + processing",
                status=Status.NOT_STARTED,
                priority=Priority.MEDIUM,
                component=ComponentType.BILLING,
                phase=4,
                estimated_hours=8,
                dependencies=["PAY-001"]
            ),
            
            # =====================================================================
            # BILLING LEDGER DELIVERABLES
            # =====================================================================
            "BLD-001": Deliverable(
                id="BLD-001",
                name="Billing Event Logger",
                description="Log all billing events immutably",
                status=Status.NOT_STARTED,
                priority=Priority.HIGH,
                component=ComponentType.BILLING,
                phase=3,
                estimated_hours=8,
                dependencies=["GDN-001", "BIL-001"]
            ),
            "BLD-002": Deliverable(
                id="BLD-002",
                name="Compliance Reports",
                description="SOC2/GDPR audit report generation",
                status=Status.NOT_STARTED,
                priority=Priority.MEDIUM,
                component=ComponentType.BILLING,
                phase=4,
                estimated_hours=12,
                dependencies=["BLD-001"]
            ),
        }
        
        return deliverables
    
    @staticmethod
    def get_phases() -> Dict[int, Phase]:
        """Define project phases"""
        return {
            1: Phase(
                number=1,
                name="Foundation",
                description="Core infrastructure, database, auth, hash chain",
                start_date=date(2026, 1, 13),
                end_date=date(2026, 1, 17),
                deliverables=[
                    "CNL-001", "CNL-002", "CNL-003", "CNL-004", "CNL-005",
                    "GDN-001", "GDN-002", "TVN-001", "TVN-002",
                    "DB-001", "DB-002", "DB-003", "AUTH-001", "SEC-002",
                    "NXS-001", "NXS-002", "NXS-003", "NXS-004", "DIS-001"
                ],
                go_criteria=[
                    "Council S00-S03 pipeline working locally",
                    "Guardian hash chain verifiable",
                    "All database schemas migrated",
                    "JWT authentication functional"
                ]
            ),
            2: Phase(
                number=2,
                name="Core Agents & Adapters",
                description="College, USO, GitLab+Stripe adapters",
                start_date=date(2026, 1, 20),
                end_date=date(2026, 1, 24),
                deliverables=[
                    "CLG-001", "CLG-002", "CLG-003",
                    "USO-001", "USO-002", "USO-003",
                    "GDN-003", "TVN-003", "AUTH-002", "AUTH-003",
                    "SEC-001", "SEC-003",
                    "NXA-001", "NXA-002", "NXA-003", "NXA-004",
                    "DIS-002", "DIS-003", "DIS-004"
                ],
                go_criteria=[
                    "28 Professors implemented",
                    "CAPS grades calculating correctly",
                    "GitLab + Stripe webhooks processing",
                    "Discord commands functional"
                ]
            ),
            3: Phase(
                number=3,
                name="Advanced Features",
                description="Remaining adapters, billing, signal routing",
                start_date=date(2026, 1, 27),
                end_date=date(2026, 1, 31),
                deliverables=[
                    "CLG-004", "USO-004", "GEN-001", "GEN-002",
                    "NXA-005", "NXA-006", "NXA-007", "NXA-008",
                    "NXG-001", "NXG-002", "NXG-003",
                    "BIL-001", "BIL-002", "BIL-003",
                    "PAY-001", "PAY-002", "BLD-001",
                    "MON-001", "MON-002"
                ],
                go_criteria=[
                    "All 8 adapters implemented",
                    "Signal routing to handlers working",
                    "Subscription creation functional",
                    "Stripe payments processing"
                ]
            ),
            4: Phase(
                number=4,
                name="Testing & Validation",
                description="Load testing, security audit, staging deploy",
                start_date=date(2026, 2, 3),
                end_date=date(2026, 2, 7),
                deliverables=[
                    "DB-004", "MON-003", "RFX-001", "RFX-002",
                    "BIL-004", "PAY-003", "BLD-002",
                    "IDE-001", "IDE-002", "IDE-003"
                ],
                go_criteria=[
                    "1,000 events/sec sustained",
                    "p99 latency < 100ms",
                    "Security audit passed",
                    "48-hour staging stability test passed"
                ]
            ),
            5: Phase(
                number=5,
                name="Production Launch",
                description="Final polish, docs, production deploy",
                start_date=date(2026, 2, 10),
                end_date=date(2026, 2, 14),
                deliverables=[
                    "IDE-004", "IDE-005",
                    "DSH-001", "DSH-002", "DSH-003"
                ],
                go_criteria=[
                    "Documentation complete",
                    "Gradual rollout successful",
                    "Customer communications sent",
                    "Incident response plan active"
                ]
            ),
        }


# =============================================================================
# ASSESSMENT ENGINE
# =============================================================================

class ProgressionAssessment:
    """
    Main assessment engine that evaluates project progression
    across all dimensions.
    """
    
    def __init__(self):
        self.components = CitadelProjectDefinition.get_components()
        self.deliverables = CitadelProjectDefinition.get_deliverables()
        self.phases = CitadelProjectDefinition.get_phases()
        self.assessment_date = datetime.now()
    
    # -------------------------------------------------------------------------
    # CORE METRICS
    # -------------------------------------------------------------------------
    
    def calculate_overall_completion(self) -> float:
        """Calculate weighted overall completion percentage"""
        total_weight = 0
        completed_weight = 0
        
        priority_weights = {
            Priority.CRITICAL: 3.0,
            Priority.HIGH: 2.0,
            Priority.MEDIUM: 1.0,
            Priority.LOW: 0.5
        }
        
        for d in self.deliverables.values():
            weight = priority_weights[d.priority]
            total_weight += weight
            completed_weight += weight * d.status.weight
        
        return (completed_weight / total_weight) * 100 if total_weight > 0 else 0
    
    def calculate_phase_completion(self, phase_num: int) -> Dict:
        """Calculate completion metrics for a specific phase"""
        phase = self.phases[phase_num]
        phase_deliverables = [
            self.deliverables[d_id] 
            for d_id in phase.deliverables 
            if d_id in self.deliverables
        ]
        
        if not phase_deliverables:
            return {"completion_pct": 0, "complete": 0, "total": 0}
        
        total = len(phase_deliverables)
        complete = sum(1 for d in phase_deliverables if d.status == Status.COMPLETE)
        in_progress = sum(1 for d in phase_deliverables if d.status == Status.IN_PROGRESS)
        review = sum(1 for d in phase_deliverables if d.status == Status.REVIEW)
        blocked = sum(1 for d in phase_deliverables if d.is_blocked)
        
        completion_pct = sum(d.completion_pct for d in phase_deliverables) / total
        
        return {
            "phase": phase_num,
            "name": phase.name,
            "completion_pct": round(completion_pct, 1),
            "complete": complete,
            "in_progress": in_progress,
            "review": review,
            "blocked": blocked,
            "total": total,
            "start_date": phase.start_date.isoformat() if phase.start_date else None,
            "end_date": phase.end_date.isoformat() if phase.end_date else None,
            "go_criteria": phase.go_criteria
        }
    
    def calculate_component_health(self, component_id: str) -> Dict:
        """Calculate health metrics for a component"""
        component = self.components[component_id]
        comp_deliverables = [
            self.deliverables[d_id]
            for d_id in component.deliverables
            if d_id in self.deliverables
        ]
        
        if not comp_deliverables:
            return {"health_score": 0, "status": "no_deliverables"}
        
        total = len(comp_deliverables)
        completion_pct = sum(d.completion_pct for d in comp_deliverables) / total
        blocked_count = sum(1 for d in comp_deliverables if d.is_blocked)
        critical_incomplete = sum(
            1 for d in comp_deliverables 
            if d.priority == Priority.CRITICAL and d.status != Status.COMPLETE
        )
        
        # Health score factors
        health_score = completion_pct
        if blocked_count > 0:
            health_score -= (blocked_count / total) * 20
        if critical_incomplete > 0:
            health_score -= (critical_incomplete / total) * 15
        
        health_score = max(0, min(100, health_score))
        
        # Determine status
        if completion_pct == 100:
            status = "complete"
        elif blocked_count > total / 2:
            status = "critical"
        elif blocked_count > 0 or critical_incomplete > 0:
            status = "at_risk"
        elif completion_pct > 50:
            status = "on_track"
        else:
            status = "early_stage"
        
        return {
            "component_id": component_id,
            "name": component.name,
            "type": component.type.value,
            "health_score": round(health_score, 1),
            "completion_pct": round(completion_pct, 1),
            "status": status,
            "spec_complete": component.spec_complete,
            "code_complete": component.code_complete,
            "tests_complete": component.tests_complete,
            "docs_complete": component.docs_complete,
            "blocked_count": blocked_count,
            "critical_incomplete": critical_incomplete,
            "total_deliverables": total
        }
    
    # -------------------------------------------------------------------------
    # ANALYSIS FUNCTIONS
    # -------------------------------------------------------------------------
    
    def get_blockers(self) -> List[Dict]:
        """Identify all blocked items and their blockers"""
        blockers = []
        for d in self.deliverables.values():
            if d.is_blocked:
                blockers.append({
                    "id": d.id,
                    "name": d.name,
                    "priority": d.priority.value,
                    "blockers": d.blockers,
                    "missing_dependencies": [
                        dep for dep in d.dependencies
                        if dep in self.deliverables and 
                        self.deliverables[dep].status != Status.COMPLETE
                    ]
                })
        return blockers
    
    def get_critical_path(self) -> List[Dict]:
        """Identify critical path items not yet complete"""
        critical = []
        for d in self.deliverables.values():
            if d.priority == Priority.CRITICAL and d.status != Status.COMPLETE:
                deps_complete = all(
                    self.deliverables[dep].status == Status.COMPLETE
                    for dep in d.dependencies
                    if dep in self.deliverables
                )
                critical.append({
                    "id": d.id,
                    "name": d.name,
                    "status": d.status.value,
                    "phase": d.phase,
                    "estimated_hours": d.estimated_hours,
                    "dependencies_met": deps_complete,
                    "can_start": deps_complete and d.status == Status.NOT_STARTED
                })
        
        # Sort by phase, then by whether it can start
        critical.sort(key=lambda x: (x["phase"], not x["can_start"]))
        return critical
    
    def get_ready_to_start(self) -> List[Dict]:
        """Get items ready to start (dependencies met)"""
        ready = []
        for d in self.deliverables.values():
            if d.status == Status.NOT_STARTED:
                deps_met = all(
                    self.deliverables[dep].status == Status.COMPLETE
                    for dep in d.dependencies
                    if dep in self.deliverables
                )
                if deps_met:
                    ready.append({
                        "id": d.id,
                        "name": d.name,
                        "priority": d.priority.value,
                        "phase": d.phase,
                        "estimated_hours": d.estimated_hours,
                        "component": d.component.value
                    })
        
        # Sort by priority (critical first), then phase
        priority_order = {
            Priority.CRITICAL: 0,
            Priority.HIGH: 1,
            Priority.MEDIUM: 2,
            Priority.LOW: 3
        }
        ready.sort(key=lambda x: (priority_order[Priority(x["priority"])], x["phase"]))
        return ready
    
    def calculate_velocity(self) -> Dict:
        """Calculate effort metrics"""
        total_estimated = sum(d.estimated_hours for d in self.deliverables.values())
        total_actual = sum(d.actual_hours for d in self.deliverables.values())
        completed_estimated = sum(
            d.estimated_hours for d in self.deliverables.values()
            if d.status == Status.COMPLETE
        )
        remaining_estimated = total_estimated - completed_estimated
        
        return {
            "total_estimated_hours": total_estimated,
            "completed_estimated_hours": completed_estimated,
            "remaining_estimated_hours": remaining_estimated,
            "total_actual_hours": total_actual,
            "efficiency_ratio": round(completed_estimated / total_actual, 2) if total_actual > 0 else 0,
            "estimated_weeks_remaining": round(remaining_estimated / 40, 1)  # 40hr work week
        }
    
    def get_risk_assessment(self) -> Dict:
        """Comprehensive risk assessment"""
        blockers = self.get_blockers()
        critical_path = self.get_critical_path()
        velocity = self.calculate_velocity()
        
        # Risk factors
        risks = []
        
        # Blocked items risk
        if len(blockers) > 0:
            risks.append({
                "category": "blockers",
                "severity": "high" if len(blockers) > 3 else "medium",
                "description": f"{len(blockers)} items currently blocked",
                "mitigation": "Resolve blocking dependencies or reassign work"
            })
        
        # Critical path risk
        critical_not_started = sum(1 for c in critical_path if c["status"] == "not_started")
        if critical_not_started > 5:
            risks.append({
                "category": "critical_path",
                "severity": "high",
                "description": f"{critical_not_started} critical items not started",
                "mitigation": "Prioritize critical path items immediately"
            })
        
        # Schedule risk
        if velocity["estimated_weeks_remaining"] > 6:
            risks.append({
                "category": "schedule",
                "severity": "medium",
                "description": f"{velocity['estimated_weeks_remaining']} weeks of work remaining",
                "mitigation": "Consider adding resources or reducing scope"
            })
        
        # Dependency chain risk
        max_dep_depth = self._calculate_max_dependency_depth()
        if max_dep_depth > 4:
            risks.append({
                "category": "dependencies",
                "severity": "medium",
                "description": f"Deep dependency chain ({max_dep_depth} levels)",
                "mitigation": "Parallelize work where possible"
            })
        
        overall_risk = "high" if any(r["severity"] == "high" for r in risks) else \
                       "medium" if any(r["severity"] == "medium" for r in risks) else "low"
        
        return {
            "overall_risk_level": overall_risk,
            "risk_count": len(risks),
            "risks": risks
        }
    
    def _calculate_max_dependency_depth(self) -> int:
        """Calculate the maximum dependency chain depth"""
        def get_depth(d_id: str, visited: set) -> int:
            if d_id in visited or d_id not in self.deliverables:
                return 0
            visited.add(d_id)
            d = self.deliverables[d_id]
            if not d.dependencies:
                return 1
            return 1 + max(get_depth(dep, visited.copy()) for dep in d.dependencies)
        
        return max(get_depth(d_id, set()) for d_id in self.deliverables.keys())
    
    # -------------------------------------------------------------------------
    # REPORT GENERATION
    # -------------------------------------------------------------------------
    
    def generate_full_report(self) -> Dict:
        """Generate comprehensive assessment report"""
        
        # Phase summaries
        phase_summaries = [
            self.calculate_phase_completion(phase_num)
            for phase_num in sorted(self.phases.keys())
        ]
        
        # Component health
        component_health = [
            self.calculate_component_health(comp_id)
            for comp_id in self.components.keys()
        ]
        
        # Sort components by health score (worst first)
        component_health.sort(key=lambda x: x["health_score"])
        
        # Summary by type
        type_summary = defaultdict(lambda: {"count": 0, "complete": 0, "completion_pct": 0})
        for d in self.deliverables.values():
            type_summary[d.component.value]["count"] += 1
            if d.status == Status.COMPLETE:
                type_summary[d.component.value]["complete"] += 1
        
        for t in type_summary:
            if type_summary[t]["count"] > 0:
                type_summary[t]["completion_pct"] = round(
                    (type_summary[t]["complete"] / type_summary[t]["count"]) * 100, 1
                )
        
        # Status distribution
        status_distribution = defaultdict(int)
        for d in self.deliverables.values():
            status_distribution[d.status.value] += 1
        
        return {
            "metadata": {
                "assessment_date": self.assessment_date.isoformat(),
                "total_deliverables": len(self.deliverables),
                "total_components": len(self.components),
                "total_phases": len(self.phases)
            },
            "summary": {
                "overall_completion_pct": round(self.calculate_overall_completion(), 1),
                "status_distribution": dict(status_distribution),
                "type_summary": dict(type_summary)
            },
            "phases": phase_summaries,
            "components": component_health,
            "velocity": self.calculate_velocity(),
            "risk_assessment": self.get_risk_assessment(),
            "critical_path": self.get_critical_path()[:10],  # Top 10
            "blockers": self.get_blockers(),
            "ready_to_start": self.get_ready_to_start()[:10],  # Top 10
            "recommendations": self._generate_recommendations()
        }
    
    def _generate_recommendations(self) -> List[str]:
        """Generate actionable recommendations"""
        recommendations = []
        
        overall = self.calculate_overall_completion()
        blockers = self.get_blockers()
        ready = self.get_ready_to_start()
        critical = self.get_critical_path()
        
        # Blocker recommendations
        if blockers:
            recommendations.append(
                f"🚫 RESOLVE BLOCKERS: {len(blockers)} items are blocked. "
                f"Focus on unblocking: {', '.join(b['id'] for b in blockers[:3])}"
            )
        
        # Critical path recommendations
        can_start_critical = [c for c in critical if c["can_start"]]
        if can_start_critical:
            recommendations.append(
                f"⚠️ CRITICAL PATH: {len(can_start_critical)} critical items can start now. "
                f"Prioritize: {', '.join(c['id'] for c in can_start_critical[:3])}"
            )
        
        # Ready to start recommendations
        if ready:
            high_priority_ready = [r for r in ready if r["priority"] in ["critical", "high"]]
            if high_priority_ready:
                recommendations.append(
                    f"✅ READY TO START: {len(high_priority_ready)} high-priority items ready. "
                    f"Next: {', '.join(r['id'] for r in high_priority_ready[:3])}"
                )
        
        # Phase recommendations
        for phase_num in sorted(self.phases.keys()):
            phase_data = self.calculate_phase_completion(phase_num)
            if phase_data["completion_pct"] < 100 and phase_data["completion_pct"] > 0:
                if phase_data["blocked"] > 0:
                    recommendations.append(
                        f"📍 PHASE {phase_num} ({phase_data['name']}): "
                        f"{phase_data['blocked']} blocked items preventing progress"
                    )
                break  # Only show current phase
        
        # Spec vs Code gap
        spec_complete_count = sum(1 for c in self.components.values() if c.spec_complete)
        code_complete_count = sum(1 for c in self.components.values() if c.code_complete)
        if spec_complete_count > code_complete_count + 3:
            recommendations.append(
                f"📝 SPEC-CODE GAP: {spec_complete_count} components have specs, "
                f"but only {code_complete_count} have code. Focus on implementation."
            )
        
        return recommendations
    
    # -------------------------------------------------------------------------
    # OUTPUT FORMATTERS
    # -------------------------------------------------------------------------
    
    def print_text_report(self):
        """Print human-readable text report"""
        report = self.generate_full_report()
        
        print("\n" + "=" * 80)
        print("  CITADEL-NEXUS PROGRESSION ASSESSMENT")
        print("=" * 80)
        print(f"  Assessment Date: {report['metadata']['assessment_date'][:10]}")
        print(f"  Total Deliverables: {report['metadata']['total_deliverables']}")
        print("=" * 80)
        
        # Overall Summary
        print("\n📊 OVERALL PROGRESS")
        print("-" * 40)
        overall = report['summary']['overall_completion_pct']
        bar_filled = int(overall / 5)
        bar_empty = 20 - bar_filled
        print(f"  Completion: [{'█' * bar_filled}{'░' * bar_empty}] {overall}%")
        
        print("\n  Status Distribution:")
        for status, count in report['summary']['status_distribution'].items():
            emoji = {"complete": "✅", "in_progress": "🔄", "review": "👀", 
                    "blocked": "🚫", "not_started": "⬜"}.get(status, "❓")
            print(f"    {emoji} {status}: {count}")
        
        # Phase Progress
        print("\n📅 PHASE PROGRESS")
        print("-" * 40)
        for phase in report['phases']:
            pct = phase['completion_pct']
            bar_filled = int(pct / 5)
            bar_empty = 20 - bar_filled
            status_emoji = "✅" if pct == 100 else "🔄" if pct > 0 else "⬜"
            print(f"  {status_emoji} Phase {phase['phase']}: {phase['name']}")
            print(f"     [{'█' * bar_filled}{'░' * bar_empty}] {pct}%")
            print(f"     {phase['complete']}/{phase['total']} complete | {phase['blocked']} blocked")
        
        # Component Health
        print("\n🏥 COMPONENT HEALTH (sorted by risk)")
        print("-" * 40)
        for comp in report['components'][:10]:
            emoji = {"complete": "✅", "on_track": "🟢", "early_stage": "🟡",
                    "at_risk": "🟠", "critical": "🔴"}.get(comp['status'], "❓")
            spec = "📝" if comp['spec_complete'] else "  "
            code = "💻" if comp['code_complete'] else "  "
            print(f"  {emoji} {comp['name'][:30]:<30} {comp['health_score']:>5.1f}% {spec}{code}")
        
        # Velocity
        print("\n⚡ VELOCITY METRICS")
        print("-" * 40)
        v = report['velocity']
        print(f"  Total Estimated Hours:     {v['total_estimated_hours']}")
        print(f"  Completed Hours:           {v['completed_estimated_hours']}")
        print(f"  Remaining Hours:           {v['remaining_estimated_hours']}")
        print(f"  Estimated Weeks Remaining: {v['estimated_weeks_remaining']}")
        
        # Risk Assessment
        print("\n⚠️ RISK ASSESSMENT")
        print("-" * 40)
        risk = report['risk_assessment']
        risk_emoji = {"high": "🔴", "medium": "🟠", "low": "🟢"}.get(risk['overall_risk_level'], "❓")
        print(f"  Overall Risk Level: {risk_emoji} {risk['overall_risk_level'].upper()}")
        for r in risk['risks']:
            print(f"    • [{r['severity'].upper()}] {r['description']}")
        
        # Critical Path
        print("\n🎯 CRITICAL PATH (Top 5)")
        print("-" * 40)
        for item in report['critical_path'][:5]:
            status_emoji = "✅" if item['status'] == 'complete' else \
                          "🟢" if item['can_start'] else "⬜"
            print(f"  {status_emoji} {item['id']}: {item['name'][:40]}")
            print(f"     Phase {item['phase']} | {item['estimated_hours']}h | Can start: {item['can_start']}")
        
        # Ready to Start
        print("\n🚀 READY TO START (Top 5)")
        print("-" * 40)
        for item in report['ready_to_start'][:5]:
            priority_emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(item['priority'], "❓")
            print(f"  {priority_emoji} {item['id']}: {item['name'][:40]}")
            print(f"     Phase {item['phase']} | {item['estimated_hours']}h | {item['component']}")
        
        # Blockers
        if report['blockers']:
            print("\n🚫 BLOCKERS")
            print("-" * 40)
            for blocker in report['blockers']:
                print(f"  • {blocker['id']}: {blocker['name']}")
                if blocker['missing_dependencies']:
                    print(f"    Waiting on: {', '.join(blocker['missing_dependencies'])}")
        
        # Recommendations
        print("\n💡 RECOMMENDATIONS")
        print("-" * 40)
        for rec in report['recommendations']:
            print(f"  {rec}")
        
        print("\n" + "=" * 80)
        print("  END OF ASSESSMENT")
        print("=" * 80 + "\n")
    
    def to_json(self) -> str:
        """Export report as JSON"""
        report = self.generate_full_report()
        return json.dumps(report, indent=2, default=str)


# =============================================================================
# INTERACTIVE STATUS UPDATER
# =============================================================================

class StatusUpdater:
    """
    Interactive tool for updating deliverable statuses.
    Can be used to mark items complete, blocked, etc.
    """
    
    def __init__(self, assessment: ProgressionAssessment):
        self.assessment = assessment
    
    def update_status(self, deliverable_id: str, new_status: Status, 
                     actual_hours: float = None, notes: str = None):
        """Update a deliverable's status"""
        if deliverable_id not in self.assessment.deliverables:
            raise ValueError(f"Unknown deliverable: {deliverable_id}")
        
        d = self.assessment.deliverables[deliverable_id]
        d.status = new_status
        if actual_hours is not None:
            d.actual_hours = actual_hours
        if notes:
            d.notes = notes
        
        return {
            "id": deliverable_id,
            "name": d.name,
            "new_status": new_status.value,
            "completion_pct": d.completion_pct
        }
    
    def mark_complete(self, deliverable_id: str, actual_hours: float = None):
        """Mark a deliverable as complete"""
        return self.update_status(deliverable_id, Status.COMPLETE, actual_hours)
    
    def mark_in_progress(self, deliverable_id: str):
        """Mark a deliverable as in progress"""
        return self.update_status(deliverable_id, Status.IN_PROGRESS)
    
    def mark_blocked(self, deliverable_id: str, blockers: List[str]):
        """Mark a deliverable as blocked"""
        if deliverable_id in self.assessment.deliverables:
            self.assessment.deliverables[deliverable_id].blockers = blockers
        return self.update_status(deliverable_id, Status.BLOCKED)
    
    def bulk_update(self, updates: List[Dict]):
        """
        Bulk update multiple deliverables.
        Each update dict should have: {id, status, actual_hours?, notes?}
        """
        results = []
        for update in updates:
            result = self.update_status(
                update["id"],
                Status(update["status"]),
                update.get("actual_hours"),
                update.get("notes")
            )
            results.append(result)
        return results


# =============================================================================
# MAIN EXECUTION
# =============================================================================

def main():
    """Main entry point"""
    import sys
    
    # Initialize assessment
    assessment = ProgressionAssessment()
    
    # Check for output format argument
    output_format = "text"
    if len(sys.argv) > 1:
        if sys.argv[1] in ["--json", "-j"]:
            output_format = "json"
        elif sys.argv[1] in ["--help", "-h"]:
            print("Usage: python citadel_progression_assessment.py [--json|-j]")
            print("  --json, -j  Output as JSON")
            print("  --help, -h  Show this help")
            return
    
    if output_format == "json":
        print(assessment.to_json())
    else:
        assessment.print_text_report()


if __name__ == "__main__":
    main()