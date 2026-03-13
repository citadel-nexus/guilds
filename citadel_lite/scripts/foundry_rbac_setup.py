#!/usr/bin/env python3
"""
Foundry RBAC Setup Agent
=========================
Automatically assigns the "Azure AI Developer" role to the current identity
on the citadel-nexus Azure AI Foundry project workspace.

This unlocks:
  - Foundry Agent threads (create_thread_and_process_run)
  - Agent234 (gpt-4o) and Agent340 (o1) via the projects SDK
  - Full stateful agent memory in citadel-nexus

Auth flow (tries in order):
  1. Azure CLI session   (run: az login)
  2. Device code browser (automatic fallback, opens browser)
  3. Environment vars    (AZURE_CLIENT_ID + AZURE_CLIENT_SECRET + AZURE_TENANT_ID)

Usage:
    python scripts/foundry_rbac_setup.py             # auto-assign current user
    python scripts/foundry_rbac_setup.py --check     # just check current roles
    python scripts/foundry_rbac_setup.py --principal <object-id>  # assign specific principal

SRS: SRS-AZURE-RBAC-001
"""
from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
SUBSCRIPTION_ID   = "9e5f865a-cfe9-4394-99d8-0b140ee59b40"
RESOURCE_GROUP    = "SUB_SYSTEMS"
PROJECT_NAME      = "citadel-nexus"   # Azure AI Foundry project / ML workspace name
AI_SERVICES_NAME  = "OAD"             # Azure AI Services resource name
TENANT_ID         = "e83868a2-a735-46d1-88fd-2a263d356d84"  # Subscription's home tenant

# Azure AI Developer role definition ID (built-in, stable across subscriptions)
AZURE_AI_DEVELOPER_ROLE = "64702f94-c441-49e6-a78b-ef80e0188fee"
ROLE_LABEL = "Azure AI Developer"

# Possible resource providers for the Foundry project
WORKSPACE_SCOPES = [
    # AI Foundry project (backed by AML workspace)
    f"/subscriptions/{SUBSCRIPTION_ID}/resourceGroups/{RESOURCE_GROUP}"
    f"/providers/Microsoft.MachineLearningServices/workspaces/{PROJECT_NAME}",
    # Azure AI Services resource (hub-level)
    f"/subscriptions/{SUBSCRIPTION_ID}/resourceGroups/{RESOURCE_GROUP}"
    f"/providers/Microsoft.CognitiveServices/accounts/{AI_SERVICES_NAME}",
    # Resource group scope (broader — covers both)
    f"/subscriptions/{SUBSCRIPTION_ID}/resourceGroups/{RESOURCE_GROUP}",
]


def _get_credential(tenant_id: str = TENANT_ID):
    """Get Azure credential scoped to the correct tenant."""
    from azure.identity import (
        DefaultAzureCredential, AzureCliCredential,
        DeviceCodeCredential, InteractiveBrowserCredential,
    )

    # ── Strategy 1: Azure CLI with explicit tenant ────────────────────────────
    print(f"[auth] Trying AzureCliCredential (tenant={tenant_id})...")
    try:
        cred = AzureCliCredential(tenant_id=tenant_id)
        token = cred.get_token("https://management.azure.com/.default")
        print(f"[auth] AzureCliCredential OK (expires: {token.expires_on})")
        return cred
    except Exception as e:
        print(f"[auth] AzureCliCredential failed: {e}")
        if "az login" in str(e).lower() or "not logged in" in str(e).lower():
            print(f"\n[auth] Run this to log in to the correct tenant:")
            print(f"       az login --tenant {tenant_id}")
            print(f"       (then re-run this script)\n")

    # ── Strategy 2: DefaultAzureCredential with tenant hint ───────────────────
    print(f"[auth] Trying DefaultAzureCredential (tenant={tenant_id})...")
    try:
        cred = DefaultAzureCredential(
            tenant_id=tenant_id,
            exclude_visual_studio_code_credential=True,
            exclude_interactive_browser_credential=True,
        )
        token = cred.get_token("https://management.azure.com/.default")
        print(f"[auth] DefaultAzureCredential OK")
        return cred
    except Exception as e:
        print(f"[auth] DefaultAzureCredential failed: {e}")

    # ── Strategy 3: Device code (always works, opens browser) ────────────────
    print(f"[auth] Falling back to DeviceCodeCredential (browser login)...")
    cred = DeviceCodeCredential(tenant_id=tenant_id)
    token = cred.get_token("https://management.azure.com/.default")
    print(f"[auth] DeviceCodeCredential OK")
    return cred


def _decode_jwt_claims(token_str: str) -> dict:
    """Decode JWT payload without verification."""
    import base64, json
    parts = token_str.split(".")
    if len(parts) < 2:
        return {}
    # Add padding
    payload = parts[1]
    payload += "=" * (4 - len(payload) % 4)
    try:
        return json.loads(base64.urlsafe_b64decode(payload))
    except Exception:
        return {}


def _get_current_principal_id(cred) -> str:
    """Get the object ID of the currently authenticated principal."""
    import urllib.request, json

    # ── Strategy 1: MS Graph /me (works for interactive user accounts) ────────
    try:
        token = cred.get_token("https://graph.microsoft.com/User.Read")
        req = urllib.request.Request(
            "https://graph.microsoft.com/v1.0/me",
            headers={"Authorization": f"Bearer {token.token}"},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            me = json.loads(r.read())
            oid = me.get("id") or me.get("objectId", "")
            display = me.get("displayName", me.get("userPrincipalName", "unknown"))
            if oid:
                print(f"[graph] Signed in as: {display}  objectId={oid}")
                return oid
    except Exception as e:
        print(f"[graph] /me failed ({e})")

    # ── Strategy 2: Decode ARM token JWT claims ───────────────────────────────
    print("[jwt]  Decoding ARM access token claims...")
    token2 = cred.get_token("https://management.azure.com/.default")
    claims = _decode_jwt_claims(token2.token)
    upn = claims.get("upn") or claims.get("unique_name") or claims.get("appid", "unknown")
    print(f"[jwt]  Account: {upn}")
    print(f"[jwt]  All claims keys: {list(claims.keys())}")

    # Try all known OID claim names (MSA accounts use 'puid' or nested 'oid')
    for field in ["oid", "sub", "puid", "objectId"]:
        val = claims.get(field, "")
        if val and len(val) > 10:
            print(f"[jwt]  Using claim '{field}' as principal ID: {val}")
            return val

    # ── Strategy 3: ARM /subscriptions whoami ────────────────────────────────
    print("[arm]  Trying ARM subscription lookup for identity...")
    try:
        req3 = urllib.request.Request(
            f"https://management.azure.com/subscriptions/{SUBSCRIPTION_ID}"
            f"?api-version=2022-12-01",
            headers={"Authorization": f"Bearer {token2.token}"},
        )
        with urllib.request.urlopen(req3, timeout=10) as r:
            pass  # Just checking auth works
    except Exception:
        pass

    # ── Strategy 4: Azure CLI direct object ID ───────────────────────────────
    import subprocess
    print("[cli]  Trying: az ad signed-in-user show --query id")
    try:
        result = subprocess.check_output(
            ["az", "ad", "signed-in-user", "show", "--query", "id", "-o", "tsv"],
            stderr=subprocess.DEVNULL, timeout=15
        ).decode().strip()
        if result and len(result) > 10:
            print(f"[cli]  objectId from az CLI: {result}")
            return result
    except Exception as e:
        print(f"[cli]  az CLI failed: {e}")

    raise RuntimeError(
        "Cannot determine principal ID automatically.\n"
        "Run with: python scripts/foundry_rbac_setup.py --principal <your-azure-object-id>\n"
        "Find your object ID at: https://portal.azure.com/#view/Microsoft_AAD_IAM/ActiveDirectoryMenuBlade"
    )


def _list_role_assignments(auth_client, scope: str, principal_id: str):
    """List existing role assignments for a principal at a scope."""
    try:
        assignments = list(auth_client.role_assignments.list_for_scope(
            scope=scope,
            filter=f"principalId eq '{principal_id}'",
        ))
        return assignments
    except Exception as e:
        print(f"[rbac]   list_for_scope failed at {scope}: {e}")
        return []


def _assign_role(auth_client, scope: str, principal_id: str, role_def_id: str) -> bool:
    """Create a role assignment. Returns True if assigned (or already exists)."""
    from azure.mgmt.authorization.models import RoleAssignmentCreateParameters

    role_def_scope = f"/subscriptions/{SUBSCRIPTION_ID}/providers/Microsoft.Authorization/roleDefinitions/{role_def_id}"
    assignment_name = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{scope}-{principal_id}-{role_def_id}"))

    try:
        result = auth_client.role_assignments.create(
            scope=scope,
            role_assignment_name=assignment_name,
            parameters=RoleAssignmentCreateParameters(
                role_definition_id=role_def_scope,
                principal_id=principal_id,
                principal_type="User",
            ),
        )
        print(f"[rbac] ASSIGNED: {ROLE_LABEL} → principal {principal_id[:8]}... at {scope}")
        print(f"[rbac]   assignment_id: {result.id}")
        return True
    except Exception as e:
        err_str = str(e)
        if "RoleAssignmentExists" in err_str or "already exists" in err_str.lower():
            print(f"[rbac] Already exists: {ROLE_LABEL} at {scope}")
            return True
        print(f"[rbac] Assignment failed at {scope}: {e}")
        return False


def check_mode(auth_client, principal_id: str):
    """Print all current role assignments for the principal."""
    print(f"\n[check] Role assignments for principal {principal_id}:")
    for scope in WORKSPACE_SCOPES:
        assignments = _list_role_assignments(auth_client, scope, principal_id)
        if assignments:
            for a in assignments:
                print(f"  scope={scope.split('/')[-1]}  role={a.role_definition_id.split('/')[-1]}")
        else:
            print(f"  scope={scope.split('/')[-1]}  (none)")


def assign_mode(auth_client, principal_id: str):
    """Assign Azure AI Developer role — tries narrowest scope first, then broader."""
    print(f"\n[assign] Assigning '{ROLE_LABEL}' to principal {principal_id[:8]}...")

    for scope in WORKSPACE_SCOPES:
        scope_label = scope.split("/")[-1]
        print(f"\n[assign] Trying scope: {scope_label}")
        success = _assign_role(auth_client, scope, principal_id, AZURE_AI_DEVELOPER_ROLE)
        if success:
            print(f"\n[assign] SUCCESS — role assigned at scope: {scope_label}")
            print(f"[assign] Foundry Agent threads are now unlocked.")
            print(f"[assign] Test with:")
            print(f"  python scripts/foundry_rbac_setup.py --check")
            return True
        print(f"[assign] Failed at {scope_label}, trying broader scope...")

    print("\n[assign] All scopes failed. Manual steps:")
    print(f"  1. Go to: https://portal.azure.com/#resource/subscriptions/{SUBSCRIPTION_ID}/resourceGroups/{RESOURCE_GROUP}")
    print(f"  2. Access Control (IAM) -> Add -> Role Assignment")
    print(f"  3. Role: {ROLE_LABEL}")
    print(f"  4. Member: select your account (objectId: {principal_id})")
    return False


def main():
    parser = argparse.ArgumentParser(description="Citadel Lite - Foundry RBAC Setup Agent")
    parser.add_argument("--check", action="store_true", help="Check current role assignments only")
    parser.add_argument("--principal", default=None, help="Specific principal object ID to assign (default: current user)")
    parser.add_argument("--tenant", default=TENANT_ID, help=f"Azure tenant ID (default: {TENANT_ID})")
    args = parser.parse_args()

    print("=" * 60)
    print("  Foundry RBAC Setup Agent - citadel-nexus")
    print("=" * 60)
    print(f"  Tenant: {args.tenant}")

    # Auth
    try:
        cred = _get_credential(tenant_id=args.tenant)
    except Exception as e:
        print(f"\n[ERROR] Authentication failed: {e}")
        print("\nRun: az login  (install Azure CLI from https://aka.ms/installazurecliwindows)")
        sys.exit(1)

    # Management client
    from azure.mgmt.authorization import AuthorizationManagementClient
    auth_client = AuthorizationManagementClient(cred, SUBSCRIPTION_ID)

    # Principal ID
    if args.principal:
        principal_id = args.principal
        print(f"[auth] Using provided principal: {principal_id}")
    else:
        try:
            principal_id = _get_current_principal_id(cred)
        except Exception as e:
            print(f"\n[ERROR] Could not determine principal ID: {e}")
            print("Use --principal <objectId> to specify explicitly.")
            sys.exit(1)

    if not principal_id:
        print("[ERROR] Empty principal ID — cannot assign role.")
        sys.exit(1)

    # Run
    if args.check:
        check_mode(auth_client, principal_id)
    else:
        assign_mode(auth_client, principal_id)

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
