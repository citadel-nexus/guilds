# src/services/auth.py
"""
API key hashing and verification for MCP server auth.
"""
from __future__ import annotations

import hashlib
import hmac
import os


def hash_key(raw_key: str) -> str:
    """Return a hex-encoded SHA-256 hash of the API key.

    Consistent with how keys are stored in the api_keys table:
        hash_key(raw) == stored_hash  →  authentic
    """
    secret = os.environ.get("MCP_KEY_SALT", "citadel-mcp-salt")
    return hmac.new(
        secret.encode(), raw_key.encode(), hashlib.sha256
    ).hexdigest()
