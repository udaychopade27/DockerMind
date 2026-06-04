import os
import time
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

# Role config — set via env vars or extend for DB-backed RBAC in Phase 4
# Format: "key1:role1,key2:role2"
# Roles: admin (full access) | operator (read + heal) | viewer (read only)

def _load_keys() -> dict:
    """Load API keys from env. Falls back to single API_SECRET as admin."""
    keys = {}
    raw = os.getenv("API_KEYS", "")
    if raw:
        for entry in raw.split(","):
            parts = entry.strip().split(":")
            if len(parts) == 2:
                keys[parts[0].strip()] = parts[1].strip()
    # Always add the main secret as admin
    secret = os.getenv("API_SECRET", "change-this-secret-in-production")
    if secret:
        keys[secret] = "admin"
    return keys


API_KEYS: dict = _load_keys()

# Routes and the minimum role required to access them
ROUTE_ROLES = {
    "POST /heal":              "operator",
    "POST /containers":        "operator",
    "POST /jobs":              "operator",
    "POST /runbooks":          "admin",
    "DELETE /slaves":          "admin",
    "GET /jobs/audit/log":     "admin",
}


def get_role(api_key: str) -> str | None:
    return API_KEYS.get(api_key)


def role_rank(role: str) -> int:
    return {"viewer": 0, "operator": 1, "admin": 2}.get(role, -1)


class RBACMiddleware(BaseHTTPMiddleware):
    """
    Lightweight RBAC middleware.
    - /health and /slaves/register + /slaves/heartbeat are public (slave agents need these)
    - /ws WebSocket is public (dashboard connects before auth)
    - Everything else requires X-Api-Key header
    """

    PUBLIC_PATHS = {"/health", "/slaves/register", "/slaves/heartbeat",
                    "/slaves/logs", "/slaves/events", "/slaves/stats", "/ws"}

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Allow public paths
        if any(path.startswith(p) for p in self.PUBLIC_PATHS):
            return await call_next(request)

        api_key = request.headers.get("X-Api-Key", "")
        role = get_role(api_key)

        if not role:
            raise HTTPException(status_code=401, detail="Invalid or missing API key")

        # Check route-specific role requirements
        route_key = f"{request.method} {path.rstrip('/')}"
        for pattern, required_role in ROUTE_ROLES.items():
            method, route_path = pattern.split(" ", 1)
            if request.method == method and path.startswith(route_path):
                if role_rank(role) < role_rank(required_role):
                    raise HTTPException(
                        status_code=403,
                        detail=f"Role '{role}' cannot access this endpoint (requires '{required_role}')"
                    )
                break

        # Attach role to request state for downstream use
        request.state.role = role
        request.state.api_key = api_key

        response = await call_next(request)
        return response