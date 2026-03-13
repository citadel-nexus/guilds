"""
Data Migration Tool — Supabase <-> AWS S3 <-> VPS

Provides bidirectional data migration across all three tiers:
  - Supabase (PostgreSQL via REST API) — structured data, user records, pipeline state
  - AWS S3 (citadel-nexus-assets) — binary assets, backups, generated files
  - VPS local filesystem (/srv/projects/) — working data, hot cache, local processing

Extends existing GCS rehydration pattern to include AWS S3 as a storage tier.

Usage (standalone):
    python -m citadel_lite.src.tools.data_migration supabase-to-s3 --table pipeline_runs
    python -m citadel_lite.src.tools.data_migration s3-to-vps --prefix assets/books/
    python -m citadel_lite.src.tools.data_migration vps-to-s3 --path /srv/projects/data/
    python -m citadel_lite.src.tools.data_migration status

Usage (A2A / agent pipeline):
    from citadel_lite.src.tools.data_migration import run_migration
    result = run_migration({"direction": "supabase_to_s3", "table": "pipeline_runs"})

CGRF v3.0: SRS-MIGRATION-001, Tier 1
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import hashlib
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Literal

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

AWS_REGION = "us-east-1"
S3_BUCKET = "citadel-nexus-assets"
VPS_DATA_ROOT = "/srv/projects"
VPS_MIGRATION_DIR = "/srv/projects/citadel/migrations"

# Supabase tables eligible for migration
MIGRATABLE_TABLES = [
    "pipeline_runs",
    "agent_outputs",
    "memory_entries",
    "skill_executions",
    "onboarding_progress",
    "engagement_metrics",
    "xp_transactions",
]

# S3 prefix mapping for different data categories
S3_PREFIX_MAP = {
    "pipeline_runs": "data/pipeline/",
    "agent_outputs": "data/agents/",
    "memory_entries": "data/memory/",
    "skill_executions": "data/skills/",
    "onboarding_progress": "data/onboarding/",
    "engagement_metrics": "data/engagement/",
    "xp_transactions": "data/xp/",
    "backups": "backups/",
    "assets": "assets/",
    "generated": "generated/",
}


class MigrationDirection(Enum):
    SUPABASE_TO_S3 = "supabase_to_s3"
    S3_TO_SUPABASE = "s3_to_supabase"
    SUPABASE_TO_VPS = "supabase_to_vps"
    VPS_TO_SUPABASE = "vps_to_supabase"
    S3_TO_VPS = "s3_to_vps"
    VPS_TO_S3 = "vps_to_s3"
    FULL_BACKUP = "full_backup"  # Supabase -> S3 + VPS


@dataclass
class MigrationRecord:
    """Record of a single migration operation."""
    migration_id: str
    direction: str
    source: str
    target: str
    entity_type: str
    started_at: str
    status: Literal["pending", "in_progress", "completed", "failed"] = "pending"
    completed_at: Optional[str] = None
    records_processed: int = 0
    bytes_transferred: int = 0
    errors: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# AWS CLI wrapper (local reuse from aws_agent pattern)
# ---------------------------------------------------------------------------

def _aws(*args: str, parse_json: bool = True, timeout: int = 120) -> Any:
    """Run an AWS CLI command and return parsed JSON or raw output."""
    cmd = ["aws", "--region", AWS_REGION, "--output", "json", *args]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(f"aws {' '.join(args[:3])}... failed: {result.stderr.strip()}")
    if not result.stdout.strip():
        return {}
    return json.loads(result.stdout) if parse_json else result.stdout


# ---------------------------------------------------------------------------
# Supabase client (lazy init)
# ---------------------------------------------------------------------------

_supabase_client = None


def _get_supabase():
    """Get or create Supabase client."""
    global _supabase_client
    if _supabase_client is not None:
        return _supabase_client

    try:
        from supabase import create_client
    except ImportError:
        raise RuntimeError("supabase-py not installed. Run: pip install supabase")

    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "") or os.getenv("SUPABASE_ANON_KEY", "")
    if not url or not key:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in environment"
        )

    _supabase_client = create_client(url, key)
    return _supabase_client


def _content_hash(data: bytes) -> str:
    """SHA-256 hash of content for integrity verification."""
    return hashlib.sha256(data).hexdigest()[:16]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _migration_id(direction: str, entity: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"mig_{direction}_{entity}_{ts}"


# ---------------------------------------------------------------------------
# Supabase -> S3
# ---------------------------------------------------------------------------

def supabase_to_s3(
    table: str,
    limit: int = 1000,
    age_days: Optional[int] = None,
) -> MigrationRecord:
    """Export a Supabase table to S3 as JSON lines."""
    prefix = S3_PREFIX_MAP.get(table, f"data/{table}/")
    record = MigrationRecord(
        migration_id=_migration_id("sub2s3", table),
        direction=MigrationDirection.SUPABASE_TO_S3.value,
        source=f"supabase:{table}",
        target=f"s3://{S3_BUCKET}/{prefix}",
        entity_type=table,
        started_at=_now(),
        status="in_progress",
    )

    try:
        sb = _get_supabase()
        query = sb.table(table).select("*").limit(limit)

        if age_days is not None:
            from datetime import timedelta
            cutoff = (datetime.now(timezone.utc) - timedelta(days=age_days)).isoformat()
            query = query.lt("created_at", cutoff)

        response = query.execute()
        rows = response.data

        if not rows:
            record.status = "completed"
            record.completed_at = _now()
            record.metadata["note"] = "No rows matched"
            return record

        # Write to temp file, upload to S3
        export_data = json.dumps(rows, indent=2, default=str)
        export_bytes = export_data.encode("utf-8")
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        s3_key = f"{prefix}{table}_{ts}.json"

        # Write temp file
        tmp_path = f"/tmp/migration_{table}_{ts}.json"
        with open(tmp_path, "w") as f:
            f.write(export_data)

        _aws("s3", "cp", tmp_path, f"s3://{S3_BUCKET}/{s3_key}", parse_json=False)
        os.unlink(tmp_path)

        record.status = "completed"
        record.completed_at = _now()
        record.records_processed = len(rows)
        record.bytes_transferred = len(export_bytes)
        record.metadata = {
            "s3_key": s3_key,
            "content_hash": _content_hash(export_bytes),
            "row_count": len(rows),
        }

    except Exception as e:
        record.status = "failed"
        record.errors.append(str(e))
        record.completed_at = _now()

    return record


# ---------------------------------------------------------------------------
# S3 -> Supabase
# ---------------------------------------------------------------------------

def s3_to_supabase(
    s3_key: str,
    table: str,
    upsert: bool = True,
    conflict_column: str = "id",
) -> MigrationRecord:
    """Import a JSON file from S3 into a Supabase table."""
    record = MigrationRecord(
        migration_id=_migration_id("s32sub", table),
        direction=MigrationDirection.S3_TO_SUPABASE.value,
        source=f"s3://{S3_BUCKET}/{s3_key}",
        target=f"supabase:{table}",
        entity_type=table,
        started_at=_now(),
        status="in_progress",
    )

    try:
        # Download from S3
        tmp_path = f"/tmp/migration_import_{table}.json"
        _aws("s3", "cp", f"s3://{S3_BUCKET}/{s3_key}", tmp_path, parse_json=False)

        with open(tmp_path, "r") as f:
            rows = json.load(f)
        os.unlink(tmp_path)

        if not isinstance(rows, list):
            rows = [rows]

        sb = _get_supabase()

        # Batch upsert (chunks of 100)
        batch_size = 100
        total = 0
        for i in range(0, len(rows), batch_size):
            batch = rows[i : i + batch_size]
            if upsert:
                sb.table(table).upsert(batch, on_conflict=conflict_column).execute()
            else:
                sb.table(table).insert(batch).execute()
            total += len(batch)

        record.status = "completed"
        record.completed_at = _now()
        record.records_processed = total
        record.bytes_transferred = os.path.getsize(tmp_path) if os.path.exists(tmp_path) else 0
        record.metadata = {"upsert": upsert, "conflict_column": conflict_column}

    except Exception as e:
        record.status = "failed"
        record.errors.append(str(e))
        record.completed_at = _now()

    return record


# ---------------------------------------------------------------------------
# S3 <-> VPS
# ---------------------------------------------------------------------------

def s3_to_vps(
    prefix: str,
    local_dir: Optional[str] = None,
    delete: bool = False,
) -> MigrationRecord:
    """Sync S3 prefix to VPS local directory."""
    local_dir = local_dir or os.path.join(VPS_DATA_ROOT, "s3-mirror", prefix.rstrip("/"))
    record = MigrationRecord(
        migration_id=_migration_id("s32vps", prefix.replace("/", "_")),
        direction=MigrationDirection.S3_TO_VPS.value,
        source=f"s3://{S3_BUCKET}/{prefix}",
        target=local_dir,
        entity_type=prefix,
        started_at=_now(),
        status="in_progress",
    )

    try:
        os.makedirs(local_dir, exist_ok=True)

        sync_args = ["s3", "sync", f"s3://{S3_BUCKET}/{prefix}", local_dir]
        if delete:
            sync_args.append("--delete")

        output = _aws(*sync_args, parse_json=False, timeout=600)

        # Count synced files
        file_count = sum(1 for _ in Path(local_dir).rglob("*") if _.is_file())
        total_bytes = sum(f.stat().st_size for f in Path(local_dir).rglob("*") if f.is_file())

        record.status = "completed"
        record.completed_at = _now()
        record.records_processed = file_count
        record.bytes_transferred = total_bytes
        record.metadata = {"local_dir": local_dir, "delete_mode": delete}

    except Exception as e:
        record.status = "failed"
        record.errors.append(str(e))
        record.completed_at = _now()

    return record


def vps_to_s3(
    local_path: str,
    s3_prefix: Optional[str] = None,
    delete: bool = False,
) -> MigrationRecord:
    """Sync VPS local directory to S3."""
    if s3_prefix is None:
        # Derive prefix from path
        rel = os.path.relpath(local_path, VPS_DATA_ROOT)
        s3_prefix = f"vps-data/{rel}/"

    record = MigrationRecord(
        migration_id=_migration_id("vps2s3", s3_prefix.replace("/", "_")),
        direction=MigrationDirection.VPS_TO_S3.value,
        source=local_path,
        target=f"s3://{S3_BUCKET}/{s3_prefix}",
        entity_type=s3_prefix,
        started_at=_now(),
        status="in_progress",
    )

    try:
        if not os.path.exists(local_path):
            raise FileNotFoundError(f"Local path does not exist: {local_path}")

        sync_args = ["s3", "sync", local_path, f"s3://{S3_BUCKET}/{s3_prefix}"]
        if delete:
            sync_args.append("--delete")

        _aws(*sync_args, parse_json=False, timeout=600)

        # Count files
        p = Path(local_path)
        if p.is_dir():
            file_count = sum(1 for _ in p.rglob("*") if _.is_file())
            total_bytes = sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
        else:
            file_count = 1
            total_bytes = p.stat().st_size

        record.status = "completed"
        record.completed_at = _now()
        record.records_processed = file_count
        record.bytes_transferred = total_bytes
        record.metadata = {"s3_prefix": s3_prefix, "delete_mode": delete}

    except Exception as e:
        record.status = "failed"
        record.errors.append(str(e))
        record.completed_at = _now()

    return record


# ---------------------------------------------------------------------------
# Supabase <-> VPS
# ---------------------------------------------------------------------------

def supabase_to_vps(
    table: str,
    local_dir: Optional[str] = None,
    limit: int = 5000,
) -> MigrationRecord:
    """Export Supabase table to VPS local JSON files."""
    local_dir = local_dir or os.path.join(VPS_DATA_ROOT, "supabase-export", table)
    record = MigrationRecord(
        migration_id=_migration_id("sub2vps", table),
        direction=MigrationDirection.SUPABASE_TO_VPS.value,
        source=f"supabase:{table}",
        target=local_dir,
        entity_type=table,
        started_at=_now(),
        status="in_progress",
    )

    try:
        sb = _get_supabase()
        response = sb.table(table).select("*").limit(limit).execute()
        rows = response.data

        os.makedirs(local_dir, exist_ok=True)

        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        out_path = os.path.join(local_dir, f"{table}_{ts}.json")

        export_data = json.dumps(rows, indent=2, default=str)
        with open(out_path, "w") as f:
            f.write(export_data)

        record.status = "completed"
        record.completed_at = _now()
        record.records_processed = len(rows)
        record.bytes_transferred = len(export_data.encode("utf-8"))
        record.metadata = {"output_path": out_path, "row_count": len(rows)}

    except Exception as e:
        record.status = "failed"
        record.errors.append(str(e))
        record.completed_at = _now()

    return record


def vps_to_supabase(
    json_path: str,
    table: str,
    upsert: bool = True,
    conflict_column: str = "id",
) -> MigrationRecord:
    """Import a local JSON file into Supabase."""
    record = MigrationRecord(
        migration_id=_migration_id("vps2sub", table),
        direction=MigrationDirection.VPS_TO_SUPABASE.value,
        source=json_path,
        target=f"supabase:{table}",
        entity_type=table,
        started_at=_now(),
        status="in_progress",
    )

    try:
        with open(json_path, "r") as f:
            rows = json.load(f)

        if not isinstance(rows, list):
            rows = [rows]

        sb = _get_supabase()
        batch_size = 100
        total = 0

        for i in range(0, len(rows), batch_size):
            batch = rows[i : i + batch_size]
            if upsert:
                sb.table(table).upsert(batch, on_conflict=conflict_column).execute()
            else:
                sb.table(table).insert(batch).execute()
            total += len(batch)

        record.status = "completed"
        record.completed_at = _now()
        record.records_processed = total
        record.bytes_transferred = os.path.getsize(json_path)
        record.metadata = {"upsert": upsert, "conflict_column": conflict_column}

    except Exception as e:
        record.status = "failed"
        record.errors.append(str(e))
        record.completed_at = _now()

    return record


# ---------------------------------------------------------------------------
# Full backup (Supabase -> S3 + VPS)
# ---------------------------------------------------------------------------

def full_backup(
    tables: Optional[List[str]] = None,
    include_vps: bool = True,
) -> Dict[str, Any]:
    """
    Full backup: export all Supabase tables to S3 and optionally VPS.
    Returns a summary of all migration records.
    """
    tables = tables or MIGRATABLE_TABLES
    results = {
        "backup_id": _migration_id("full", "backup"),
        "started_at": _now(),
        "tables": {},
        "status": "in_progress",
    }

    for table in tables:
        try:
            s3_result = supabase_to_s3(table)
            results["tables"][table] = {"s3": s3_result.to_dict()}

            if include_vps:
                vps_result = supabase_to_vps(table)
                results["tables"][table]["vps"] = vps_result.to_dict()

        except Exception as e:
            results["tables"][table] = {"error": str(e)}

    # Summary
    completed = sum(
        1 for t in results["tables"].values()
        if isinstance(t, dict) and t.get("s3", {}).get("status") == "completed"
    )
    results["status"] = "completed"
    results["completed_at"] = _now()
    results["summary"] = {
        "total_tables": len(tables),
        "successful": completed,
        "failed": len(tables) - completed,
    }

    return results


# ---------------------------------------------------------------------------
# Migration status / inventory
# ---------------------------------------------------------------------------

def migration_status() -> Dict[str, Any]:
    """Get current state of all data stores."""
    status = {
        "timestamp": _now(),
        "stores": {},
    }

    # S3 stats
    try:
        data = _aws(
            "s3api", "list-objects-v2",
            "--bucket", S3_BUCKET,
            "--query", "length(Contents[])",
        )
        size_data = _aws(
            "s3api", "list-objects-v2",
            "--bucket", S3_BUCKET,
            "--query", "[sum(Contents[].Size), length(Contents[])]",
        )
        if isinstance(size_data, list) and len(size_data) == 2:
            total_bytes, obj_count = size_data
        else:
            total_bytes, obj_count = 0, 0

        status["stores"]["s3"] = {
            "bucket": S3_BUCKET,
            "object_count": obj_count,
            "total_size_gb": round((total_bytes or 0) / (1024**3), 2),
            "available": True,
        }
    except Exception as e:
        status["stores"]["s3"] = {"available": False, "error": str(e)}

    # VPS local stats
    try:
        vps_path = Path(VPS_DATA_ROOT)
        if vps_path.exists():
            total = sum(f.stat().st_size for f in vps_path.rglob("*") if f.is_file())
            status["stores"]["vps"] = {
                "root": VPS_DATA_ROOT,
                "total_size_gb": round(total / (1024**3), 2),
                "available": True,
            }
        else:
            status["stores"]["vps"] = {"available": False, "error": "Path not found"}
    except Exception as e:
        status["stores"]["vps"] = {"available": False, "error": str(e)}

    # Supabase connectivity
    try:
        sb = _get_supabase()
        # Quick health check — query one row from a known table
        sb.table("pipeline_runs").select("id").limit(1).execute()
        status["stores"]["supabase"] = {"available": True}
    except Exception as e:
        status["stores"]["supabase"] = {"available": False, "error": str(e)}

    return status


# ---------------------------------------------------------------------------
# Agent-compatible entry point
# ---------------------------------------------------------------------------

def run_migration(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Agent-compatible entry point for data migration.

    params:
        direction: str — one of MigrationDirection values
        table: str — Supabase table name (for supabase operations)
        prefix: str — S3 prefix (for S3 operations)
        path: str — VPS local path (for VPS operations)
        limit: int — row limit for exports (default 1000)
        upsert: bool — upsert mode for imports (default True)
        delete: bool — delete mode for sync (default False)
    """
    direction = params.get("direction", "")
    try:
        if direction == "supabase_to_s3":
            result = supabase_to_s3(
                table=params["table"],
                limit=params.get("limit", 1000),
                age_days=params.get("age_days"),
            )
        elif direction == "s3_to_supabase":
            result = s3_to_supabase(
                s3_key=params["s3_key"],
                table=params["table"],
                upsert=params.get("upsert", True),
            )
        elif direction == "s3_to_vps":
            result = s3_to_vps(
                prefix=params["prefix"],
                local_dir=params.get("local_dir"),
                delete=params.get("delete", False),
            )
        elif direction == "vps_to_s3":
            result = vps_to_s3(
                local_path=params["path"],
                s3_prefix=params.get("s3_prefix"),
                delete=params.get("delete", False),
            )
        elif direction == "supabase_to_vps":
            result = supabase_to_vps(
                table=params["table"],
                local_dir=params.get("local_dir"),
                limit=params.get("limit", 5000),
            )
        elif direction == "vps_to_supabase":
            result = vps_to_supabase(
                json_path=params["path"],
                table=params["table"],
                upsert=params.get("upsert", True),
            )
        elif direction == "full_backup":
            return full_backup(
                tables=params.get("tables"),
                include_vps=params.get("include_vps", True),
            )
        elif direction == "status":
            return migration_status()
        else:
            return {
                "status": "error",
                "error": f"Unknown direction: {direction}",
                "valid_directions": [d.value for d in MigrationDirection],
            }

        return result.to_dict()

    except Exception as e:
        return {"status": "failed", "error": str(e), "direction": direction}


# ---------------------------------------------------------------------------
# CLI interface
# ---------------------------------------------------------------------------

def _cli():
    """Command-line interface for data migration."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Citadel Data Migration Tool — Supabase <-> AWS S3 <-> VPS"
    )
    sub = parser.add_subparsers(dest="command")

    # supabase-to-s3
    p1 = sub.add_parser("supabase-to-s3", help="Export Supabase table to S3")
    p1.add_argument("--table", required=True, choices=MIGRATABLE_TABLES)
    p1.add_argument("--limit", type=int, default=1000)
    p1.add_argument("--age-days", type=int, help="Only export records older than N days")

    # s3-to-supabase
    p2 = sub.add_parser("s3-to-supabase", help="Import S3 JSON file to Supabase")
    p2.add_argument("--s3-key", required=True)
    p2.add_argument("--table", required=True, choices=MIGRATABLE_TABLES)
    p2.add_argument("--no-upsert", action="store_true")

    # s3-to-vps
    p3 = sub.add_parser("s3-to-vps", help="Sync S3 prefix to VPS local directory")
    p3.add_argument("--prefix", required=True)
    p3.add_argument("--local-dir", help="Override local directory")
    p3.add_argument("--delete", action="store_true", help="Mirror mode: delete absent files")

    # vps-to-s3
    p4 = sub.add_parser("vps-to-s3", help="Sync VPS local directory to S3")
    p4.add_argument("--path", required=True)
    p4.add_argument("--s3-prefix", help="Override S3 prefix")
    p4.add_argument("--delete", action="store_true")

    # supabase-to-vps
    p5 = sub.add_parser("supabase-to-vps", help="Export Supabase table to VPS JSON")
    p5.add_argument("--table", required=True, choices=MIGRATABLE_TABLES)
    p5.add_argument("--limit", type=int, default=5000)

    # vps-to-supabase
    p6 = sub.add_parser("vps-to-supabase", help="Import VPS JSON file to Supabase")
    p6.add_argument("--path", required=True)
    p6.add_argument("--table", required=True, choices=MIGRATABLE_TABLES)
    p6.add_argument("--no-upsert", action="store_true")

    # full-backup
    p7 = sub.add_parser("full-backup", help="Full backup of all tables to S3 + VPS")
    p7.add_argument("--tables", nargs="+", choices=MIGRATABLE_TABLES, help="Specific tables")
    p7.add_argument("--no-vps", action="store_true", help="Skip VPS backup")

    # status
    sub.add_parser("status", help="Show migration status of all data stores")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "supabase-to-s3":
        result = supabase_to_s3(args.table, args.limit, args.age_days)
        print(json.dumps(result.to_dict(), indent=2))
    elif args.command == "s3-to-supabase":
        result = s3_to_supabase(args.s3_key, args.table, upsert=not args.no_upsert)
        print(json.dumps(result.to_dict(), indent=2))
    elif args.command == "s3-to-vps":
        result = s3_to_vps(args.prefix, args.local_dir, args.delete)
        print(json.dumps(result.to_dict(), indent=2))
    elif args.command == "vps-to-s3":
        result = vps_to_s3(args.path, args.s3_prefix, args.delete)
        print(json.dumps(result.to_dict(), indent=2))
    elif args.command == "supabase-to-vps":
        result = supabase_to_vps(args.table, limit=args.limit)
        print(json.dumps(result.to_dict(), indent=2))
    elif args.command == "vps-to-supabase":
        result = vps_to_supabase(args.path, args.table, upsert=not args.no_upsert)
        print(json.dumps(result.to_dict(), indent=2))
    elif args.command == "full-backup":
        result = full_backup(args.tables, include_vps=not args.no_vps)
        print(json.dumps(result, indent=2))
    elif args.command == "status":
        result = migration_status()
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    _cli()
