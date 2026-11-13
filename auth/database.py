"""
RescueNet Authentication Database & User Store.

Manages persistent SQLite storage in data/auth.db for:
- User accounts and roles (ADMIN, COORDINATOR, RESPONDER)
- Argon2id password hashes
- Token revocation list (blacklist)
- Brute-force rate limiting and login audit logs
- Secure initial administrator provisioning
"""

from __future__ import annotations
import os
import sqlite3
import time
import uuid
import secrets
from typing import Dict, Any, Optional, List, Tuple
from auth.crypto import hash_password, verify_password, validate_password_strength

DEFAULT_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "auth.db")
AUTH_DB_PATH = os.environ.get("RESCUENET_AUTH_DB_PATH", DEFAULT_DB_PATH)

# Role definitions
ROLE_ADMIN = "ADMIN"
ROLE_COORDINATOR = "COORDINATOR"
ROLE_RESPONDER = "RESPONDER"
VALID_ROLES = {ROLE_ADMIN, ROLE_COORDINATOR, ROLE_RESPONDER}

# Rate limiting parameters
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_WINDOW_SECONDS = 300  # 5 minutes


def get_db_path() -> str:
    current_path = os.environ.get("RESCUENET_AUTH_DB_PATH", DEFAULT_DB_PATH)
    path = os.path.abspath(current_path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(get_db_path(), timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    """Initialize SQLite database tables for authentication and security auditing."""
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT UNIQUE NOT NULL COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                full_name TEXT NOT NULL,
                created_at REAL NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS revoked_tokens (
                jti TEXT PRIMARY KEY,
                revoked_at REAL NOT NULL,
                expires_at REAL NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS login_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                identifier TEXT NOT NULL,
                attempted_at REAL NOT NULL,
                success INTEGER NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                user_id TEXT,
                username TEXT,
                action TEXT NOT NULL,
                ip_address TEXT,
                details TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_revoked_expires ON revoked_tokens(expires_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_login_attempts_id_time ON login_attempts(identifier, attempted_at)")
        conn.commit()


def init_admin_account() -> Optional[Dict[str, str]]:
    """
    Ensure an initial administrator account exists.
    If an admin already exists, DOES NOT OVERWRITE OR RECREATE.
    Returns dict with credentials only if a brand-new admin was generated.
    """
    init_db()
    with get_connection() as conn:
        cursor = conn.execute("SELECT id, username FROM users WHERE role = ?", (ROLE_ADMIN,))
        existing_admin = cursor.fetchone()
        if existing_admin:
            # Admin already exists; preserve existing account
            return None

        # No admin exists. Create initial administrator.
        admin_username = os.environ.get("RESCUENET_ADMIN_USER", "admin").strip()
        if not admin_username:
            admin_username = "admin"

        admin_password = os.environ.get("RESCUENET_ADMIN_PASSWORD")
        was_generated = False

        if not admin_password:
            # Generate a strong, secure 16-character password with letters, digits, and special chars
            token = secrets.token_urlsafe(12)
            admin_password = f"Rnet!{token}9"
            was_generated = True

        valid, err = validate_password_strength(admin_password)
        if not valid:
            # If user provided a weak env password, append standard requirement
            admin_password = admin_password + "R1!"

        pw_hash = hash_password(admin_password)
        admin_id = str(uuid.uuid4())
        now = time.time()

        conn.execute(
            """
            INSERT INTO users (id, username, password_hash, role, full_name, created_at, is_active)
            VALUES (?, ?, ?, ?, ?, ?, 1)
            """,
            (admin_id, admin_username, pw_hash, ROLE_ADMIN, "System Administrator", now),
        )
        conn.commit()

        # If password was generated, write to local credentials file with note to rotate
        if was_generated:
            creds_path = os.path.join(os.path.dirname(get_db_path()), "INITIAL_ADMIN_CREDENTIALS.txt")
            try:
                with open(creds_path, "w", encoding="utf-8") as f:
                    f.write("=== RESCUENET INITIAL ADMINISTRATOR CREDENTIALS ===\n")
                    f.write(f"Username: {admin_username}\n")
                    f.write(f"Password: {admin_password}\n")
                    f.write(f"Role: {ROLE_ADMIN}\n")
                    f.write("IMPORTANT: Change this password immediately after logging in.\n")
                    f.write("Do not commit this file to version control.\n")
            except Exception:
                pass

        return {
            "username": admin_username,
            "password": admin_password,
            "generated": was_generated,
        }


def check_rate_limit(identifier: str) -> Tuple[bool, int]:
    """
    Check if the identifier (username or IP) is rate limited.
    Returns (is_limited, seconds_remaining).
    """
    now = time.time()
    window_start = now - LOCKOUT_WINDOW_SECONDS

    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT COUNT(*) as failed_count, MAX(attempted_at) as last_attempt
            FROM login_attempts
            WHERE identifier = ? AND success = 0 AND attempted_at >= ?
            """,
            (identifier.lower(), window_start),
        )
        row = cursor.fetchone()
        if not row or not row["failed_count"]:
            return False, 0

        failed_count = row["failed_count"]
        last_attempt = row["last_attempt"] or now

        if failed_count >= MAX_FAILED_ATTEMPTS:
            remaining = int((last_attempt + LOCKOUT_WINDOW_SECONDS) - now)
            if remaining > 0:
                return True, remaining
        return False, 0


def record_login_attempt(identifier: str, success: bool) -> None:
    """Record a login attempt for brute-force prevention and audit."""
    now = time.time()
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO login_attempts (identifier, attempted_at, success) VALUES (?, ?, ?)",
            (identifier.lower(), now, 1 if success else 0),
        )
        if success:
            # On successful login, clear previous failed attempts for this identifier
            conn.execute(
                "DELETE FROM login_attempts WHERE identifier = ? AND success = 0",
                (identifier.lower(),),
            )
        # Purge stale attempts older than 1 hour to keep database compact
        conn.execute("DELETE FROM login_attempts WHERE attempted_at < ?", (now - 3600,))
        conn.commit()


def log_audit(
    action: str,
    user_id: Optional[str] = None,
    username: Optional[str] = None,
    ip_address: Optional[str] = None,
    details: Optional[str] = None,
) -> None:
    """Append a security audit record."""
    now = time.time()
    try:
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO audit_log (timestamp, user_id, username, action, ip_address, details)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (now, user_id, username, action, ip_address, details),
            )
            conn.commit()
    except Exception:
        pass


def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    """Fetch user by username (case-insensitive)."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT id, username, password_hash, role, full_name, created_at, is_active FROM users WHERE username = ?",
            (username.strip(),),
        )
        row = cursor.fetchone()
        if row:
            return dict(row)
    return None


def get_user_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    """Fetch user by primary key ID."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT id, username, password_hash, role, full_name, created_at, is_active FROM users WHERE id = ?",
            (user_id,),
        )
        row = cursor.fetchone()
        if row:
            return dict(row)
    return None


def create_user(
    username: str,
    password: str,
    role: str = ROLE_RESPONDER,
    full_name: str = "",
) -> Dict[str, Any]:
    """Create a new operator account."""
    username = username.strip().lower()
    if not username:
        raise ValueError("Username cannot be empty")
    if len(username) < 3:
        raise ValueError("Username must be at least 3 characters")
    if role not in VALID_ROLES:
        raise ValueError(f"Invalid role '{role}'. Must be one of: {sorted(VALID_ROLES)}")

    valid, err_msg = validate_password_strength(password)
    if not valid:
        raise ValueError(err_msg)

    if get_user_by_username(username):
        raise ValueError(f"User '{username}' already exists")

    pw_hash = hash_password(password)
    user_id = str(uuid.uuid4())
    now = time.time()
    full_name = full_name.strip() or username.title()

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO users (id, username, password_hash, role, full_name, created_at, is_active)
            VALUES (?, ?, ?, ?, ?, ?, 1)
            """,
            (user_id, username, pw_hash, role, full_name, now),
        )
        conn.commit()

    return {
        "id": user_id,
        "username": username,
        "role": role,
        "full_name": full_name,
        "created_at": now,
        "is_active": 1,
    }


def update_user_password(user_id: str, new_password: str) -> None:
    """Update a user's password with strength validation and Argon2id rehashing."""
    valid, err_msg = validate_password_strength(new_password)
    if not valid:
        raise ValueError(err_msg)

    user = get_user_by_id(user_id)
    if not user:
        raise ValueError("User not found")

    new_hash = hash_password(new_password)
    with get_connection() as conn:
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, user_id))
        conn.commit()


def list_users() -> List[Dict[str, Any]]:
    """List all accounts (excluding password hashes)."""
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT id, username, role, full_name, created_at, is_active FROM users ORDER BY created_at ASC"
        )
        return [dict(r) for r in cursor.fetchall()]


def revoke_token(jti: str, expires_at: float) -> None:
    """Add a JWT ID to the revocation list."""
    now = time.time()
    with get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO revoked_tokens (jti, revoked_at, expires_at) VALUES (?, ?, ?)",
            (jti, now, expires_at),
        )
        # Clean up already-expired revocations to keep table small
        conn.execute("DELETE FROM revoked_tokens WHERE expires_at < ?", (now,))
        conn.commit()


def is_token_revoked(jti: str) -> bool:
    """Check if token ID has been revoked."""
    if not jti:
        return True
    with get_connection() as conn:
        cursor = conn.execute("SELECT 1 FROM revoked_tokens WHERE jti = ?", (jti,))
        return cursor.fetchone() is not None
