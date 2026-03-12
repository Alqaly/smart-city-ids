"""Authentication request and response Pydantic models.

These models define the JSON contract for the ``POST /api/login``
endpoint.  The login flow is demo-grade — see ``infrastructure.auth``
for credential validation details.
"""

from pydantic import BaseModel


class LoginRequest(BaseModel):
    """Login request body — username and password.

    Example::

        {"username": "analyst", "password": "analyst"}
    """

    username: str  # Demo users: analyst, operator, admin.
    password: str  # Plaintext password (research prototype — use hashing in production).


class LoginResponse(BaseModel):
    """Login response — contains the JWT bearer token.

    Example::

        {"access_token": "eyJ...", "token_type": "bearer", "user": "analyst"}
    """

    access_token: str           # Signed HS256 JWT (24-hour expiry).
    token_type: str = "bearer"  # Always "bearer" per OAuth2 convention.
    user: str                   # Authenticated username echoed back.
