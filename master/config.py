import os
from typing import Optional

# ── Dynamic In-Memory Settings Cache ──────────────────────────────────────────
# Precedence:
#   1. SQLite dynamic settings (loaded on startup or changed via UI / API)
#   2. Environment variables from .env / container environment
_dynamic_settings: dict = {}

def mask_secret(val: Optional[str]) -> str:
    """Mask sensitive keys/tokens to prevent visual leakage in UI/logs."""
    if not val:
        return ""
    s = str(val).strip()
    if len(s) <= 8:
        return "*" * len(s)
    return f"{s[:4]}...{'*' * 6}...{s[-4:]}"

def get_config_val(key: str, default: str = "") -> str:
    """Return setting from dynamic cache if present, otherwise os.getenv."""
    if key in _dynamic_settings and _dynamic_settings[key] is not None:
        return str(_dynamic_settings[key])
    return os.getenv(key, default)

def set_config_val(key: str, value: str):
    """Update dynamic cache and synchronize global module variables."""
    _dynamic_settings[key] = value
    _sync_globals()

def _sync_globals():
    """Keep module-level constants in sync for any legacy callers."""
    global LLM_PROVIDER, OLLAMA_BASE_URL, LLM_MODEL
    global GEMINI_API_KEY, GEMINI_MODEL, OPENROUTER_API_KEY, OPENROUTER_MODEL
    
    LLM_PROVIDER = get_config_val("LLM_PROVIDER", os.getenv("LLM_PROVIDER", "local"))
    OLLAMA_BASE_URL = get_config_val("OLLAMA_BASE_URL", os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))
    LLM_MODEL = get_config_val("LLM_MODEL", os.getenv("LLM_MODEL", "phi3:mini"))
    GEMINI_API_KEY = get_config_val("GEMINI_API_KEY", os.getenv("GEMINI_API_KEY", ""))
    GEMINI_MODEL = get_config_val("GEMINI_MODEL", os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))
    OPENROUTER_API_KEY = get_config_val("OPENROUTER_API_KEY", os.getenv("OPENROUTER_API_KEY", ""))
    OPENROUTER_MODEL = get_config_val("OPENROUTER_MODEL", os.getenv("OPENROUTER_MODEL", "google/gemma-4-26b-a4b-it:free"))

async def load_dynamic_settings():
    """Load dynamic settings from SQLite database at startup."""
    try:
        from database import db_get_all_settings
        stored = await db_get_all_settings()
        for k, v in stored.items():
            _dynamic_settings[k] = v
        _sync_globals()
        print(f"[Config] Loaded {len(stored)} dynamic settings from SQLite into memory")
    except Exception as e:
        print(f"[Config] Could not load dynamic settings from DB: {e}")

# Dynamic getters used by LLM client and routers
def get_llm_provider() -> str:
    return get_config_val("LLM_PROVIDER", os.getenv("LLM_PROVIDER", "local")).lower()

def get_gemini_api_key() -> str:
    return get_config_val("GEMINI_API_KEY", os.getenv("GEMINI_API_KEY", "")).strip()

def get_gemini_model() -> str:
    return get_config_val("GEMINI_MODEL", os.getenv("GEMINI_MODEL", "gemini-2.5-flash")).strip()

def get_openrouter_api_key() -> str:
    return get_config_val("OPENROUTER_API_KEY", os.getenv("OPENROUTER_API_KEY", "")).strip()

def get_openrouter_model() -> str:
    return get_config_val("OPENROUTER_MODEL", os.getenv("OPENROUTER_MODEL", "google/gemma-4-26b-a4b-it:free")).strip()

def get_ollama_base_url() -> str:
    return get_config_val("OLLAMA_BASE_URL", os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")).strip()

def get_ollama_model() -> str:
    return get_config_val("LLM_MODEL", os.getenv("LLM_MODEL", "phi3:mini")).strip()


# ── Initial static defaults from environment ──────────────────────────────────
LLM_PROVIDER       = os.getenv("LLM_PROVIDER", "local")
OLLAMA_BASE_URL   = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
LLM_MODEL         = os.getenv("LLM_MODEL", "phi3:mini")
GEMINI_API_KEY    = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL      = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL  = os.getenv("OPENROUTER_MODEL", "google/gemma-4-26b-a4b-it:free")

# Master API
MASTER_HOST = os.getenv("MASTER_HOST", "0.0.0.0")
MASTER_PORT = int(os.getenv("MASTER_PORT", "8000"))
API_SECRET  = os.getenv("API_SECRET", "change-this-secret-in-production")

# gRPC server (master listens for slave connections)
GRPC_PORT = int(os.getenv("GRPC_PORT", "50051"))

# mTLS cert paths
CA_CERT     = os.getenv("CA_CERT",     "/app/certs/ca.crt")
SERVER_CERT = os.getenv("SERVER_CERT", "/app/certs/master.crt")
SERVER_KEY  = os.getenv("SERVER_KEY",  "/app/certs/master.key")

# Slave heartbeat — mark offline after this many seconds without ping
SLAVE_TIMEOUT_SECS = int(os.getenv("SLAVE_TIMEOUT_SECS", "30"))

# Docker socket (when master manages its own host too)
DOCKER_SOCKET = os.getenv("DOCKER_SOCKET", "unix:///var/run/docker.sock")
