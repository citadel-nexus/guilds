# tests/test_cgrf_cli_json.py
"""Tests for CGRF CLI --json output mode — Phase 27."""
import json
import sys
import tempfile
import textwrap
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.cgrf.cli import cmd_validate, cmd_tier_check, cmd_report, main


# ========== helpers ==========

def _make_module(content: str) -> Path:
    """Write content to a temp .py file and return its path."""
    f = tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False, encoding="utf-8")
    f.write(textwrap.dedent(content))
    f.close()
    return Path(f.name)


def _ns(**kw):
    """Build an argparse-like namespace."""
    import argparse
    return argparse.Namespace(**kw)


def _capture_json(func, args):
    """Run a CLI command and capture its JSON stdout."""
    import io
    buf = io.StringIO()
    with patch("sys.stdout", buf):
        rc = func(args)
    output = buf.getvalue().strip()
    return rc, json.loads(output)


# ========== validate --json ==========

def test_validate_json_compliant_tier0():
    """validate --json returns compliant=true for a parseable module at Tier 0."""
    mod = _make_module('"""Hello."""\nx = 1\n')
    rc, data = _capture_json(cmd_validate, _ns(module=str(mod), tier=0, json=True))
    assert rc == 0
    assert data["command"] == "validate"
    assert data["compliant"] is True
    assert data["tier"] == 0
    assert isinstance(data["checks"], list)
    assert any(c["name"] == "parse" and c["passed"] for c in data["checks"])


def test_validate_json_non_compliant():
    """validate --json returns compliant=false when metadata missing at Tier 1."""
    mod = _make_module('"""Hello."""\nx = 1\n')
    rc, data = _capture_json(cmd_validate, _ns(module=str(mod), tier=1, json=True))
    assert rc == 1
    assert data["compliant"] is False
    failed = [c for c in data["checks"] if not c["passed"] and c["required"]]
    assert len(failed) > 0


def test_validate_json_with_metadata():
    """validate --json with full CGRF metadata at Tier 1."""
    mod = _make_module('''\
        """Agent module."""
        _MODULE_NAME = "test_agent"
        _MODULE_VERSION = "1.0.0"
        _CGRF_TIER = 0
        x = 1
    ''')
    rc, data = _capture_json(cmd_validate, _ns(module=str(mod), tier=0, json=True))
    assert rc == 0
    assert data["compliant"] is True


def test_validate_json_module_not_found():
    """validate --json with non-existent module returns error JSON."""
    rc, data = _capture_json(cmd_validate, _ns(module="/nonexistent/foo.py", tier=1, json=True))
    assert rc == 1
    assert "error" in data


# ========== tier-check --json ==========

def test_tier_check_json_all_pass():
    """tier-check --json with multiple modules all passing Tier 0."""
    m1 = _make_module('"""A."""\nx = 1\n')
    m2 = _make_module('"""B."""\ny = 2\n')
    rc, data = _capture_json(cmd_tier_check, _ns(modules=[str(m1), str(m2)], tier=0, json=True))
    assert rc == 0
    assert data["command"] == "tier-check"
    assert data["summary"]["total"] == 2
    assert data["summary"]["passed"] == 2
    assert data["summary"]["failed"] == 0


def test_tier_check_json_mixed():
    """tier-check --json with one valid and one nonexistent module."""
    m1 = _make_module('"""A."""\nx = 1\n')
    rc, data = _capture_json(cmd_tier_check, _ns(modules=[str(m1), "/no/such.py"], tier=0, json=True))
    assert rc == 1
    assert data["summary"]["failed"] >= 1
    assert len(data["results"]) == 2


# ========== report --json ==========

def test_report_json_output():
    """report --json returns structured output with modules and summary."""
    import io
    buf = io.StringIO()
    with patch("sys.stdout", buf):
        rc = cmd_report(_ns(tier=1, json=True))
    output = buf.getvalue().strip()
    data = json.loads(output)
    assert rc == 0
    assert data["command"] == "report"
    assert "summary" in data
    assert "total" in data["summary"]
    assert "modules" in data


# ========== main() integration ==========

def test_main_validate_json_flag():
    """main() with validate --json works end-to-end."""
    mod = _make_module('"""Hello."""\nx = 1\n')
    import io
    buf = io.StringIO()
    with patch("sys.argv", ["cgrf", "validate", "--module", str(mod), "--tier", "0", "--json"]):
        with patch("sys.stdout", buf):
            rc = main()
    output = buf.getvalue().strip()
    data = json.loads(output)
    assert data["command"] == "validate"
    assert data["compliant"] is True
