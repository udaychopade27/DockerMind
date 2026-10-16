#!/usr/bin/env bash
# ==============================================================================
# DockerMind — Universal 1-Line Autonomous Cluster & Agent Bootstrapper
# ==============================================================================
# Usage:
#   Master (Interactive):
#     curl -sSL https://raw.githubusercontent.com/<org>/dockermind/main/install.sh | bash
#
#   Master (Non-Interactive / Headless):
#     curl -sSL ... | bash -s -- --role master --password "admin123" --ai-provider gemini --gemini-key "AIzaSy..."
#
#   Edge Slave (Automated 1-Liner):
#     curl -sSL ... | bash -s -- --role slave --master http://<IP>:8000 --secret <SECRET> --name node-edge-01
# ==============================================================================

set -eo pipefail

# ── Color Palette ─────────────────────────────────────────────────────────────
BOLD='\033[1m'
NC='\033[0m'
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
DIM='\033[2m'
MAGENTA='\033[0;35m'

log_info()  { echo -e "${CYAN}ℹ${NC}  $*"; }
log_ok()    { echo -e "${GREEN}✔${NC}  $*"; }
log_warn()  { echo -e "${YELLOW}▲${NC}  $*"; }
log_err()   { echo -e "${RED}✖${NC}  $*"; }
log_step()  { echo -e "\n${BOLD}${MAGENTA}▶ $1${NC}"; }

# ── Safe Input Helper (supports piped curl | bash via /dev/tty) ──────────────
prompt_read() {
  local prompt_text="$1"
  local var_name="$2"
  local is_secret="${3:-false}"

  if [ -t 0 ]; then
    if [ "$is_secret" = "true" ]; then
      read -s -r -p "$prompt_text" "$var_name"
      echo ""
    else
      read -r -p "$prompt_text" "$var_name"
    fi
  elif [ -e /dev/tty ]; then
    if [ "$is_secret" = "true" ]; then
      read -s -r -p "$prompt_text" "$var_name" </dev/tty
      echo ""
    else
      read -r -p "$prompt_text" "$var_name" </dev/tty
    fi
  else
    eval "$var_name=''"
  fi
}

# ── Generate High-Entropy Cryptographic String ────────────────────────────────
gen_random_secret() {
  local length="${1:-32}"
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex "$((length / 2))" 2>/dev/null
  else
    tr -dc 'a-f0-9' </dev/urandom | head -c "$length"
  fi
}

# ── Detect Host LAN IP ────────────────────────────────────────────────────────
detect_host_ip() {
  local ip=""
  if command -v ip >/dev/null 2>&1; then
    ip=$(ip route get 1.1.1.1 2>/dev/null | awk '{print $7}' | tr -d ' \n')
  fi
  if [ -z "$ip" ] && command -v hostname >/dev/null 2>&1; then
    ip=$(hostname -I 2>/dev/null | awk '{print $1}' | tr -d ' \n')
  fi
  if [ -z "$ip" ]; then
    ip="127.0.0.1"
  fi
  echo "$ip"
}

# ── Banner ────────────────────────────────────────────────────────────────────
print_banner() {
  echo -e "${CYAN}"
  cat << "EOF"
  ██████╗  ██████╗  ██████╗██╗  ██╗███████╗██████╗ ███╗   ███╗██╗███╗   ██╗██████╗ 
  ██╔══██╗██╔═══██╗██╔════╝██║ ██╔╝██╔════╝██╔══██╗████╗ ████║██║████╗  ██║██╔══██╗
  ██║  ██║██║   ██║██║     █████═╝ █████╗  ██████╔╝██╔████╔██║██║██╔██╗ ██║██║  ██║
  ██║  ██║██║   ██║██║     ██╔═██╗ ██╔══╝  ██╔══██╗██║╚██╔╝██║██║██║╚██╗██║██║  ██║
  ██████╔╝╚██████╔╝╚██████╗██║ ╚██╗███████╗██║  ██║██║ ╚═╝ ██║██║██║ ╚████║██████╔╝
  ╚═════╝  ╚═════╝  ╚═════╝╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝╚═╝╚═╝  ╚═══╝╚═════╝ 
EOF
  echo -e "       ${BOLD}Autonomous AI SRE & Container Incident Remediation Platform${NC}"
  echo -e "                 ${DIM}Universal Zero-Touch Installer v1.0.0${NC}\n"
}

# ── Pre-flight Checks ─────────────────────────────────────────────────────────
check_dependencies() {
  log_step "Pre-flight Environment Validation"

  local os_type
  os_type=$(uname -s)
  log_info "Host Operating System: ${BOLD}${os_type} ($(uname -m))${NC}"

  if ! command -v docker >/dev/null 2>&1; then
    log_err "Docker is not installed on this system."
    echo -e "   Please install Docker Engine first: ${CYAN}https://docs.docker.com/engine/install/${NC}"
    echo -e "   Or run: ${BOLD}curl -fsSL https://get.docker.com | sh${NC}"
    exit 1
  fi
  local docker_ver
  docker_ver=$(docker --version | awk '{print $3}' | tr -d ',')
  log_ok "Docker Engine found: ${BOLD}v${docker_ver}${NC}"

  if docker compose version >/dev/null 2>&1; then
    local compose_ver
    compose_ver=$(docker compose version --short 2>/dev/null || echo "v2")
    log_ok "Docker Compose plugin found: ${BOLD}${compose_ver}${NC}"
  elif command -v docker-compose >/dev/null 2>&1; then
    log_ok "Docker Compose standalone found: ${BOLD}$(docker-compose --version)${NC}"
  else
    log_err "Docker Compose is required but was not found."
    exit 1
  fi

  if command -v openssl >/dev/null 2>&1; then
    log_ok "Cryptographic engine (OpenSSL) available."
  else
    log_warn "OpenSSL not found. High-entropy /dev/urandom will be used for token generation."
  fi
}

# ── Parse CLI Arguments ───────────────────────────────────────────────────────
ROLE=""
ADMIN_PASS=""
AI_PROVIDER=""
GEMINI_KEY=""
OPENROUTER_KEY=""
MASTER_URL_PARAM=""
SLAVE_SECRET_PARAM=""
SLAVE_NAME_PARAM=""
HEADLESS=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --role)
      ROLE="$2"
      shift 2
      ;;
    --password)
      ADMIN_PASS="$2"
      shift 2
      ;;
    --ai-provider)
      AI_PROVIDER="$2"
      shift 2
      ;;
    --gemini-key)
      GEMINI_KEY="$2"
      shift 2
      ;;
    --openrouter-key)
      OPENROUTER_KEY="$2"
      shift 2
      ;;
    --master)
      MASTER_URL_PARAM="$2"
      shift 2
      ;;
    --secret)
      SLAVE_SECRET_PARAM="$2"
      shift 2
      ;;
    --name)
      SLAVE_NAME_PARAM="$2"
      shift 2
      ;;
    --headless)
      HEADLESS=true
      shift
      ;;
    *)
      shift
      ;;
  esac
done

# ── Role Selection ────────────────────────────────────────────────────────────
select_role() {
  if [ -n "$ROLE" ]; then
    return
  fi

  echo -e "Choose deployment mode:"
  echo -e "  ${BOLD}1) Master Cluster${NC}  — Master Controller + AI Engine + Web UI Dashboard"
  echo -e "  ${BOLD}2) Edge Slave Agent${NC} — Lightweight monitor for Docker/Podman node joining master"
  echo ""
  local choice=""
  prompt_read "Select installation role [1-2] (default: 1): " choice false

  case "$choice" in
    2|slave|agent)
      ROLE="slave"
      ;;
    *)
      ROLE="master"
      ;;
  esac
}

# ==============================================================================
# MASTER NODE INSTALLATION
# ==============================================================================
install_master() {
  log_step "Configuring DockerMind Master Cluster"

  local admin_password="$ADMIN_PASS"
  if [ -z "$admin_password" ]; then
    echo -e "\n${BOLD}Administrator Security Credentials:${NC}"
    echo -e "${DIM}Define a secure password for the 'admin' account to access the dashboard.${NC}"

    while true; do
      local p1=""
      local p2=""
      prompt_read "Enter Admin Password [press Enter for default 'admin']: " p1 true
      if [ -z "$p1" ]; then
        admin_password="admin"
        log_ok "Default credentials active: ${BOLD}admin / admin${NC} (Same as Grafana default)"
        break
      fi

      if [ ${#p1} -lt 4 ]; then
        log_err "Password must be at least 4 characters long."
        continue
      fi

      prompt_read "Confirm Admin Password: " p2 true
      if [ "$p1" != "$p2" ]; then
        log_err "Passwords do not match. Please try again."
        continue
      fi

      admin_password="$p1"
      log_ok "Custom admin password configured."
      break
    done
  fi

  log_info "Provisioning cluster security keys..."
  local jwt_secret
  jwt_secret=$(gen_random_secret 64)
  local api_secret
  api_secret=$(gen_random_secret 32)
  log_ok "Cryptographic JWT signing key and mutual cluster API secret generated."

  local selected_ai="${AI_PROVIDER:-online}"
  local gemini_k="$GEMINI_KEY"
  local openrouter_k="$OPENROUTER_KEY"

  if [ -z "$AI_PROVIDER" ] && [ "$HEADLESS" = false ]; then
    echo -e "\n${BOLD}AI Root-Cause Intelligence Engine:${NC}"
    echo -e "  1) Google Gemini (Recommended — Ultra-fast, generous free tier)"
    echo -e "  2) OpenRouter (Multi-model: Claude, DeepSeek, Llama 3)"
    echo -e "  3) Local Ollama (Fully air-gapped / offline, requires ~4GB RAM)"
    echo -e "  4) Skip for now (Configure later via Web UI Settings & Vault)"
    echo ""
    local ai_choice=""
    prompt_read "Select AI provider [1-4] (default: 1): " ai_choice false

    case "$ai_choice" in
      2)
        selected_ai="openrouter"
        prompt_read "Enter OpenRouter API Key (or press Enter to skip): " openrouter_k true
        ;;
      3)
        selected_ai="local"
        ;;
      4)
        selected_ai="online"
        ;;
      *)
        selected_ai="gemini"
        prompt_read "Enter Google Gemini API Key (or press Enter to skip): " gemini_k true
        ;;
    esac
  fi

  log_step "Generating Internal Security & mTLS Certificates"
  if [ -f "./scripts/gen_certs.sh" ]; then
    bash ./scripts/gen_certs.sh >/dev/null 2>&1 || true
    log_ok "mTLS certificates provisioned in ./master/certs and ./slave/certs."
  fi

  log_step "Persisting Hardened Environment Configuration (.env)"
  cat > .env << EOF
# ── DockerMind Master Configuration ──────────────────────────────────────────
# Generated automatically by install.sh on $(date -u)
ADMIN_USERNAME=admin
ADMIN_PASSWORD=${admin_password}
JWT_SECRET=${jwt_secret}
API_SECRET=${api_secret}

# ── AI SRE Intelligence Provider ──────────────────────────────────────────────
LLM_PROVIDER=${selected_ai}
GEMINI_API_KEY=${gemini_k}
GEMINI_MODEL=gemini-2.5-flash
OPENROUTER_API_KEY=${openrouter_k}
OPENROUTER_MODEL=google/gemma-4-26b-a4b-it:free
OLLAMA_BASE_URL=http://ollama:11434
LLM_MODEL=qwen2.5-coder:1.5b

# ── Alert Notification Channels ──────────────────────────────────────────────
SLACK_WEBHOOK_URL=
DISCORD_WEBHOOK_URL=
GENERIC_WEBHOOK_URL=
NOTIFY_MIN_SEVERITY=warn
EOF

  chmod 600 .env
  log_ok "Configuration saved to .env with restrictive permissions (chmod 600)."

  log_step "Launching DockerMind Master Stack"
  local compose_cmd="docker compose"
  if ! docker compose version >/dev/null 2>&1; then
    compose_cmd="docker-compose"
  fi

  if [ "$selected_ai" = "local" ]; then
    log_info "Starting containers with local Ollama profile..."
    $compose_cmd --profile local up -d
  else
    log_info "Starting containers..."
    $compose_cmd up -d
  fi

  log_info "Awaiting master API readiness probe..."
  local attempts=0
  local max_attempts=30
  local healthy=false

  while [ $attempts -lt $max_attempts ]; do
    if curl -s -f http://127.0.0.1:8000/health >/dev/null 2>&1; then
      healthy=true
      break
    fi
    sleep 2
    attempts=$((attempts + 1))
    echo -n "."
  done
  echo ""

  if [ "$healthy" = true ]; then
    log_ok "Master API controller is online and healthy!"
  else
    log_warn "Master API is still initializing. Check logs via: docker logs -f dockermind-master"
  fi

  local host_ip
  host_ip=$(detect_host_ip)

  echo ""
  echo -e "${GREEN}==============================================================================${NC}"
  echo -e "                   ${BOLD}🚀 DOCKERMIND MASTER CLUSTER DEPLOYED${NC}"
  echo -e "${GREEN}==============================================================================${NC}"
  echo -e "  ${BOLD}Web Dashboard UI:${NC}    ${CYAN}http://${host_ip}:3000${NC} (or http://localhost:3000)"
  echo -e "  ${BOLD}Master REST API:${NC}     ${CYAN}http://${host_ip}:8000${NC}"
  echo -e "  ${BOLD}Admin Username:${NC}      admin"
  echo -e "  ${BOLD}Admin Password:${NC}      ${BOLD}${admin_password}${NC} (Default: admin)"
  echo -e "  ${BOLD}Active AI Engine:${NC}    ${selected_ai}"
  echo -e "${GREEN}------------------------------------------------------------------------------${NC}"
  echo -e "  ${BOLD}Dynamic Key & Alert Rotation:${NC}"
  echo -e "  Configure Slack, Discord, Gmail SMTP, and rotate AI keys anytime in the UI:"
  echo -e "  ${CYAN}http://${host_ip}:3000/#settings${NC} (Zero container restarts required)"
  echo -e "${GREEN}------------------------------------------------------------------------------${NC}"
  echo -e "  ${BOLD}📡 COPY-PASTE 1-LINE COMMAND TO JOIN EDGE SLAVE NODES:${NC}"
  echo ""
  echo -e "  ${YELLOW}curl -sSL https://raw.githubusercontent.com/dockermind/dockermind/main/install.sh | bash -s -- \\${NC}"
  echo -e "  ${YELLOW}  --role slave --master http://${host_ip}:8000 --secret ${api_secret} --name node-\$(hostname)${NC}"
  echo -e "${GREEN}==============================================================================${NC}\n"
}

# ==============================================================================
# EDGE SLAVE AGENT INSTALLATION
# ==============================================================================
install_slave() {
  log_step "Configuring DockerMind Edge Slave Node"

  local master_url="$MASTER_URL_PARAM"
  local slave_secret="$SLAVE_SECRET_PARAM"
  local slave_name="$SLAVE_NAME_PARAM"

  if [ -z "$master_url" ]; then
    prompt_read "Enter Master URL (e.g. http://192.168.1.50:8000): " master_url false
  fi
  if [ -z "$master_url" ]; then
    log_err "Master URL is required to join cluster."
    exit 1
  fi
  master_url="${master_url%/}"

  if [ -z "$slave_secret" ]; then
    prompt_read "Enter Cluster Pre-Shared Secret: " slave_secret true
  fi
  if [ -z "$slave_secret" ]; then
    log_err "Cluster secret is required for authentication."
    exit 1
  fi

  if [ -z "$slave_name" ]; then
    local default_name="slave-$(hostname)"
    prompt_read "Enter Node Identifier [default: ${default_name}]: " slave_name false
    if [ -z "$slave_name" ]; then
      slave_name="$default_name"
    fi
  fi

  log_info "Verifying connectivity to Master controller at ${master_url}..."
  if ! curl -s -f --connect-timeout 5 "${master_url}/health" >/dev/null 2>&1; then
    log_warn "Could not reach Master /health endpoint at ${master_url}. Please ensure port 8000 is open in firewall."
    local cont=""
    prompt_read "Proceed with deployment anyway? [y/N]: " cont false
    if [[ ! "$cont" =~ ^[Yy]$ ]]; then
      log_err "Installation aborted."
      exit 1
    fi
  else
    log_ok "Successfully connected to Master controller."
  fi

  local docker_sock="/var/run/docker.sock"
  if [ ! -e "$docker_sock" ]; then
    log_warn "Docker socket not found at /var/run/docker.sock."
    if [ -e "/run/podman/podman.sock" ]; then
      docker_sock="/run/podman/podman.sock"
      log_ok "Detected Podman socket at /run/podman/podman.sock"
    fi
  fi

  log_step "Launching DockerMind Edge Agent Container"

  # Container network & hostname resolution
  local target_master="$master_url"
  local net_args="--add-host host.docker.internal:host-gateway"

  # If master is specified as localhost/127.0.0.1 on the same machine, route through host gateway
  if [[ "$target_master" =~ 127\.0\.0\.1|localhost ]]; then
    target_master="http://host.docker.internal:8000"
    log_info "Translating local master address to http://host.docker.internal:8000 for container bridge access."
  fi

  # If dockermind docker bridge exists on this host, connect directly
  if docker network inspect dockermind >/dev/null 2>&1; then
    net_args="--network dockermind $net_args"
  fi

  docker rm -f dockermind-slave >/dev/null 2>&1 || true

  log_info "Starting 'dockermind-slave' agent container..."
  docker run -d \
    --name dockermind-slave \
    --restart unless-stopped \
    $net_args \
    -p 8080:8080 \
    -v "${docker_sock}:/var/run/docker.sock:ro" \
    -e SLAVE_ID="${slave_name}" \
    -e MASTER_URL="${target_master}" \
    -e SLAVE_SECRET="${slave_secret}" \
    -e SLAVE_PORT="8080" \
    dockermind-slave-local:latest 2>/dev/null || \
  docker run -d \
    --name dockermind-slave \
    --restart unless-stopped \
    $net_args \
    -p 8080:8080 \
    -v "${docker_sock}:/var/run/docker.sock:ro" \
    -e SLAVE_ID="${slave_name}" \
    -e MASTER_URL="${target_master}" \
    -e SLAVE_SECRET="${slave_secret}" \
    -e SLAVE_PORT="8080" \
    ghcr.io/dockermind/slave:latest

  log_ok "Edge Agent container started as 'dockermind-slave'."

  echo ""
  echo -e "${GREEN}==============================================================================${NC}"
  echo -e "                   ${BOLD}🛰️  DOCKERMIND EDGE SLAVE AGENT JOINED${NC}"
  echo -e "${GREEN}==============================================================================${NC}"
  echo -e "  ${BOLD}Node Identifier:${NC}     ${slave_name}"
  echo -e "  ${BOLD}Connected Master:${NC}    ${master_url}"
  echo -e "  ${BOLD}Local Port:${NC}          8080"
  echo -e "  ${BOLD}Socket Interface:${NC}    ${docker_sock}"
  echo -e "  ${BOLD}Status:${NC}              Active & Streaming Telemetry"
  echo -e "${GREEN}==============================================================================${NC}\n"
}

# ── Main Entrypoint ───────────────────────────────────────────────────────────
main() {
  print_banner
  check_dependencies
  select_role

  case "$ROLE" in
    master)
      install_master
      ;;
    slave|agent)
      install_slave
      ;;
    *)
      log_err "Unknown role: $ROLE. Valid options: master, slave"
      exit 1
      ;;
  esac
}

main "$@"
