import os
from datetime import datetime, timedelta
from typing import Optional

from fastapi import HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from database import (
    db_get_user,
    db_list_users,
    db_create_user,
    db_update_user,
    db_delete_user,
    db_seed_initial_users
)

# ── Config ────────────────────────────────────────────────────────────────────

JWT_SECRET       = os.getenv("JWT_SECRET", "my-super-secure-jwt-key-32chars")
JWT_ALGORITHM    = "HS256"
JWT_EXPIRE_HOURS = int(os.getenv("JWT_EXPIRE_HOURS", "24"))
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
ROLE_RANK = {"viewer": 0, "operator": 1, "admin": 2}

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

def safe_password(password: str) -> str:
    """
    bcrypt only supports first 72 bytes.
    """
    return password.encode("utf-8")[:72].decode(
    "utf-8",
    errors="ignore",
    )

# ── User store ────────────────────────────────────────────────────────────────
# Loaded from env var USERS="username:plaintext_password:role,..."
# Passwords are bcrypt-hashed at load time so they're never compared as plaintext
# in hot paths.
# Fallback: admin user with password = API_SECRET value.

def _load_users() -> dict:
    users = {}

    raw = os.getenv("USERS", "")

    if raw:
        for entry in raw.split(","):
            parts = [p.strip() for p in entry.split(":")]

            if len(parts) == 3:
                username, password, role = parts

                if role not in ROLE_RANK:
                    role = "viewer"

                users[username] = {
                    "hashed_password": pwd_ctx.hash(
                        safe_password(password)
                    ),
                    "role": role,
                }

    if "admin" not in users:
        users["admin"] = {
            "hashed_password": pwd_ctx.hash(
                safe_password(ADMIN_PASSWORD)
            ),
            "role": "admin",
        }

    return users


USERS: dict = _load_users()

async def sync_users_from_db():
    """
    Seeds initial users into SQLite on startup and synchronizes
    the in-memory USERS cache with persistent DB records.
    """
    global USERS
    try:
        raw_env_users = os.getenv("USERS", "")
        await db_seed_initial_users(
            default_admin_password=ADMIN_PASSWORD,
            env_users_str=raw_env_users,
            pwd_hasher_fn=lambda p: pwd_ctx.hash(safe_password(p))
        )
        db_users = await db_list_users()
        new_users = {}
        for u in db_users:
            full = await db_get_user(u["username"])
            if full:
                new_users[full["username"]] = {
                    "hashed_password": full["password_hash"],
                    "role": full["role"],
                    "created_at": full.get("created_at"),
                    "updated_at": full.get("updated_at")
                }
        if "admin" not in new_users:
            new_users["admin"] = {
                "hashed_password": pwd_ctx.hash(safe_password(ADMIN_PASSWORD)),
                "role": "admin",
                "created_at": time.time(),
                "updated_at": time.time()
            }
        USERS = new_users
        print(f"[Auth] Successfully synced {len(USERS)} user accounts from persistent database.")
    except Exception as e:
        print(f"[Auth] Warning: Could not sync users from DB ({e}); falling back to env-based user store.")




# ── JWT helpers ───────────────────────────────────────────────────────────────

def create_token(username: str, role: str) -> dict:
    expire = datetime.utcnow() + timedelta(hours=JWT_EXPIRE_HOURS)
    payload = {
        "sub":  username,
        "role": role,
        "exp":  expire,
        "iat":  datetime.utcnow(),
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return {
        "access_token": token,
        "token_type":   "bearer",
        "expires_in":   JWT_EXPIRE_HOURS * 3600,
        "role":         role,
        "username":     username,
    }


def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if not payload.get("sub"):
            raise HTTPException(401, "Invalid token: missing subject")
        return payload
    except JWTError as e:
        raise HTTPException(401, f"Token invalid or expired: {e}")


def authenticate_user(
    username: str,
    password: str,
):
    user = USERS.get(username)

    if not user:
        return None

    if not pwd_ctx.verify(
        safe_password(password),
        user["hashed_password"],
    ):
        return None

    return {
        "username": username,
        "role": user["role"],
    }


# ── FastAPI dependencies ──────────────────────────────────────────────────────
# These are used directly in route functions as Depends(...)

# HTTPBearer reads "Authorization: Bearer <token>" — shows lock icon in Swagger
_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> dict:
    """
    Dependency: validates Bearer JWT, returns {"sub": "alice", "role": "admin"}.
    Use in any route:  user = Depends(get_current_user)
    """
    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated. Click 'Authorize' in Swagger and enter your Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return decode_token(credentials.credentials)


def require_role(minimum_role: str):
    """
    Dependency factory enforcing a minimum RBAC role.
    Use:  user = Depends(require_role("operator"))
    """
    def _check(user: dict = Depends(get_current_user)) -> dict:
        user_rank    = ROLE_RANK.get(user.get("role", ""), -1)
        required_rank = ROLE_RANK.get(minimum_role, 99)
        if user_rank < required_rank:
            raise HTTPException(
                status_code=403,
                detail=f"Your role '{user.get('role')}' cannot perform this action. "
                       f"Required: '{minimum_role}' or higher.",
            )
        return user
    return _check


# Convenience aliases so routes read naturally
require_viewer   = Depends(require_role("viewer"))
require_operator = Depends(require_role("operator"))
require_admin    = Depends(require_role("admin"))


# ── Global JWT middleware ─────────────────────────────────────────────────────
# Blocks all non-public routes before they even hit the router.
# Routes use Depends(require_role(...)) for fine-grained RBAC on top of this.

class JWTMiddleware(BaseHTTPMiddleware):

    # Slave agents + Swagger UI + login bypass token check entirely
    PUBLIC_PREFIXES = (
        "/health",
        "/auth/",
        "/slaves/register",
        "/slaves/heartbeat",
        "/slaves/logs",
        "/slaves/events",
        "/slaves/stats",
        "/ws",
        "/docs",
        "/openapi.json",
        "/redoc",
    )

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        if request.method == "OPTIONS" or any(path.startswith(p) for p in self.PUBLIC_PREFIXES):
            return await call_next(request)

        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={
                    "detail": "Not authenticated. Use 'Authorize' in Swagger UI or pass "
                              "'Authorization: Bearer <token>' header."
                },
            )

        try:
            payload = jwt.decode(auth[7:], JWT_SECRET, algorithms=[JWT_ALGORITHM])
            request.state.user = payload.get("sub", "unknown")
            request.state.role = payload.get("role", "viewer")
        except JWTError as e:
            return JSONResponse(
                status_code=401,
                content={"detail": f"Token invalid or expired: {e}"},
            )

        return await call_next(request)