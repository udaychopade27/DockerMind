from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from middleware.auth import authenticate_user, create_token, get_current_user, USERS, ROLE_RANK
from database import audit

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class UserCreateRequest(BaseModel):
    username: str
    password: str
    role: str = "viewer"   # viewer | operator | admin


# ── Login ─────────────────────────────────────────────────────────────────────

@router.post("/login", summary="Login — returns JWT Bearer token")
async def login(req: LoginRequest):
    """
    Exchange username + password for a JWT token.
    Paste the returned access_token into Swagger's Authorize dialog (no 'Bearer ' prefix needed there).
    """
    user = authenticate_user(req.username, req.password)
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
    return {
        "users": [
            {"username": u, "role": info["role"]}
            for u, info in USERS.items()
        ]
    }


@router.post("/users", summary="Create a new user (admin only)")
async def create_user(req: UserCreateRequest, user: dict = Depends(get_current_user)):
    if ROLE_RANK.get(user.get("role"), -1) < ROLE_RANK["admin"]:
        raise HTTPException(403, "Admin role required")
    if req.username in USERS:
        raise HTTPException(400, f"User '{req.username}' already exists")
    if req.role not in ROLE_RANK:
        raise HTTPException(400, f"Invalid role '{req.role}'. Must be: viewer, operator, admin")

    from passlib.context import CryptContext
    pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
    USERS[req.username] = {
        "hashed_password": pwd_ctx.hash(req.password),
        "role": req.role,
    }
    await audit("user_created", target=req.username, user=user.get("sub"),
                result={"role": req.role})
    return {"status": "created", "username": req.username, "role": req.role}


@router.delete("/users/{username}", summary="Delete a user (admin only)")
async def delete_user(username: str, user: dict = Depends(get_current_user)):
    if ROLE_RANK.get(user.get("role"), -1) < ROLE_RANK["admin"]:
        raise HTTPException(403, "Admin role required")
    if username == "admin":
        raise HTTPException(400, "Cannot delete the default admin account")
    if username not in USERS:
        raise HTTPException(404, f"User '{username}' not found")
    del USERS[username]
    await audit("user_deleted", target=username, user=user.get("sub"))
    return {"status": "deleted", "username": username}