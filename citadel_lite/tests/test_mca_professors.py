"""Tests for MCA professors — Mirror, Oracle, Government (mock Bedrock)."""

import pytest
from unittest.mock import MagicMock, patch

from src.mca.professors.prof_mirror import ProfMirror
from src.mca.professors.prof_oracle import ProfOracle
from src.mca.professors.prof_government import ProfGovernment


# ── Mock Bedrock helper ────────────────────────────────────────────────────
def _make_mock_bedrock(return_text: str):
    """Create a mock BedrockProfessorClient that returns fixed text."""
    mock = MagicMock()
    mock.is_available.return_value = True
    resp = MagicMock()
    resp.success = True
    resp.content = return_text
    resp.input_tokens = 100
    resp.output_tokens = 200
    resp.latency_ms = 500.0
    mock.invoke.return_value = resp
    return mock


# ── JSON sample outputs (new format) ─────────────────────────────────────
import json as _json

MIRROR_JSON_OUTPUT = _json.dumps({
    "code_patterns": [
        "Singleton pattern: Used in 5 modules for client initialization",
        "Repository pattern: Data access layer follows repository pattern",
    ],
    "anti_patterns": [
        "God class: professor_base.py is 73KB with too many responsibilities",
    ],
    "plan_coverage": {
        "Phase 19 A2A": {"status": "COVERED", "notes": "Full implementation"},
        "Phase 25 ZES Agent": {"status": "MISSING", "notes": "Not yet started"},
        "Phase 27 TradeBuilder": {"status": "PARTIAL", "notes": "Only API stubs"},
    },
    "key_findings": [
        "Test coverage is low for MCA modules",
        "No integration tests for Bedrock pipeline",
    ],
    "recommendations": [
        "Split professor_base.py into smaller focused classes",
        "Add integration test suite for Bedrock",
    ],
})

ORACLE_JSON_OUTPUT = _json.dumps({
    "health_status": {
        "overall": "YELLOW",
        "code_quality": {"score": 7, "notes": "Good structure but some god classes"},
        "test_coverage": {"score": 4, "notes": "Below threshold for production"},
        "doc_completeness": {"score": 6, "notes": "Roadmap is detailed but API docs missing"},
        "deployment_readiness": {"score": 3, "notes": "No CI/CD pipeline configured"},
    },
    "product_doc_strength": {
        "plan_clarity": {"score": 8, "notes": "Clear phased roadmap"},
        "roadmap_alignment": {"score": 7, "notes": "Good alignment with codebase"},
        "feature_spec_depth": {"score": 5, "notes": "Some features lack detailed specs"},
        "sales_readiness": {"score": 4, "notes": "Missing customer-facing documentation"},
    },
    "top_3_improvements": [
        {"title": "CI/CD Pipeline", "description": "Set up automated testing and deployment"},
        {"title": "API Documentation", "description": "Generate OpenAPI specs from FastAPI endpoints"},
        {"title": "Test Coverage", "description": "Increase to 80% minimum for core modules"},
    ],
    "tier_coverage": [
        "Scout: 60% — Basic features covered",
        "Operator: 30% — Advanced features need work",
        "ZES Agent: 10% — Minimal implementation",
    ],
    "key_findings": [
        "Revenue readiness blocked by deployment gaps",
        "Documentation strength below sales threshold",
    ],
})

GOVERNMENT_JSON_OUTPUT = _json.dumps({
    "approved": [
        {"id": "EP-CODE-abc12345", "reason": "Low risk code pattern fix with test plan"},
        {"id": "EP-RAG-def67890", "reason": "Documentation improvement is low risk"},
    ],
    "rejected": [
        {"id": "EP-CODE-ghi11111", "reason": "Missing test plan for security-critical change"},
    ],
    "risk_assessment": [
        {"id": "EP-CODE-abc12345", "level": "LOW", "description": "Simple refactoring"},
        {"id": "EP-RAG-def67890", "level": "LOW", "description": "Documentation only"},
        {"id": "EP-CODE-ghi11111", "level": "HIGH", "description": "Security module without tests"},
    ],
    "conflict_arbitration": [
        {"id": "CONFLICT-001", "resolution": "Resolve in favor of Phase 25 priority"},
    ],
    "policy_notes": [
        "All approved proposals have corresponding test plans",
        "Security review required for EP-CODE-ghi11111 before re-submission",
    ],
})

# ── Sample LLM outputs ────────────────────────────────────────────────────
MIRROR_OUTPUT = """\
### Code Patterns
- Singleton pattern: Used in 5 modules for client initialization
- Repository pattern: Data access layer follows repository pattern

### Anti-Patterns
- God class: professor_base.py is 73KB with too many responsibilities

### Plan Coverage
- Phase 19 A2A: COVERED — Full implementation
- Phase 25 ZES Agent: MISSING — Not yet started
- Phase 27 TradeBuilder: PARTIAL — Only API stubs

### Key Findings
- Test coverage is low for MCA modules
- No integration tests for Bedrock pipeline

### Recommendations
- Split professor_base.py into smaller focused classes
- Add integration test suite for Bedrock
"""

ORACLE_OUTPUT = """\
### Health Status
- overall: YELLOW
- code_quality: 7 — Good structure but some god classes
- test_coverage: 4 — Below threshold for production
- doc_completeness: 6 — Roadmap is detailed but API docs missing
- deployment_readiness: 3 — No CI/CD pipeline configured

### Product Doc Strength
- plan_clarity: 8 — Clear phased roadmap
- roadmap_alignment: 7 — Good alignment with codebase
- feature_spec_depth: 5 — Some features lack detailed specs
- sales_readiness: 4 — Missing customer-facing documentation

### Top 3 Improvements
1. CI/CD Pipeline: Set up automated testing and deployment
2. API Documentation: Generate OpenAPI specs from FastAPI endpoints
3. Test Coverage: Increase to 80% minimum for core modules

### Tier Coverage
- Scout: 60% — Basic features covered
- Operator: 30% — Advanced features need work
- ZES Agent: 10% — Minimal implementation

### Key Findings
- Revenue readiness blocked by deployment gaps
- Documentation strength below sales threshold
"""

GOVERNMENT_OUTPUT = """\
### Approved
- EP-CODE-abc12345: Low risk code pattern fix with test plan
- EP-RAG-def67890: Documentation improvement is low risk

### Rejected
- EP-CODE-ghi11111: Missing test plan for security-critical change

### Risk Assessment
- EP-CODE-abc12345: LOW — Simple refactoring
- EP-RAG-def67890: LOW — Documentation only
- EP-CODE-ghi11111: HIGH — Security module without tests

### Conflict Arbitration
- CONFLICT-001: Resolve in favor of Phase 25 priority

### Policy Notes
- All approved proposals have corresponding test plans
- Security review required for EP-CODE-ghi11111 before re-submission

### ENUM Tags
- CAPS_COMPLIANCE_CHECK
- CAPS_APPROVAL_GRANTED
"""


# ── CGRF Metadata ──────────────────────────────────────────────────────────
class TestCGRFMetadata:
    def test_mirror_metadata(self):
        from src.mca.professors import prof_mirror
        assert prof_mirror._MODULE_NAME == "prof_mirror"
        assert prof_mirror._CGRF_TIER == 1

    def test_oracle_metadata(self):
        from src.mca.professors import prof_oracle
        assert prof_oracle._MODULE_NAME == "prof_oracle"
        assert prof_oracle._CGRF_TIER == 1

    def test_government_metadata(self):
        from src.mca.professors import prof_government
        assert prof_government._MODULE_NAME == "prof_government"
        assert prof_government._CGRF_TIER == 1

    def test_bedrock_adapter_metadata(self):
        from src.mca.professors import bedrock_adapter
        assert bedrock_adapter._MODULE_NAME == "bedrock_adapter"
        assert bedrock_adapter._CGRF_TIER == 1


# ── ProfMirror tests ──────────────────────────────────────────────────────
class TestProfMirror:
    def test_init(self):
        mock = _make_mock_bedrock("")
        prof = ProfMirror(bedrock_client=mock)
        assert prof.name == "mirror_mca"

    def test_analyze_with_mock(self):
        mock = _make_mock_bedrock(MIRROR_OUTPUT)
        prof = ProfMirror(bedrock_client=mock)
        result = prof.analyze({"code_summary": {"files": 100}})

        assert len(result["code_patterns"]) == 2
        assert len(result["anti_patterns"]) == 1
        assert "Phase 25 ZES Agent" in result["plan_coverage"]
        assert result["plan_coverage"]["Phase 25 ZES Agent"]["status"] == "MISSING"
        assert len(result["key_findings"]) == 2
        assert len(result["recommendations"]) == 2
        assert result["raw_output"] == MIRROR_OUTPUT

    def test_analyze_none_response(self):
        mock = _make_mock_bedrock("")
        mock.is_available.return_value = False
        prof = ProfMirror(bedrock_client=mock)
        result = prof.analyze({"test": True})
        assert result["code_patterns"] == []
        assert result["plan_coverage"] == {}

    def test_extract_list_section(self):
        items = ProfMirror._extract_list_section("Key Findings", MIRROR_OUTPUT)
        assert len(items) == 2
        assert "Test coverage" in items[0]

    def test_extract_coverage_section(self):
        coverage = ProfMirror._extract_coverage_section(MIRROR_OUTPUT)
        assert "Phase 19 A2A" in coverage
        assert coverage["Phase 19 A2A"]["status"] == "COVERED"
        assert coverage["Phase 27 TradeBuilder"]["status"] == "PARTIAL"


# ── ProfOracle tests ──────────────────────────────────────────────────────
class TestProfOracle:
    def test_init(self):
        mock = _make_mock_bedrock("")
        prof = ProfOracle(bedrock_client=mock)
        assert prof.name == "oracle_mca"

    def test_analyze_with_mock(self):
        mock = _make_mock_bedrock(ORACLE_OUTPUT)
        prof = ProfOracle(bedrock_client=mock)
        result = prof.analyze({"plan_summary": {"phases": 27}})

        assert result["health_status"]["overall"] == "YELLOW"
        assert result["health_status"]["code_quality"]["score"] == 7.0
        assert result["health_status"]["deployment_readiness"]["score"] == 3.0
        assert len(result["top_3_improvements"]) == 3
        assert result["top_3_improvements"][0]["title"] == "CI/CD Pipeline"
        assert len(result["tier_coverage"]) == 3

    def test_extract_health_status(self):
        health = ProfOracle._extract_health_status(ORACLE_OUTPUT)
        assert health["overall"] == "YELLOW"
        assert health["test_coverage"]["score"] == 4.0

    def test_extract_numbered_list(self):
        items = ProfOracle._extract_numbered_list("Top 3 Improvements", ORACLE_OUTPUT)
        assert len(items) == 3
        assert items[1]["title"] == "API Documentation"

    def test_extract_scored_section(self):
        scores = ProfOracle._extract_scored_section("Product Doc Strength", ORACLE_OUTPUT)
        assert scores["plan_clarity"]["score"] == 8.0
        assert scores["sales_readiness"]["score"] == 4.0


# ── ProfGovernment tests ──────────────────────────────────────────────────
class TestProfGovernment:
    def test_init(self):
        mock = _make_mock_bedrock("")
        prof = ProfGovernment(bedrock_client=mock)
        assert prof.name == "government_mca"

    def test_analyze_with_mock(self):
        mock = _make_mock_bedrock(GOVERNMENT_OUTPUT)
        prof = ProfGovernment(bedrock_client=mock)
        result = prof.analyze(
            {"summary": "test"},
            proposals=[{"id": "EP-CODE-abc12345", "title": "Fix"}],
        )

        assert len(result["approved"]) == 2
        assert result["approved"][0]["id"] == "EP-CODE-abc12345"
        assert len(result["rejected"]) == 1
        assert len(result["risk_assessment"]) == 3
        assert result["risk_assessment"][2]["level"] == "HIGH"
        assert len(result["policy_notes"]) == 2
        assert len(result["enum_tags"]) > 0

    def test_extract_risk_assessment(self):
        risks = ProfGovernment._extract_risk_assessment(GOVERNMENT_OUTPUT)
        assert len(risks) == 3
        assert risks[0]["level"] == "LOW"
        assert risks[2]["level"] == "HIGH"

    def test_extract_enum_tags(self):
        tags = ProfGovernment.extract_enum_tags("compliance check approved security review")
        assert "CAPS_COMPLIANCE_CHECK" in tags
        assert "CAPS_SECURITY_REVIEW" in tags

    def test_analyze_with_conflicts(self):
        mock = _make_mock_bedrock(GOVERNMENT_OUTPUT)
        prof = ProfGovernment(bedrock_client=mock)
        result = prof.analyze(
            {"summary": "test"},
            conflicts=[{"id": "CONFLICT-001", "description": "Phase priority"}],
        )
        assert len(result["conflict_arbitration"]) == 1

    def test_empty_result_on_none(self):
        mock = _make_mock_bedrock("")
        mock.is_available.return_value = False
        prof = ProfGovernment(bedrock_client=mock)
        result = prof.analyze({"test": True})
        assert result["approved"] == []
        assert result["rejected"] == []


# ── JSON format tests ──────────────────────────────────────────────────────
class TestProfMirrorJSON:
    def test_analyze_json_output(self):
        mock = _make_mock_bedrock(MIRROR_JSON_OUTPUT)
        prof = ProfMirror(bedrock_client=mock)
        result = prof.analyze({"code_summary": {"files": 100}})

        assert len(result["code_patterns"]) == 2
        assert len(result["anti_patterns"]) == 1
        assert "Phase 25 ZES Agent" in result["plan_coverage"]
        assert result["plan_coverage"]["Phase 25 ZES Agent"]["status"] == "MISSING"
        assert len(result["key_findings"]) == 2
        assert len(result["recommendations"]) == 2
        assert result["raw_output"] == MIRROR_JSON_OUTPUT

    def test_analyze_fenced_json(self):
        fenced = f"```json\n{MIRROR_JSON_OUTPUT}\n```"
        mock = _make_mock_bedrock(fenced)
        prof = ProfMirror(bedrock_client=mock)
        result = prof.analyze({})
        assert len(result["code_patterns"]) == 2

    def test_analyze_embedded_json(self):
        wrapped = f"Here is the analysis:\n{MIRROR_JSON_OUTPUT}\nEnd."
        mock = _make_mock_bedrock(wrapped)
        prof = ProfMirror(bedrock_client=mock)
        result = prof.analyze({})
        assert len(result["code_patterns"]) == 2


class TestProfOracleJSON:
    def test_analyze_json_output(self):
        mock = _make_mock_bedrock(ORACLE_JSON_OUTPUT)
        prof = ProfOracle(bedrock_client=mock)
        result = prof.analyze({"plan_summary": {"phases": 27}})

        assert result["health_status"]["overall"] == "YELLOW"
        assert result["health_status"]["code_quality"]["score"] == 7
        assert result["health_status"]["deployment_readiness"]["score"] == 3
        assert len(result["top_3_improvements"]) == 3
        assert result["top_3_improvements"][0]["title"] == "CI/CD Pipeline"
        assert len(result["tier_coverage"]) == 3
        assert result["raw_output"] == ORACLE_JSON_OUTPUT

    def test_analyze_fenced_json(self):
        fenced = f"```json\n{ORACLE_JSON_OUTPUT}\n```"
        mock = _make_mock_bedrock(fenced)
        prof = ProfOracle(bedrock_client=mock)
        result = prof.analyze({})
        assert result["health_status"]["overall"] == "YELLOW"


class TestProfGovernmentJSON:
    def test_analyze_json_output(self):
        mock = _make_mock_bedrock(GOVERNMENT_JSON_OUTPUT)
        prof = ProfGovernment(bedrock_client=mock)
        result = prof.analyze(
            {"summary": "test"},
            proposals=[{"id": "EP-CODE-abc12345", "title": "Fix"}],
        )

        assert len(result["approved"]) == 2
        assert result["approved"][0]["id"] == "EP-CODE-abc12345"
        assert result["approved"][0]["reason"] == "Low risk code pattern fix with test plan"
        assert len(result["rejected"]) == 1
        assert result["rejected"][0]["id"] == "EP-CODE-ghi11111"
        assert len(result["risk_assessment"]) == 3
        assert result["risk_assessment"][2]["level"] == "HIGH"
        assert len(result["conflict_arbitration"]) == 1
        assert result["conflict_arbitration"][0]["id"] == "CONFLICT-001"
        assert len(result["policy_notes"]) == 2

    def test_analyze_fenced_json(self):
        fenced = f"```json\n{GOVERNMENT_JSON_OUTPUT}\n```"
        mock = _make_mock_bedrock(fenced)
        prof = ProfGovernment(bedrock_client=mock)
        result = prof.analyze({})
        assert len(result["approved"]) == 2

    def test_enum_tags_from_json_output(self):
        mock = _make_mock_bedrock(GOVERNMENT_JSON_OUTPUT)
        prof = ProfGovernment(bedrock_client=mock)
        result = prof.analyze({})
        # enum_tags use keyword matching on raw_output — still works with JSON
        assert len(result["enum_tags"]) > 0
