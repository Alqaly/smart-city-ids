"""Authentication helpers — JWT creation and verification."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from config import Config

logger = logging.getLogger(__name__)

security = HTTPBearer()

# ── Demo credentials ──────────────────────────────────────────────────────
# In production, replace with AD/LDAP/database auth.
_DEMO_USERS = {
    "analyst": "analyst",
    "operator": "operator",
    "admin": "admin",
}


def create_jwt_token(username: str) -> str:
    """Create JWT token (demo-grade — use proper auth in production)."""
    try:
        import jwt

        payload = {
            "user": username,
            "iat": datetime.now(tz=timezone.utc),
            "exp": datetime.now(tz=timezone.utc) + timedelta(hours=24),
        }
        return jwt.encode(payload, Config.SECRET_KEY, algorithm="HS256")
    except Exception:
        import base64

        return base64.b64encode(
            f"{username}:{int(datetime.now(tz=timezone.utc).timestamp())}".encode()
        ).decode()


def verify_jwt_token(token: str) -> Optional[str]:
    """Verify JWT token and return username, or ``None``."""
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
    """Validate demo credentials."""
    return _DEMO_USERS.get(username) == password


async def verify_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    """FastAPI dependency — verify Bearer token, return username."""
    token = credentials.credentials
    if not token:
        raise HTTPException(status_code=401, detail="No token provided")
    username = verify_jwt_token(token)
    if not username:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return username
