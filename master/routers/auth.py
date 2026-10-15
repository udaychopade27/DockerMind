import time
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field

from middleware.auth import (
    authenticate_user,
    create_token,
    get_current_user,
    USERS,
    ROLE_RANK,
    pwd_ctx,
    safe_password
)
from database import (
    audit,
    db_get_user,
    db_list_users,
    db_create_user,
    db_update_user,
    db_delete_user
)

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class UserCreateRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6)
    role: str = "viewer"   # viewer | operator | admin


class UserUpdateRequest(BaseModel):
    role: Optional[str] = None       # viewer | operator | admin
    password: Optional[str] = None   # optional password reset (min 6 chars)


# ── Login ─────────────────────────────────────────────────────────────────────

@router.post("/login", summary="Login — returns JWT Bearer token")
async def login(req: LoginRequest):
    """
    Exchange username + password for a JWT token.
    Paste the returned access_token into Swagger's Authorize dialog (no 'Bearer ' prefix needed there).
    """
    user = authenticate_user(req.username, req.password)
    if not user:
        # Fallback to direct DB query in case of fresh insertion
        db_user = await db_get_user(req.username)
        if db_user and pwd_ctx.verify(safe_password(req.password), db_user["password_hash"]):
            user = {"username": db_user["username"], "role": db_user["role"]}
            USERS[db_user["username"]] = {
                "hashed_password": db_user["password_hash"],
                "role": db_user["role"],
                "created_at": db_user.get("created_at"),
                "updated_at": db_user.get("updated_at")
            }

    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    token_data = create_token(user["username"], user["role"])
    await audit("login", user=user["username"], result={"role": user["role"]})
    return token_data


@router.post("/login/form", include_in_schema=False)
async def login_form(form: OAuth2PasswordRequestForm = Depends()):
    """OAuth2 password flow — used by Swagger's built-in token form."""
    user = authenticate_user(form.username, form.password)
    if not user:
        db_user = await db_get_user(form.username)
        if db_user and pwd_ctx.verify(safe_password(form.password), db_user["password_hash"]):
            user = {"username": db_user["username"], "role": db_user["role"]}
            USERS[db_user["username"]] = {
                "hashed_password": db_user["password_hash"],
                "role": db_user["role"],
                "created_at": db_user.get("created_at"),
                "updated_at": db_user.get("updated_at")
            }

    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    token_data = create_token(user["username"], user["role"])
    return token_data


# ── Current user info ─────────────────────────────────────────────────────────

@router.get("/me", summary="Get current user info from token")
async def me(user: dict = Depends(get_current_user)):
    return {
        "username": user.get("sub"),
        "role":     user.get("role"),
        "expires":  user.get("exp"),
    }


# ── User management (admin only) ──────────────────────────────────────────────

@router.get("/users", summary="List all users (admin only)")
async def list_users(user: dict = Depends(get_current_user)):
    if ROLE_RANK.get(user.get("role"), -1) < ROLE_RANK["admin"]:
        raise HTTPException(403, "Admin role required")

    db_users = await db_list_users()
    if not db_users:
        # Fallback to in-memory USERS cache
        now = time.time()
        return {
            "users": [
                {
                    "username": u,
                    "role": info["role"],
                    "created_at": info.get("created_at", now),
                    "updated_at": info.get("updated_at", now)
                }
                for u, info in USERS.items()
            ]
        }
    return {"users": db_users}


@router.post("/users", summary="Create a new user (admin only)")
async def create_user(req: UserCreateRequest, user: dict = Depends(get_current_user)):
    if ROLE_RANK.get(user.get("role"), -1) < ROLE_RANK["admin"]:
        raise HTTPException(403, "Admin role required")

    clean_username = req.username.strip()
    if not clean_username or len(clean_username) < 3:
        raise HTTPException(400, "Username must be at least 3 characters")
    if len(req.password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters")
    if req.role not in ROLE_RANK:
        raise HTTPException(400, f"Invalid role '{req.role}'. Must be: viewer, operator, admin")

    existing = await db_get_user(clean_username)
    if existing or clean_username in USERS:
        raise HTTPException(400, f"User '{clean_username}' already exists")

    hashed_pw = pwd_ctx.hash(safe_password(req.password))
    created = await db_create_user(clean_username, hashed_pw, req.role)
    if not created:
        raise HTTPException(500, "Failed to persist user to SQLite database")

    # Update in-memory cache
    USERS[clean_username] = {
        "hashed_password": hashed_pw,
        "role": req.role,
        "created_at": created["created_at"],
        "updated_at": created["updated_at"]
    }

    await audit("user_created", target=clean_username, user=user.get("sub"),
                result={"role": req.role})
    return {
        "status": "created",
        "username": clean_username,
        "role": req.role,
        "created_at": created["created_at"]
    }


@router.put("/users/{username}", summary="Update user role or reset password (admin only)")
async def update_user(username: str, req: UserUpdateRequest, user: dict = Depends(get_current_user)):
    if ROLE_RANK.get(user.get("role"), -1) < ROLE_RANK["admin"]:
        raise HTTPException(403, "Admin role required")

    existing = await db_get_user(username)
    if not existing and username not in USERS:
        raise HTTPException(404, f"User '{username}' not found")

    new_role = None
    if req.role is not None:
        if req.role not in ROLE_RANK:
            raise HTTPException(400, f"Invalid role '{req.role}'. Must be: viewer, operator, admin")
        if username == "admin" and req.role != "admin":
            raise HTTPException(400, "Cannot change role of primary 'admin' account")
        new_role = req.role

    new_hash = None
    if req.password is not None and req.password.strip():
        if len(req.password.strip()) < 6:
            raise HTTPException(400, "New password must be at least 6 characters")
        new_hash = pwd_ctx.hash(safe_password(req.password.strip()))

    if new_role is None and new_hash is None:
        raise HTTPException(400, "Provide either 'role' or 'password' to update")

    updated = await db_update_user(username, role=new_role, password_hash=new_hash)

    # Sync cache
    now = time.time()
    if username in USERS:
        if new_role:
            USERS[username]["role"] = new_role
        if new_hash:
            USERS[username]["hashed_password"] = new_hash
        USERS[username]["updated_at"] = now
    elif updated:
        USERS[username] = {
            "hashed_password": updated["password_hash"],
            "role": updated["role"],
            "created_at": updated.get("created_at", now),
            "updated_at": updated.get("updated_at", now)
        }

    await audit("user_updated", target=username, user=user.get("sub"),
                result={"updated_role": new_role, "password_reset": bool(new_hash)})
    return {
        "status": "updated",
        "username": username,
        "role": updated["role"] if updated else new_role
    }


@router.delete("/users/{username}", summary="Delete a user (admin only)")
async def delete_user(username: str, user: dict = Depends(get_current_user)):
    if ROLE_RANK.get(user.get("role"), -1) < ROLE_RANK["admin"]:
        raise HTTPException(403, "Admin role required")
    if username == "admin":
        raise HTTPException(400, "Cannot delete the default primary 'admin' account")
    if username == user.get("sub"):
        raise HTTPException(400, "Cannot delete your own active administrator account")

    deleted_db = await db_delete_user(username)
    if username in USERS:
        del USERS[username]
    elif not deleted_db:
        raise HTTPException(404, f"User '{username}' not found")

    await audit("user_deleted", target=username, user=user.get("sub"))
    return {"status": "deleted", "username": username}