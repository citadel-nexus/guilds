# CGRF v3.0 CLI - Governance & Validation Tools

CGRF (Complete Governance & Reflex Framework) CLI provides validation and compliance checking for autonomous system modules against tiered governance requirements.

## Installation

No installation required. Run directly from the project root:

```bash
python cgrf.py <command> [options]
```

Or as a Python module:

```bash
python -m src.cgrf <command> [options]
```

## CGRF Tier System

| Tier | Name             | Test Coverage | Implementation Time | Requirements                            |
| ---- | ---------------- | ------------- | ------------------- | --------------------------------------- |
| 0    | Experimental     | 0%            | <5 min              | Basic structure, parsing                |
| 1    | Development      | 50%           | ~2 hours            | Docstrings, CGRF metadata, unit tests   |
| 2    | Production       | 80%           | 1-2 days            | Integration tests, policy compliance    |
| 3    | Mission-Critical | 95%           | ~1 week             | E2E tests, audit trail, full governance |

## Commands

### `validate` - Validate a single module

Validates a Python module against CGRF tier requirements.

```bash
python cgrf.py validate --module <path> --tier <0-3>
```

**Examples:**

```bash
# Validate sentinel_v2 against Tier 1 (Development)
python cgrf.py validate --module src/agents/sentinel_v2.py --tier 1

# Validate guardian_v3 against Tier 2 (Production)
python cgrf.py validate --module src/agents/guardian_v3.py --tier 2

# Validate orchestrator_v3 against Tier 0 (Experimental)
python cgrf.py validate --module src/orchestrator_v3.py --tier 0
```

**Output:**

- Detailed validation report with color-coded results
- Pass/Fail status for each requirement
- Warnings for tier mismatches or optional requirements
- Final compliance status

**Exit codes:**

- `0`: Module is compliant
- `1`: Module is not compliant or validation error

### `tier-check` - Check multiple modules

Quickly check multiple modules against a tier (summary output).

```bash
python cgrf.py tier-check <module1> <module2> ... --tier <0-3>
```

**Examples:**

```bash
# Check all 4 main agents against Tier 1
python cgrf.py tier-check \
  src/agents/sentinel_v2.py \
  src/agents/sherlock_v3.py \
  src/agents/fixer_v3.py \
  src/agents/guardian_v3.py \
  --tier 1

# Check orchestrators against Tier 0
python cgrf.py tier-check src/orchestrator_v*.py --tier 0
```

**Output:**

- One-line summary per module (PASS/FAIL)
- Failed checks listed for non-compliant modules

**Exit codes:**

- `0`: All modules compliant
- `1`: One or more modules not compliant

### `report` - Generate compliance report

Scan all modules and generate a compliance report.

```bash
python cgrf.py report --tier <0-3>
```

**Examples:**

```bash
# Generate Tier 1 compliance report for all agents
python cgrf.py report --tier 1

# Generate Tier 2 compliance report
python cgrf.py report --tier 2
```

**Output:**

- List of all discovered modules with PASS/FAIL status
- Total compliance count

**Scanned directories:**

- `src/agents/`
- `src/orchestrator_v3.py`
- `src/orchestrator_v2.py`

## Validation Checks

### Tier 0 (Experimental) - All Optional

- ✅ **parse**: Module can be parsed by Python AST
- 🔶 **module_docstring**: Module has docstring (optional)
- 🔶 **cgrf_metadata**: Has `_MODULE_NAME`, `_MODULE_VERSION`, `_CGRF_TIER` (optional)
- 🔶 **test_file**: Has corresponding test file (optional)

### Tier 1 (Development) - Production Ready

- ✅ **parse**: Module can be parsed
- ✅ **module_docstring**: Module has docstring (required)
- ✅ **cgrf_metadata**: Complete CGRF metadata with matching tier (required)
- ✅ **test_file**: Corresponding test file exists in `tests/` (required)

### Tier 2 (Production) - Tier 1 + Integration

- All Tier 1 requirements
- ✅ **integration_tests**: Integration tests in `tests/integration/` (required)

### Tier 3 (Mission-Critical) - Tier 2 + E2E

- All Tier 2 requirements
- ✅ **e2e_tests**: Module referenced in E2E test suite (required)

## CGRF Metadata Format

For Tier 1+, modules must include CGRF metadata constants:

```python
# Module metadata constants
_MODULE_NAME = "sentinel_v2"
_MODULE_VERSION = "2.1.0"
_CGRF_TIER = 1  # 0=Experimental, 1=Development, 2=Production, 3=Mission-Critical

def _generate_cgrf_metadata(packet: HandoffPacket) -> CGRFMetadata:
    """Generate CGRF v3.0 metadata for agent output."""
    timestamp = datetime.utcnow().isoformat() + "Z"
    report_id = f"SRS-SENTINEL-{datetime.utcnow().strftime('%Y%m%d')}-{packet.event.event_id[:8]}-V{_MODULE_VERSION}"

    return CGRFMetadata(
        report_id=report_id,
        tier=_CGRF_TIER,
        module_version=_MODULE_VERSION,
        module_name=_MODULE_NAME,
        execution_role="BACKEND_SERVICE",
        created=timestamp,
        author="agent",
        last_updated=timestamp,
    )
```

## Color Coding

- 🟢 **GREEN [PASS]**: Check passed
- 🔴 **RED [FAIL]**: Required check failed
- 🟡 **YELLOW [WARN]**: Optional check failed or warning
- 🔵 **CYAN**: Tier 1 (Development)
- 🟡 **YELLOW**: Tier 2 (Production)
- 🔴 **RED**: Tier 3 (Mission-Critical)
- ⚪ **DIM**: Tier 0 (Experimental)

## Test File Discovery

The validator searches for test files in these locations:

- `tests/test_{module_name}.py`
- `test/test_{module_name}.py`
- `tests/{module_name}_test.py`

For integration tests (Tier 2+):

- `tests/integration/*{module_name}*.py`

For E2E tests (Tier 3):

- `tests/test_pipeline_e2e.py` (module must be referenced)

## Troubleshooting

### "Module not found" error

- Ensure the path is correct relative to project root
- Use forward slashes or escaped backslashes in paths

### "Not compliant" with CGRF metadata

- Add `_MODULE_NAME`, `_MODULE_VERSION`, `_CGRF_TIER` constants
- Implement `_generate_cgrf_metadata()` function
- Ensure tier value matches target tier

### "No test file found"

- Create a test file in `tests/test_{module_name}.py`
- Or update validator to recognize existing test patterns

## Development

### Project Structure

```
src/cgrf/
├── __init__.py          # Package metadata
├── __main__.py          # Module entry point
├── cli.py               # CLI interface (argparse + colors)
├── validator.py         # Validation logic
└── README.md            # This file

cgrf.py                  # Standalone entry point
```

### Adding New Validation Checks

Edit `src/cgrf/validator.py` and add checks to `CGRFValidator` class:

```python
def _check_custom_requirement(self, ..., result: ValidationResult, requirements: Dict) -> None:
    """Check custom requirement."""
    required = requirements.get("custom_required", False)

    # Perform validation logic
    passed = ...

    result.add_check(
        "custom_requirement",
        passed,
        "Custom requirement message",
        required=required
    )
```

Then update `TIER_REQUIREMENTS` dict to include the requirement for specific tiers.

## References

- CGRF Specification: `citadel_lite/blueprints/CGRF.txt`
- Module Types: `src/types.py` (CGRFMetadata dataclass)
- Implementation Examples: `src/agents/sentinel_v2.py`, `src/agents/guardian_v3.py`

## Version History

- **v0.1.0** (2026-02-11): Initial MVP release
  - `validate` command with tier 0-3 support
  - `tier-check` command for batch validation
  - `report` command for compliance reports
  - CGRF metadata validation
  - Test file discovery
  - Color-coded terminal output
