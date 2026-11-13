"""
RescueNet Authentication Cryptography Module.

Provides military-grade password hashing using Argon2id (from cryptography library),
secure salt generation, constant-time verification, and password strength validation.
Never stores or logs plaintext passwords.
"""

from __future__ import annotations
import hmac
import os
import re
from typing import Tuple
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id
from cryptography.exceptions import InvalidKey


# Argon2id Parameters (RFC 9106 recommended parameters for sensitive systems)
ARGON2_TIME_COST = 2        # 2 iterations
ARGON2_MEMORY_COST = 65536  # 64 MB RAM
ARGON2_PARALLELISM = 4     # 4 lanes / threads
ARGON2_HASH_LEN = 32       # 256-bit derived key
ARGON2_SALT_LEN = 16       # 128-bit cryptographically secure salt


def validate_password_strength(password: str) -> Tuple[bool, str]:
    """
    Enforce strong password policy for emergency response operators:
    - Minimum 8 characters
    - At least one uppercase or lowercase letter
    - At least one numeric digit
    """
    if not password or len(password) < 8:
        return False, "Password must be at least 8 characters long."
    if not re.search(r"[a-zA-Z]", password):
        return False, "Password must contain at least one letter."
    if not re.search(r"[0-9]", password):
        return False, "Password must contain at least one digit."
    return True, "Password meets strength requirements."


def hash_password(password: str) -> str:
    """
    Securely hash a plaintext password using Argon2id with a unique 128-bit random salt.
    Returns standard serialized hash string:
    $argon2id$v=19$m=65536,t=2,p=4$<salt_hex>$<hash_hex>
    """
    if not password:
        raise ValueError("Password cannot be empty")

    salt = os.urandom(ARGON2_SALT_LEN)
    kdf = Argon2id(
        salt=salt,
        length=ARGON2_HASH_LEN,
        iterations=ARGON2_TIME_COST,
        lanes=ARGON2_PARALLELISM,
        memory_cost=ARGON2_MEMORY_COST,
    )
    derived = kdf.derive(password.encode("utf-8"))
    
    salt_hex = salt.hex()
    hash_hex = derived.hex()
    return f"$argon2id$v=19$m={ARGON2_MEMORY_COST},t={ARGON2_TIME_COST},p={ARGON2_PARALLELISM}${salt_hex}${hash_hex}"


def verify_password(password: str, stored_hash: str) -> bool:
    """
    Verify a plaintext password against a stored Argon2id hash using constant-time comparison.
    Safely rejects malformed hashes without raising unhandled exceptions.
    """
    if not password or not stored_hash:
        return False

    try:
        parts = stored_hash.split("$")
        # Format: ["", "argon2id", "v=19", "m=...,t=...,p=...", salt_hex, hash_hex]
        if len(parts) != 6 or parts[1] != "argon2id":
            return False

        params_str = parts[3]
        params = dict(item.split("=") for item in params_str.split(","))
        memory_cost = int(params.get("m", ARGON2_MEMORY_COST))
        iterations = int(params.get("t", ARGON2_TIME_COST))
        lanes = int(params.get("p", ARGON2_PARALLELISM))

        salt = bytes.fromhex(parts[4])
        expected_hash = bytes.fromhex(parts[5])

        kdf = Argon2id(
            salt=salt,
            length=len(expected_hash),
            iterations=iterations,
            lanes=lanes,
            memory_cost=memory_cost,
        )
        # Constant-time verification
        kdf.verify(password.encode("utf-8"), expected_hash)
        return True
    except (InvalidKey, ValueError, IndexError, KeyError):
        return False
