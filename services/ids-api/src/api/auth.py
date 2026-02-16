"""
Authentication API Router
=========================

Provides JWT-based authentication endpoints for the Smart City IDS
operator dashboard.  This module implements a minimal but functional
authentication flow intended for academic demonstration and local
deployment scenarios:

1. **Login** — The client (browser dashboard) sends a username/password
   pair to ``POST /api/auth/login``.  If the credentials match one of
   the pre-configured demo accounts the server returns a signed JWT
   bearer token.
2. **Logout** — ``POST /api/auth/logout`` is a no-op on the server
   side because JWTs are stateless; the client simply discards the
   token.  A production system would maintain a token blacklist or use
   short-lived tokens with a refresh mechanism.

Demo credentials (configured in ``infrastructure/auth.py``):
    * ``analyst`` / ``analyst`` — read-only security analyst role
    * ``operator`` / ``operator`` — full operator privileges

Security note:
    The credentials and JWT secret are hard-coded for the capstone
    demonstration.  In a production deployment they would be replaced
    with an external identity provider (e.g., OAuth 2.0 / OIDC).
"""

from fastapi import APIRouter, Request

from infrastructure.auth import (
    authenticate_user,
    create_jwt_token,
)
from models.auth import LoginRequest, LoginResponse

# ── Router instance registered by the main FastAPI application at startup ──
router = APIRouter(tags=["auth"])


@router.post("/api/auth/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """Authenticate a security analyst and return a JWT bearer token.

    The endpoint validates the supplied ``username`` and ``password``
    against the built-in demo credential store (see
    ``infrastructure.auth.authenticate_user``).  On success it mints a
    JWT with ``create_jwt_token`` and returns it inside a
    ``LoginResponse`` envelope so the dashboard can attach it to
    subsequent API calls via the ``Authorization: Bearer <token>``
    header.

    Demo credentials:
        * ``analyst``  / ``analyst``
        * ``operator`` / ``operator``

    Args:
        request: A ``LoginRequest`` Pydantic model containing
            ``username`` and ``password`` fields.

    Returns:
        A ``LoginResponse`` with ``access_token``, ``token_type``
        (always ``"bearer"``), and the authenticated ``user`` name.

    Raises:
        HTTPException(401): If the credentials are invalid.
    """
    # Verify credentials against the demo user store
    if authenticate_user(request.username, request.password):
        # Mint a signed JWT containing the username claim
        token = create_jwt_token(request.username)
        return LoginResponse(
            access_token=token, token_type="bearer", user=request.username
        )
    # Import here to keep the happy-path import footprint minimal
    from fastapi import HTTPException

    raise HTTPException(status_code=401, detail="Invalid credentials")


@router.post("/api/auth/logout")
async def logout(request: Request):
    """Log out the current operator session (client-side invalidation).

    Because the IDS uses stateless JWT tokens there is no server-side
    session to destroy.  This endpoint exists so that the dashboard UI
    has a conventional logout target; the client is expected to discard
    the stored token upon receiving the success response.

    In a production deployment this would add the token's ``jti`` to a
    revocation list or rely on short token lifetimes combined with a
    refresh-token rotation scheme.

    Returns:
        A simple JSON acknowledgement message.
    """
    return {"message": "Logged out successfully"}
