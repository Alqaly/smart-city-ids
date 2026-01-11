"""
Security module for Smart City IDS - Capstone 2 Phase 1
Implements: JWT authentication, RBAC, and token management
"""

from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, List
import os

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
import logging

logger = logging.getLogger(__name__)

# Configuration
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-secret-key-change-in-production")
JWT_EXPIRATION_HOURS = int(os.getenv("JWT_EXPIRATION_HOURS", "24"))
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Security scheme
security = HTTPBearer()


class Role(str, Enum):
    """User roles for RBAC"""
    ADMIN = "admin"
    ANALYST = "analyst"
    MONITOR = "monitor"
    SERVICE = "service"


class TokenData:
    """Token payload data"""
    def __init__(self, sub: str, role: Role, exp: datetime, permissions: List[str] = None):
        self.sub = sub  # User/service ID
        self.role = role
        self.exp = exp
        self.permissions = permissions or []
        self.created_at = datetime.utcnow()

    def is_expired(self) -> bool:
        """Check if token is expired"""
        return datetime.utcnow() > self.exp

    def has_permission(self, permission: str) -> bool:
        """Check if user has specific permission"""
        return permission in self.permissions or self.role == Role.ADMIN


def hash_password(password: str) -> str:
    """Hash password using bcrypt"""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against hash"""
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(
    data: dict,
    expires_delta: Optional[timedelta] = None
) -> str:
    """Create JWT access token"""
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    
    try:
        encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
        logger.info(f"Token created for user: {data.get('sub')}")
        return encoded_jwt
    except Exception as e:
        logger.error(f"Failed to create token: {e}")
        raise HTTPException(status_code=500, detail="Failed to create token")


async def verify_token(credentials: HTTPAuthCredentials) -> TokenData:
    """Verify JWT token and extract claims"""
    token = credentials.credentials
    
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        sub: str = payload.get("sub")
        role: str = payload.get("role", Role.MONITOR.value)
        exp: int = payload.get("exp")
        permissions: List[str] = payload.get("permissions", [])
        
        if sub is None:
            logger.warning("Token missing subject claim")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing subject",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        exp_datetime = datetime.utcfromtimestamp(exp)
        token_data = TokenData(sub=sub, role=Role(role), exp=exp_datetime, permissions=permissions)
        
        if token_data.is_expired():
            logger.warning(f"Token expired for user: {sub}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token expired",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        logger.info(f"Token verified for user: {sub} with role: {role}")
        return token_data
        
    except JWTError as e:
        logger.error(f"JWT verification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


def require_role(*roles: Role):
    """Dependency: Require specific role(s)"""
    async def check_role(token: TokenData = Depends(verify_token)) -> TokenData:
        if token.role not in roles:
            logger.warning(f"User {token.sub} with role {token.role} denied access (required: {roles})")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions"
            )
        return token
    return check_role


def require_permission(permission: str):
    """Dependency: Require specific permission"""
    async def check_permission(token: TokenData = Depends(verify_token)) -> TokenData:
        if not token.has_permission(permission):
            logger.warning(f"User {token.sub} denied permission: {permission}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required permission: {permission}"
            )
        return token
    return check_permission


async def get_current_user(token: TokenData = Depends(verify_token)) -> TokenData:
    """Get current authenticated user"""
    return token


# Role-based permissions mapping
ROLE_PERMISSIONS = {
    Role.ADMIN: [
        "alert:read", "alert:write", "alert:delete",
        "analysis:read", "analysis:write",
        "automation:read", "automation:write", "automation:execute",
        "user:read", "user:write", "user:delete",
        "system:read", "system:write", "system:admin"
    ],
    Role.ANALYST: [
        "alert:read", "alert:write",
        "analysis:read", "analysis:write",
        "automation:read", "automation:execute"
    ],
    Role.MONITOR: [
        "alert:read",
        "analysis:read",
        "automation:read"
    ],
    Role.SERVICE: [
        "alert:write",  # Services can submit alerts
    ]
}


def get_role_permissions(role: Role) -> List[str]:
    """Get permissions for a specific role"""
    return ROLE_PERMISSIONS.get(role, [])
