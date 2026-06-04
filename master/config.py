import os

# LLM
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
LLM_MODEL       = os.getenv("LLM_MODEL", "phi3:mini")   # ~2.2GB, runs fine on 4GB RAM

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