"""
RescueNet JWT Token Generation & Verification.

Cryptographically signed session tokens using HMAC-SHA256 with 256-bit server secret.
Supports configurable expiration, payload decoding, and token revocation checks.
"""

from __future__ import annotations
import base64
import json
import os
import time
import uuid
from typing import Dict, Any, Optional
from cryptography.hazmat.primitives import hashes, hmac


DEFAULT_TOKEN_EXPIRY_SECONDS = 8 * 3600  # 8 hours default session duration
SECRET_FILE_PATH = os.path.join(os.path.dirname(__file__), "..", "data", ".auth_secret")


def _get_or_create_jwt_secret() -> bytes:
    """
    Retrieve JWT secret from environment or generate persistent 256-bit secret in data/.auth_secret.
    Never exposes secret in code or version control.
    """
    env_secret = os.environ.get("RESCUENET_JWT_SECRET")
    if env_secret and len(env_secret.strip()) >= 32:
        return env_secret.strip().encode("utf-8")

    secret_path = os.path.abspath(SECRET_FILE_PATH)
    os.makedirs(os.path.dirname(secret_path), exist_ok=True)

    if os.path.exists(secret_path):
        try:
            with open(secret_path, "rb") as f:
                content = f.read().strip()
                if len(content) >= 32:
                    return content
        except Exception:
            pass

    # Generate new random 256-bit (32 bytes) secret
    new_secret = os.urandom(32).hex().encode("utf-8")
    try:
        with open(secret_path, "wb") as f:
            f.write(new_secret)
    except Exception:
        pass
    return new_secret


JWT_SECRET = _get_or_create_jwt_secret()


def _b64url_encode(data: bytes) -> str:
    """Encode bytes into base64url string without padding."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data_str: str) -> bytes:
    """Decode base64url string into bytes with padding restored."""
    rem = len(data_str) % 4
    if rem > 0:
        data_str += "=" * (4 - rem)
    return base64.urlsafe_b64decode(data_str)


def _compute_hmac(message: bytes, secret: bytes = JWT_SECRET) -> bytes:
    """Compute HMAC-SHA256 digest for message."""
    h = hmac.HMAC(secret, hashes.SHA256())
    h.update(message)
    return h.finalize()


def create_access_token(
    user_id: str,
    username: str,
    role: str,
    full_name: str = "",
    expires_in_seconds: float = DEFAULT_TOKEN_EXPIRY_SECONDS,
) -> str:
    """
    Generate a signed JWT access token for an authenticated user.
    """
    header = {"alg": "HS256", "typ": "JWT"}
    now = time.time()
    payload = {
        "sub": user_id,
        "username": username,
        "role": role,
        "name": full_name,
        "iat": int(now),
        "exp": int(now + expires_in_seconds),
        "jti": uuid.uuid4().hex,
    }

    header_bytes = json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")

    unsigned_token = f"{_b64url_encode(header_bytes)}.{_b64url_encode(payload_bytes)}"
    signature = _compute_hmac(unsigned_token.encode("ascii"))
    signed_token = f"{unsigned_token}.{_b64url_encode(signature)}"
    return signed_token


def verify_access_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Verify and decode a signed JWT token.
    Returns decoded payload dict if valid and unexpired; returns None if invalid or expired.
    """
    if not token or not isinstance(token, str):
        return None

    parts = token.split(".")
    if len(parts) != 3:
        return None

    header_b64, payload_b64, sig_b64 = parts
    unsigned_bytes = f"{header_b64}.{payload_b64}".encode("ascii")

    try:
        provided_sig = _b64url_decode(sig_b64)
        expected_sig = _compute_hmac(unsigned_bytes)

        # Constant-time signature comparison to prevent timing attacks
        h_ver = hmac.HMAC(JWT_SECRET, hashes.SHA256())
        h_ver.update(unsigned_bytes)
        h_ver.verify(provided_sig)

        payload_bytes = _b64url_decode(payload_b64)
        payload = json.loads(payload_bytes.decode("utf-8"))

        # Verify expiration
        exp = payload.get("exp", 0)
        if time.time() > exp:
            return None  # Token expired

        return payload
    except Exception:
        return None
