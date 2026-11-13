"""
RescueNet Authentication Middleware & FastAPI Dependencies.

Provides JWT session extraction (from Authorization header, HttpOnly cookie, or query param),
Argon2id password verification, revocation checks, and Role-Based Access Control (RBAC).
"""

from __future__ import annotations
from typing import Dict, Any, Optional, List, Set, Union
from fastapi import Request, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from auth.tokens import verify_access_token
from auth.database import (
    get_user_by_id,
    is_token_revoked,
    ROLE_ADMIN,
    ROLE_COORDINATOR,
    ROLE_RESPONDER,
    VALID_ROLES,
)

# Optional HTTPBearer scheme so Swagger UI shows Authorize button
security_bearer = HTTPBearer(auto_error=False)


def extract_token_from_request(
    request: Request,
    auth_header: Optional[HTTPAuthorizationCredentials] = None,
) -> Optional[str]:
    """
    Extract token from:
    1. Authorization: Bearer <token>
    2. Cookie: rescuenet_token
    3. Query parameter: ?token=<token>
    """
    # 1. Check HTTPBearer scheme
    if auth_header and auth_header.credentials:
        return auth_header.credentials.strip()

    # 2. Check direct Authorization header
    auth_raw = request.headers.get("Authorization") or request.headers.get("authorization")
    if auth_raw and auth_raw.startswith("Bearer "):
        token = auth_raw[7:].strip()
        if token:
            return token

    # 3. Check cookies (HttpOnly cookie for browsers)
    cookie_token = request.cookies.get("rescuenet_token")
    if cookie_token:
        return cookie_token.strip()

    # 4. Check query parameter (e.g. for media downloads or WebSocket handshakes)
    query_token = request.query_params.get("token")
    if query_token:
        return query_token.strip()

    return None


async def get_current_user(
    request: Request,
    auth_header: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer),
) -> Dict[str, Any]:
    """
    FastAPI dependency that enforces authentication.
    Raises HTTP 401 if token is missing, invalid, expired, or revoked.
    """
    token = extract_token_from_request(request, auth_header)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please log in.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = verify_access_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    jti = payload.get("jti")
    if jti and is_token_revoked(jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has been terminated. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed session token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = get_user_by_id(user_id)
    if not user or not user.get("is_active"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is inactive or disabled.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return {
        "id": user["id"],
        "username": user["username"],
        "role": user["role"],
        "full_name": user["full_name"],
        "token_jti": jti,
        "token": token,
    }


async def get_optional_current_user(
    request: Request,
    auth_header: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer),
) -> Optional[Dict[str, Any]]:
    """
    Optional authentication dependency.
    Returns user dict if valid token is provided, or None if unauthenticated.
    """
    try:
        return await get_current_user(request, auth_header)
    except HTTPException:
        return None


def require_role(allowed_roles: Union[List[str], Set[str]]):
    """
    Factory creating a dependency that verifies the user has one of the allowed roles.
    Raises HTTP 403 Forbidden if user role is insufficient.
    """
    allowed_set = set(allowed_roles)

    async def role_dependency(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
        user_role = current_user.get("role")
        if user_role not in allowed_set:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access forbidden: Role '{user_role}' does not have sufficient permission for this resource. Required: {sorted(list(allowed_set))}",
            )
        return current_user

    return role_dependency


# Pre-configured role dependencies
require_admin = require_role([ROLE_ADMIN])
require_coordinator = require_role([ROLE_ADMIN, ROLE_COORDINATOR])
require_responder = require_role([ROLE_ADMIN, ROLE_COORDINATOR, ROLE_RESPONDER])


def verify_ws_token(token: Optional[str]) -> Optional[Dict[str, Any]]:
    """
    Verify authentication token for WebSocket handshakes.
    Returns decoded user dict or None.
    """
    if not token:
        return None
    payload = verify_access_token(token)
    if not payload:
        return None
    jti = payload.get("jti")
    if jti and is_token_revoked(jti):
        return None
    user = get_user_by_id(payload.get("sub", ""))
    if not user or not user.get("is_active"):
        return None
    return {
        "id": user["id"],
        "username": user["username"],
        "role": user["role"],
        "full_name": user["full_name"],
    }
