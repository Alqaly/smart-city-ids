"""Authentication API router."""

from fastapi import APIRouter, Request

from infrastructure.auth import (
    authenticate_user,
    create_jwt_token,
)
from models.auth import LoginRequest, LoginResponse

router = APIRouter(tags=["auth"])


@router.post("/api/auth/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """Authenticate security analyst and return JWT token.

    Demo credentials:
    - analyst / analyst
    - operator / operator
    """
    if authenticate_user(request.username, request.password):
        token = create_jwt_token(request.username)
        return LoginResponse(
            access_token=token, token_type="bearer", user=request.username
        )
    from fastapi import HTTPException

    raise HTTPException(status_code=401, detail="Invalid credentials")


@router.post("/api/auth/logout")
async def logout(request: Request):
    """Logout operator (invalidate token on client side)."""
    return {"message": "Logged out successfully"}
