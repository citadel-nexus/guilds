"""
SMP Notion Registry Sync.

Synchronises SMP (Software Module Profile) metadata for citadel_lite
modules into a Notion database.  Each module gets one row with:
  module_name, version, cgrf_tier, execution_role, caps_grade, srs_codes,
  last_synced, compliance_pass.

All public functions are safe to call when ``NOTION_TOKEN`` or
``NOTION_SMP_REGISTRY_DB_ID`` are unset — they log a warning and return
None (dry-run safe).

CGRF compliance
---------------
_MODULE_NAME    = "smp_notion_sync"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER      = 1
_EXECUTION_ROLE = "INTEGRATION"
"""
from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

# ── CGRF Metadata ────────────────────────────────────────────────────────────
_MODULE_NAME    = "smp_notion_sync"
_MODULE_VERSION = "1.0.0"
_CGRF_TIER      = 1
_EXECUTION_ROLE = "INTEGRATION"
# ─────────────────────────────────────────────────────────────────────────────

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.notion.com/v1"
_NOTION_VERSION = "2022-06-28"
_REQUIRED_FIELDS = ("_MODULE_NAME", "_MODULE_VERSION", "_CGRF_TIER", "_EXECUTION_ROLE")


# ── Credential helpers ────────────────────────────────────────────────────────

def _token() -> Optional[str]:
    return os.getenv("NOTION_TOKEN")


def _db_id() -> Optional[str]:
    return os.getenv("NOTION_SMP_REGISTRY_DB_ID")


def _headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {_token()}",
        "Notion-Version": _NOTION_VERSION,
        "Content-Type": "application/json",
    }


# ── Module introspection ──────────────────────────────────────────────────────

def _extract_cgrf_fields(py_file: Path) -> Dict[str, Any]:
    """
    Extract CGRF 4-field values from a .py file via regex.

    Returns a dict with keys: module_name, version, cgrf_tier,
    execution_role, compliance_pass.
    """
    try:
        content = py_file.read_text(encoding="utf-8")
    except Exception:
        return {"module_name": py_file.stem, "version": "", "cgrf_tier": -1,
                "execution_role": "", "compliance_pass": False}

    def _find(field: str) -> Optional[str]:
        m = re.search(rf"^{re.escape(field)}\s*=\s*(.+)$", content, re.MULTILINE)
        if m:
            return m.group(1).strip().strip('"').strip("'")
        return None

    module_name = _find("_MODULE_NAME") or py_file.stem
    version = _find("_MODULE_VERSION") or ""
    tier_raw = _find("_CGRF_TIER")
    try:
        tier = int(tier_raw) if tier_raw is not None else -1
    except ValueError:
        tier = -1
    execution_role = _find("_EXECUTION_ROLE") or ""

    compliance_pass = all([
        bool(_find(f)) for f in _REQUIRED_FIELDS
    ])

    return {
        "module_name": module_name,
        "version": version,
        "cgrf_tier": tier,
        "execution_role": execution_role,
        "compliance_pass": compliance_pass,
    }


def collect_module_metadata(src_dir: Path) -> List[Dict[str, Any]]:
    """
    Scan *src_dir* recursively and return a list of module metadata dicts.

    Skips __init__.py and conftest.py.
    """
    skip = {"__init__.py", "conftest.py"}
    modules = []
    for py_file in sorted(src_dir.rglob("*.py")):
        if py_file.name in skip:
            continue
        meta = _extract_cgrf_fields(py_file)
        try:
            meta["rel_path"] = str(py_file.relative_to(src_dir.parent))
        except ValueError:
            meta["rel_path"] = str(py_file)
        modules.append(meta)
    return modules


# ── Notion page builders ──────────────────────────────────────────────────────

def _build_properties(module: Dict[str, Any]) -> Dict[str, Any]:
    """Build Notion page properties payload for a module entry."""
    tier_map = {-1: "UNKNOWN", 0: "T0", 1: "T1", 2: "T2", 3: "T3"}
    tier_label = tier_map.get(module.get("cgrf_tier", -1), "UNKNOWN")

    props: Dict[str, Any] = {
        "module_name": {
            "title": [{"text": {"content": module.get("module_name", "")}}]
        },
        "version": {
            "rich_text": [{"text": {"content": module.get("version", "")}}]
        },
        "cgrf_tier": {
            "select": {"name": tier_label}
        },
        "execution_role": {
            "select": {"name": module.get("execution_role", "UNKNOWN") or "UNKNOWN"}
        },
        "caps_grade": {
            "select": {"name": module.get("caps_grade", "UNKNOWN") or "UNKNOWN"}
        },
        "last_synced": {
            "date": {"start": datetime.now(timezone.utc).isoformat()}
        },
        "compliance_pass": {
            "checkbox": bool(module.get("compliance_pass", False))
        },
    }
    # srs_codes (multi-select) — optional
    srs_codes = module.get("srs_codes", [])
    if srs_codes:
        props["srs_codes"] = {
            "multi_select": [{"name": c} for c in srs_codes]
        }
    return props


def _query_existing_entries(db_id: str) -> Dict[str, str]:
    """
    Return a mapping of module_name → page_id for existing DB entries.

    Returns {} on failure.
    """
    url = f"{_BASE_URL}/databases/{db_id}/query"
    try:
        resp = requests.post(url, headers=_headers(), json={}, timeout=10)
        resp.raise_for_status()
        pages = resp.json().get("results", [])
        result = {}
        for page in pages:
            title_prop = page.get("properties", {}).get("module_name", {})
            title_parts = title_prop.get("title", [])
            if title_parts:
                name = title_parts[0].get("text", {}).get("content", "")
                result[name] = page["id"]
        return result
    except Exception as e:
        logger.warning("smp_notion_sync: failed to query existing entries: %s", e)
        return {}


def _create_page(db_id: str, properties: Dict[str, Any]) -> Optional[str]:
    """Create a new Notion page in the SMP registry DB. Returns page_id or None."""
    url = f"{_BASE_URL}/pages"
    payload = {"parent": {"database_id": db_id}, "properties": properties}
    try:
        resp = requests.post(url, headers=_headers(), json=payload, timeout=10)
        resp.raise_for_status()
        return resp.json().get("id")
    except Exception as e:
        logger.warning("smp_notion_sync: failed to create page: %s", e)
        return None


def _update_page(page_id: str, properties: Dict[str, Any]) -> bool:
    """Update an existing Notion page. Returns True on success."""
    url = f"{_BASE_URL}/pages/{page_id}"
    try:
        resp = requests.patch(url, headers=_headers(), json={"properties": properties}, timeout=10)
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.warning("smp_notion_sync: failed to update page %s: %s", page_id, e)
        return False


# ── Public entry points ───────────────────────────────────────────────────────

def sync_smp_registry(
    modules: Optional[List[Dict[str, Any]]] = None,
    src_dir: Optional[str] = None,
    dry_run: bool = True,
) -> List[Dict[str, Any]]:
    """
    Sync module SMP metadata to the Notion SMP Registry DB.

    Parameters
    ----------
    modules :
        List of module dicts (with keys: module_name, version, cgrf_tier,
        execution_role, caps_grade, srs_codes, compliance_pass).
        If None, collects from *src_dir* automatically.
    src_dir :
        Path to scan when *modules* is None.  Defaults to ``src/`` relative
        to the project root (two levels up from this file).
    dry_run :
        If True no Notion API calls are made — returns the would-be payloads.

    Returns
    -------
    List of result dicts:
      {"module_name": ..., "action": "create|update|skip", "status": "ok|dry_run|error"}
    """
    tok = _token()
    db = _db_id()

    if not tok or not db:
        missing = []
        if not tok:
            missing.append("NOTION_TOKEN")
        if not db:
            missing.append("NOTION_SMP_REGISTRY_DB_ID")
        logger.warning("smp_notion_sync: %s not set — no-op", ", ".join(missing))
        return []

    if modules is None:
        root = Path(__file__).resolve().parent.parent.parent
        scan_dir = Path(src_dir) if src_dir else root / "src"
        modules = collect_module_metadata(scan_dir)

    if dry_run:
        logger.info("smp_notion_sync: dry_run=True — %d module(s) would be synced", len(modules))
        return [
            {"module_name": m.get("module_name", ""), "action": "dry_run", "status": "dry_run"}
            for m in modules
        ]

    existing = _query_existing_entries(db)
    results = []

    for module in modules:
        name = module.get("module_name", "")
        properties = _build_properties(module)

        if name in existing:
            ok = _update_page(existing[name], properties)
            results.append({
                "module_name": name,
                "action": "update",
                "status": "ok" if ok else "error",
            })
        else:
            page_id = _create_page(db, properties)
            results.append({
                "module_name": name,
                "action": "create",
                "status": "ok" if page_id else "error",
            })
        logger.debug("smp_notion_sync: %s → %s", name, results[-1]["status"])

    ok_count = sum(1 for r in results if r["status"] == "ok")
    logger.info("smp_notion_sync: synced %d/%d modules", ok_count, len(modules))
    return results
