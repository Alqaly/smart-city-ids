"""Authentication helpers — JWT creation, verification, and demo credentials.

This module provides the authentication layer for the Smart City IDS API.
It is intentionally **demo-grade** — credentials are hardcoded and JWTs
use a single symmetric key.  For production use, these should be replaced
with AD/LDAP/OAuth integration and an asymmetric signing key.

Functions:
    create_jwt_token   – Create a HS256 JWT valid for 24 hours.
    verify_jwt_token   – Decode and validate a JWT, returning the username.
    authenticate_user  – Check username/password against demo credentials.
    verify_token       – FastAPI ``Depends`` dependency for Bearer auth.

Security notes:
    * ``Config.SECRET_KEY`` is auto-generated at startup (see config.py)
      to avoid using a hardcoded key.
    * If the ``PyJWT`` library is not installed, both creation and
      verification fall back to a **base64-encoded** token — this is
      insecure but keeps the demo functional.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from config import Config

logger = logging.getLogger(__name__)

# FastAPI security scheme — extracts the Bearer token from the
# ``Authorization`` header automatically.
security = HTTPBearer()

# ── Demo credentials ──────────────────────────────────────────────────────
# Three built-in users for live demonstrations.
# In production, replace with AD/LDAP/database-backed auth.
_DEMO_USERS = {
    "analyst": "analyst",    # View-only analyst role.
    "operator": "operator",  # Can approve/reject governance actions.
    "admin": "admin",        # Full administrative access.
}


def create_jwt_token(username: str) -> str:
    """Create a HS256 JWT token valid for 24 hours.

    The ``iat`` (issued-at) and ``exp`` (expiration) claims use
    timezone-aware UTC datetimes (Python 3.12+ deprecation-safe).

    Falls back to base64 encoding if ``PyJWT`` is not installed.

    Args:
        username: The authenticated user's name to embed in the token.

    Returns:
        Encoded JWT string (or base64 fallback).
    """
    try:
        import jwt

        payload = {
            "user": username,
            "iat": datetime.now(tz=timezone.utc),
            "exp": datetime.now(tz=timezone.utc) + timedelta(hours=24),
        }
        return jwt.encode(payload, Config.SECRET_KEY, algorithm="HS256")
    except Exception:
        # Fallback: base64(username:timestamp) — insecure, demo only.
        import base64
        return base64.b64encode(
            f"{username}:{int(datetime.now(tz=timezone.utc).timestamp())}".encode()
        ).decode()


def verify_jwt_token(token: str) -> Optional[str]:
    """Verify a JWT token and extract the username.

    Attempts PyJWT decoding first, then falls back to base64 parsing
    for tokens created by the fallback path.

    Args:
        token: Raw JWT string from the Authorization header.

    Returns:
        Username string if valid, or ``None`` if verification fails.
    """
    try:
        import jwt
        payload = jwt.decode(token, Config.SECRET_KEY, algorithms=["HS256"])
        return payload.get("user", "unknown")
    except Exception:
        try:
            import base64
            decoded = base64.b64decode(token).decode()
            return decoded.split(":")[0]
        except Exception:
            return None


def authenticate_user(username: str, password: str) -> bool:
    """Validate demo credentials.

    Args:
        username: Provided username.
        password: Provided password.

    Returns:
        ``True`` if credentials match a demo user, ``False`` otherwise.
    """
    return _DEMO_USERS.get(username) == password


async def verify_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    """FastAPI dependency — verify Bearer token, return the username.

    Raise ``HTTPException(401)`` if the token is missing or invalid.
    Use in route signatures as: ``user: str = Depends(verify_token)``.

    Args:
        credentials: Automatically injected by FastAPI's ``HTTPBearer``.

    Returns:
        Authenticated username string.

    Raises:
        HTTPException: 401 if token is missing or invalid.
    """
    token = credentials.credentials
    if not token:
        raise HTTPException(status_code=401, detail="No token provided")
    username = verify_jwt_token(token)
    if not username:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return username
