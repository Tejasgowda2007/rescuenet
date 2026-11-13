"""
RescueNet Authentication REST API Routes.

Implements:
- POST /api/auth/login (Argon2id verification, brute-force rate-limiting, JWT & HttpOnly cookie)
- POST /api/auth/logout (Revocation list blacklisting & cookie deletion)
- GET  /api/auth/me (Current user context & role check)
- POST /api/auth/change-password (Self-service credential rotation)
- GET  /api/auth/users (Admin-only operator directory)
- POST /api/auth/users (Admin-only user provisioning)
"""

from __future__ import annotations
import os
import time
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from auth.crypto import verify_password, validate_password_strength
from auth.tokens import create_access_token, verify_access_token
from auth.database import (
    get_user_by_username,
    get_user_by_id,
    create_user,
    update_user_password,
    list_users,
    revoke_token,
    check_rate_limit,
    record_login_attempt,
    log_audit,
    ROLE_ADMIN,
    ROLE_COORDINATOR,
    ROLE_RESPONDER,
    VALID_ROLES,
)
from auth.middleware import get_current_user, require_admin

auth_router = APIRouter(prefix="/api/auth", tags=["Authentication"])


# --- Schemas ---

class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64, description="Operator callsign / username")
    password: str = Field(..., min_length=1, max_length=128, description="Operator password")


class UserResponse(BaseModel):
    id: str
    username: str
    role: str
    full_name: str
    created_at: Optional[float] = None
    is_active: Optional[int] = 1


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


class CreateUserRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=8, max_length=128)
    role: str = Field(default=ROLE_RESPONDER)
    full_name: str = Field(default="")


# --- Endpoints ---

@auth_router.post("/login", response_model=LoginResponse)
async def login(req: LoginRequest, request: Request, response: Response):
    """
    Authenticate emergency operator credentials with Argon2id and rate-limit protection.
    Issues a cryptographically signed HMAC-SHA256 JWT and sets a secure HttpOnly cookie.
    """
    client_ip = request.client.host if request.client else "unknown"
    username = req.username.strip()

    # 1. Check brute force rate limit for both username and client IP
    is_limited_user, remain_user = check_rate_limit(username)
    is_limited_ip, remain_ip = check_rate_limit(client_ip)

    if is_limited_user or is_limited_ip:
        remain = max(remain_user, remain_ip)
        log_audit("LOGIN_LOCKED_OUT", username=username, ip_address=client_ip, details=f"Wait {remain}s")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many failed login attempts. Security lockout active. Please retry in {remain} seconds.",
        )

    # 2. Look up user
    user = get_user_by_username(username)
    if not user or not verify_password(req.password, user["password_hash"]):
        # Record failure for both username and IP
        record_login_attempt(username, False)
        record_login_attempt(client_ip, False)
        log_audit("LOGIN_FAILED", username=username, ip_address=client_ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 3. Check account status
    if not user.get("is_active"):
        record_login_attempt(username, False)
        log_audit("LOGIN_INACTIVE_USER", user_id=user["id"], username=username, ip_address=client_ip)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled. Contact system administrator.",
        )

    # 4. Successful login
    record_login_attempt(username, True)
    record_login_attempt(client_ip, True)
    log_audit("LOGIN_SUCCESS", user_id=user["id"], username=username, ip_address=client_ip)

    token = create_access_token(
        user_id=user["id"],
        username=user["username"],
        role=user["role"],
        full_name=user["full_name"],
    )

    # Set secure HttpOnly cookie for web browser session handling
    # SameSite=Lax protects against CSRF while allowing seamless top-level navigation
    # Secure=True if in HTTPS, False for offline LAN/HTTP operation
    is_https = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
    response.set_cookie(
        key="rescuenet_token",
        value=token,
        httponly=True,
        samesite="lax",
        secure=is_https,
        max_age=8 * 3600,
        path="/",
    )

    user_data = UserResponse(
        id=user["id"],
        username=user["username"],
        role=user["role"],
        full_name=user["full_name"],
        created_at=user["created_at"],
        is_active=user["is_active"],
    )

    return LoginResponse(access_token=token, token_type="bearer", user=user_data)


@auth_router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Revoke current JWT session and clear session cookies.
    """
    token_jti = current_user.get("token_jti")
    if token_jti:
        # Revoke token with 8h expiration window
        revoke_token(token_jti, time.time() + 8 * 3600)

    # Delete session cookie
    response.delete_cookie(key="rescuenet_token", path="/")

    client_ip = request.client.host if request.client else "unknown"
    log_audit("LOGOUT", user_id=current_user["id"], username=current_user["username"], ip_address=client_ip)

    return {"status": "success", "message": "Session terminated successfully"}


@auth_router.get("/me")
async def get_me(current_user: Dict[str, Any] = Depends(get_current_user)):
    """
    Get profile information and active role permissions for the currently authenticated operator.
    """
    return {
        "user": {
            "id": current_user["id"],
            "username": current_user["username"],
            "role": current_user["role"],
            "full_name": current_user["full_name"],
        }
    }


@auth_router.post("/change-password")
async def change_password(
    req: ChangePasswordRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Change password for the authenticated operator with old password verification.
    """
    user = get_user_by_id(current_user["id"])
    if not user:
        raise HTTPException(status_code=404, detail="User account not found")

    if not verify_password(req.old_password, user["password_hash"]):
        raise HTTPException(status_code=400, detail="Current password incorrect")

    valid, err_msg = validate_password_strength(req.new_password)
    if not valid:
        raise HTTPException(status_code=400, detail=err_msg)

    update_user_password(user["id"], req.new_password)
    log_audit("PASSWORD_CHANGED", user_id=user["id"], username=user["username"])

    return {"status": "success", "message": "Password updated successfully"}


@auth_router.get("/users", response_model=List[UserResponse])
async def get_all_users(admin: Dict[str, Any] = Depends(require_admin)):
    """
    List all registered operators and their assigned roles (Admin only).
    """
    users = list_users()
    return [
        UserResponse(
            id=u["id"],
            username=u["username"],
            role=u["role"],
            full_name=u["full_name"],
            created_at=u["created_at"],
            is_active=u["is_active"],
        )
        for u in users
    ]


@auth_router.post("/users", response_model=UserResponse)
async def provision_user(
    req: CreateUserRequest,
    admin: Dict[str, Any] = Depends(require_admin),
):
    """
    Provision a new operator account with specific RBAC role (Admin only).
    """
    try:
        new_user = create_user(
            username=req.username,
            password=req.password,
            role=req.role,
            full_name=req.full_name,
        )
        log_audit(
            "USER_CREATED",
            user_id=admin["id"],
            username=admin["username"],
            details=f"Created {new_user['username']} ({new_user['role']})",
        )
        return UserResponse(**new_user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
