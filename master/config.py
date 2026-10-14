import os

# ── LLM provider selection ────────────────────────────────────────────────────
# LLM_PROVIDER options:
#   "local"      → Ollama (default — no API key needed)
#   "online"     → Gemini first, OpenRouter fallback
#   "gemini"     → Gemini only
#   "openrouter" → OpenRouter only
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "local")

# Ollama (local)
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
LLM_MODEL       = os.getenv("LLM_MODEL", "phi3:mini")   # ~2.2GB, runs fine on 4GB RAM

# Gemini (Google AI Studio — free tier: 15 RPM, 1500 RPD, 1M token context)
# Get key: https://aistudio.google.com/app/apikey
# gemini-1.5-flash  → MOST RELIABLE on free tier (confirmed working)
# gemini-2.0-flash  → may 404 depending on region/key type
GEMINI_API_KEY  = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL    = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# OpenRouter (fallback — use a specific free chat model)
# Get key: https://openrouter.ai/keys
# WARNING: "openrouter/free" auto-router can route to moderation models — avoid it
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL   = os.getenv("OPENROUTER_MODEL", "google/gemma-4-26b-a4b-it:free")

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