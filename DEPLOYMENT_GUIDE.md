# DockerMind — Production Deployment & Operations Guide

This guide provides end-to-end instructions for deploying, configuring, securing, and operating **DockerMind** across standalone Docker hosts, Podman environments, and Kubernetes clusters.

---

## 📋 Table of Contents
1. [Architecture Overview](#1-architecture-overview)
2. [Prerequisites](#2-prerequisites)
3. [1-Line Universal Bootstrapper (`install.sh`)](#3-1-line-universal-bootstrapper-installsh)
   - [Deploying the Master Node](#deploying-the-master-node)
   - [Default Credentials (`admin` / `admin`)](#default-credentials-admin--admin)
   - [Connecting Distributed Edge Slaves](#connecting-distributed-edge-slaves)
4. [Zero-Downtime Integrations & Settings Vault](#4-zero-downtime-integrations--settings-vault)
   - [Hot-Reloading AI SRE Engine (Gemini / Ollama / OpenRouter)](#hot-reloading-ai-sre-engine)
   - [Multi-Channel Alerts (Slack, Discord, Email SMTP)](#multi-channel-alerts)
5. [User Directory & Role-Based Access Control (RBAC)](#5-user-directory--role-based-access-control-rbac)
6. [Prometheus Monitoring & Grafana Dashboard](#6-prometheus-monitoring--grafana-dashboard)
7. [Multi-Runtime Setup](#7-multi-runtime-setup)
   - [Docker (Standalone & Swarm)](#docker-standalone--swarm)
   - [Podman (Rootless & Enterprise Linux)](#podman-rootless--enterprise-linux)
   - [Kubernetes (Light Agent DaemonSet & Pod Watcher)](#kubernetes-light-agent-daemonset--pod-watcher)
8. [Network Topology & Security Hardening](#8-network-topology--security-hardening)
9. [Backup & Disaster Recovery](#9-backup--disaster-recovery)
10. [Troubleshooting & Verification](#10-troubleshooting--verification)

---

## 1. Architecture Overview

DockerMind operates on a decoupled **Master-Slave** architecture:

```
                          ┌────────────────────────────────────────┐
                          │         Web Console (:3000)            │
                          │   (Fleet, Alerts, RBAC, Settings)      │
                          └───────────────────▲────────────────────┘
                                              │
                                              │ REST / WebSockets
                                              ▼
┌──────────────────┐      ┌────────────────────────────────────────┐      ┌──────────────────┐
│ Prometheus Server│◄────►│          DockerMind Master             │◄────►│   AI Providers   │
│  (Scrapes :8000) │      │     (FastAPI, LLM Pipeline, RBAC)      │      │ (Gemini, Ollama, │
└──────────────────┘      └───────────▲─────────────────▲──────────┘      │   OpenRouter)    │
                                      │                 │                 └──────────────────┘
                 Heartbeat / Telemetry│                 │ Fleet Commands
                 (HTTPS / mTLS / Token│                 │ (:8080)
                                      ▼                 ▼
                          ┌────────────────────────────────────────┐
                          │          Distributed Slave Node        │
                          │    (Go Agent: Watcher, Stats, Exec)    │
                          │  Mounted: /var/run/docker.sock or CRI  │
                          └────────────────────────────────────────┘
```

- **Master Node (`dockermind-master` & `dockermind-dashboard`):** Ingests telemetry, processes logs through the AI reasoning pipeline, manages persistent configuration/RBAC in SQLite (`/app/data/dockermind.db`), broadcasts real-time WebSocket feeds, and serves Prometheus metrics (`GET /metrics`).
- **Edge Slave Node (`dockermind-slave`):** Lightweight Go agent (<20MB memory) deployed onto each monitored host. Watches container lifecycle events (`die`, `oom`, `health_status`), tracks True RSS memory, filters log anomalies, and executes autonomous self-healing commands.

---

## 2. Prerequisites

| Component | Minimum Specification | Recommended Specification |
| :--- | :--- | :--- |
| **OS** | Linux (Ubuntu 20.04+, Debian 11+, RHEL 8+, Alpine 3.18+) or WSL2 | Ubuntu 22.04 LTS / RHEL 9 |
| **CPU / RAM (Master)** | 1 vCPU / 1 GB RAM | 2 vCPU / 2 GB RAM |
| **CPU / RAM (Slave)** | 0.25 vCPU / 64 MB RAM | 0.5 vCPU / 128 MB RAM |
| **Runtimes** | Docker Engine 20.10+, Podman 4.0+, or Kubernetes 1.24+ | Latest Docker CE or Kubernetes |
| **Network Ports** | Inbound `8000` (API/WS), `3000` (UI) on Master; Inbound `8080` on Slave | Internal overlay network or firewall-restricted |

---

## 3. 1-Line Universal Bootstrapper (`install.sh`)

DockerMind ships with a self-contained POSIX shell bootstrapper that provisions everything with zero manual editing.

### Deploying the Master Node

To install the Master Node interactively:

```bash
curl -fsSL https://raw.githubusercontent.com/dockermind/dockermind/main/install.sh | bash
```

Or from within a cloned repository:

```bash
bash install.sh
```

#### What `install.sh` Performs Automatically:
1. **Host Environment Verification:** Detects CPU, RAM, Docker/Podman sockets, and required utilities.
2. **Interactive Password Setup:** Prompts for a secure Admin password (with confirmation).
3. **Cryptographic Key Generation:** Generates high-entropy `JWT_SECRET` and `API_SECRET` via `openssl rand -hex 32`.
4. **mTLS Certificate Provisioning:** Generates cluster root CA, master certificate, and slave client certificate via `scripts/gen_certs.sh`.
5. **Dynamic AI Engine Selection:** Interactively configures Google Gemini, OpenRouter, or Local Ollama.
6. **Hardened Configuration:** Writes `.env` with strict permissions (`chmod 600`).
7. **Container Launch:** Starts `dockermind-master` and `dockermind-dashboard` in detached mode.
8. **Slave Join Generator:** Automatically prints the exact 1-line command to copy-paste onto edge worker nodes.

---

### Default Credentials (`admin` / `admin`)

> [!IMPORTANT]
> **DevOps Default Standard:**
> If you leave the password prompt blank during installation or deploy headlessly without setting `ADMIN_PASSWORD`, DockerMind sets the default credentials to:
> - **Username:** `admin`
> - **Password:** `admin`
>
> *(Identical to the industry-standard default used by Grafana).*
>
> Once logged in, navigate to **Users & RBAC** or execute `PUT /auth/users/admin` to update your password immediately in production.

---

### Connecting Distributed Edge Slaves

Every monitored host runs a lightweight Go agent. When the Master finishes installation, it displays a ready-to-run slave command:

```bash
curl -fsSL https://raw.githubusercontent.com/dockermind/dockermind/main/install.sh | bash -s -- \
  --role slave \
  --master http://<MASTER_HOST_OR_IP>:8000 \
  --secret <YOUR_API_SECRET> \
  --node-id node-worker-01
```

#### Headless / Automated Slave Join Options:
| Flag | Description | Default |
| :--- | :--- | :--- |
| `--role slave` | Sets execution mode to Edge Slave Agent. | `master` |
| `--master <URL>` | Full HTTP/HTTPS address of the Master API. | *Required* |
| `--secret <HEX>` | Cluster shared `API_SECRET` for authentication. | *Required* |
| `--node-id <NAME>` | Unique node identifier in the cluster. | Hostname |
| `--runtime <NAME>` | Container runtime (`docker` or `podman`). | Auto-detected |

Once started, the slave connects immediately. You will see its green `online` badge appear in the **DockerMind Dashboard** within 3 seconds.

---

## 4. Zero-Downtime Integrations & Settings Vault

DockerMind features a **Zero-Downtime Settings Vault**. You never need to restart containers or edit `.env` files to rotate AI API keys or adjust alert destinations.

### Hot-Reloading AI SRE Engine

Open the Web Console at `http://<MASTER_IP>:3000` and click the **Integrations & Vault** tab in the sidebar:

1. **Provider Switcher:** Seamlessly switch between **Google Gemini**, **OpenRouter**, or **Local Ollama** on the fly.
2. **Dynamic API Key Entry:** Paste new keys. Secrets are stored encrypted in SQLite and masked in the UI (`AIzaSy...******...YXCg`).
3. **Live Test Connection:** Click **"Test AI Connection"** to verify latency and model response before saving.
4. **Instant Zero-Downtime Hot-Reload:** Upon saving, the in-memory LLM client dynamically reloads keys without dropping ongoing telemetry streams.

---

### Multi-Channel Alerts

Configure alert dispatching directly from the **Integrations & Vault** tab:

- **Slack Incoming Webhook:**
  - URL: `https://hooks.slack.com/services/T.../B.../...`
  - Receive real-time rich incident cards with severity tags, MB memory usage, and root-cause summaries.
- **Discord Webhook:**
  - URL: `https://discord.com/api/webhooks/.../...`
  - Colored embeds matching incident severity (Red = Critical, Amber = Warning).
- **Email (SMTP) with TLS/SSL:**
  - Standard support for corporate SMTP relays and **Gmail App Passwords**:
    - **Host:** `smtp.gmail.com`
    - **Port:** `587` (STARTTLS) or `465` (SSL)
    - **Username:** `your-email@gmail.com`
    - **Password:** Google 16-character App Password
    - **From Email:** `dockermind-alerts@yourcompany.com`
    - **To Email:** `oncall-team@yourcompany.com`
- **Verify Instantly:** Click **"Send Test Alert"** to dispatch a diagnostic ping to all enabled channels simultaneously.

---

## 5. User Directory & Role-Based Access Control (RBAC)

DockerMind features a persistent user directory backed by SQLite (`/app/data/dockermind.db`) with bcrypt hashing.

### Role Hierarchy
| Role | Privileges | Target Persona |
| :--- | :--- | :--- |
| **`admin`** | Full permissions: User management, Settings Vault, LLM keys, container `exec`, node deregistration, audit logs. | Lead DevOps / SRE Architect |
| **`operator`** | Container control: `restart`, `start`, `stop`, acknowledge alerts, trigger auto-healing, fleet commands. | On-Call Engineers & Developers |
| **`viewer`** | Read-only access: View dashboard, stream logs, inspect metrics and crash loops. | Stakeholders, Auditors, Read-Only QA |

### User Management Operations
Administrators can manage users directly in the **Users & RBAC** tab:
- **Create User:** Enter username, password, and assign role.
- **Update Role:** Promote or demote operators/viewers on the fly.
- **Password Reset:** Reset credentials for compromised or forgotten accounts.
- **Delete Account:** Remove retired accounts (with built-in safeguards preventing root admin and self-deletion).

---

## 6. Prometheus Monitoring & Grafana Dashboard

DockerMind includes a native Prometheus exporter exposing cluster health, true memory usage, and AI SRE incident telemetry.

### Exporter Endpoint
- **URL:** `http://<MASTER_IP>:8000/metrics`
- **Format:** Standard Prometheus Exposition Format (`text/plain; version=0.0.4`)
- **Authentication:** Unauthenticated scraper access enabled by default.

### Prometheus Configuration (`prometheus.yml`)
Add DockerMind to your Prometheus scrape jobs:

```yaml
scrape_configs:
  - job_name: 'dockermind'
    scrape_interval: 15s
    scrape_timeout: 10s
    static_configs:
      - targets: ['<MASTER_IP>:8000']
        labels:
          cluster: 'production-fleet'
```

### Pre-built Grafana Dashboard
A production-ready dashboard is included in the repository at:
[`monitoring/grafana/dockermind-dashboard.json`](file:///monitoring/grafana/dockermind-dashboard.json)

#### How to Import:
1. Open your Grafana instance (`http://<GRAFANA_IP>:3000`).
2. Navigate to **Dashboards** → **New** → **Import**.
3. Upload `dockermind-dashboard.json` or paste the JSON content.
4. Select your Prometheus data source and click **Import**.

#### Included Dashboard Panels:
- **Cluster Fleet Status:** Online/offline slave nodes gauge.
- **Container Inventory:** Total containers grouped by state (`running`, `exited`, `paused`).
- **True RSS Memory Usage:** Real physical memory consumption per container with inactive page-cache subtracted.
- **Active Crash Loops Gauge:** Immediate red alert panel for containers in `CrashLoopBackOff`.
- **Circuit Breaker Status:** Indicates when auto-healing has halted restarts to prevent resource thrashing.
- **AI Diagnostics & Healing Counter:** Real-time log of AI automated interventions.

---

## 7. Multi-Runtime Setup

### Docker (Standalone & Swarm)
Standard installation mounts the Linux Docker daemon socket:
```bash
docker run -d --name dockermind-slave \
  -v /var/run/docker.sock:/var/run/docker.sock:ro \
  -e MASTER_URL="http://master:8000" \
  -e SLAVE_SECRET="<API_SECRET>" \
  dockermind-slave:latest
```

---

### Podman (Rootless & Enterprise Linux)
DockerMind automatically detects Podman sockets:
- **System Socket:** `/run/podman/podman.sock`
- **Rootless User Socket:** `/run/user/<UID>/podman/podman.sock`

#### Launching on Podman:
```bash
# Enable rootless socket
systemctl --user enable --now podman.socket

# Run agent with user socket
podman run -d --name dockermind-slave \
  -v $XDG_RUNTIME_DIR/podman/podman.sock:/var/run/docker.sock:ro \
  -e MASTER_URL="http://master:8000" \
  -e SLAVE_SECRET="<API_SECRET>" \
  dockermind-slave:latest
```

---

### Kubernetes (Light Agent DaemonSet & Pod Watcher)

DockerMind is engineered for cloud-native Kubernetes workloads as well as Docker. It deploys as a lightweight `DaemonSet` across worker nodes to observe pod lifecycles, monitor container runtime sockets (`containerd`, `CRI-O`, or `Docker`), and stream `CrashLoopBackOff` and `OOMKilled` pod telemetry to the Master AI engine.

#### Step 1: Create Namespace & Secret
```bash
kubectl create namespace dockermind

kubectl create secret generic dockermind-cluster-secret \
  --namespace dockermind \
  --from-literal=MASTER_URL="http://<MASTER_IP>:8000" \
  --from-literal=SLAVE_SECRET="<YOUR_API_SECRET>"
```

#### Step 2: Apply DaemonSet Manifest
```bash
kubectl apply -f deploy/kubernetes/dockermind-daemonset.yaml
```

#### DaemonSet Specification Overview (`dockermind-daemonset.yaml`):
```yaml
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: dockermind-agent
  namespace: dockermind
  labels:
    app: dockermind-agent
spec:
  selector:
    matchLabels:
      app: dockermind-agent
  template:
    metadata:
      labels:
        app: dockermind-agent
    spec:
      serviceAccountName: dockermind-agent-sa
      tolerations:
        - operator: Exists # Schedule on control-plane and worker nodes
      containers:
        - name: agent
          image: dockermind/slave:latest
          env:
            - name: NODE_NAME
              valueFrom:
                fieldRef:
                  fieldPath: spec.nodeName
            - name: MASTER_URL
              valueFrom:
                secretKeyRef:
                  name: dockermind-cluster-secret
                  key: MASTER_URL
            - name: SLAVE_SECRET
              valueFrom:
                secretKeyRef:
                  name: dockermind-cluster-secret
                  key: SLAVE_SECRET
          volumeMounts:
            - name: cri-socket
              mountPath: /var/run/docker.sock
              readOnly: true
      volumes:
        - name: cri-socket
          hostPath:
            path: /run/containerd/containerd.sock # Or /var/run/docker.sock
```

---

## 8. Network Topology & Security Hardening

### Firewall Rules & Port Matrix
| Port | Protocol | Source | Destination | Purpose |
| :--- | :---: | :---: | :---: | :--- |
| **`3000`** | TCP | Operators / Browser | Master Node | React Web Console (Nginx) |
| **`8000`** | TCP | Slaves & Prometheus | Master Node | REST API, WebSockets, `/metrics` |
| **`8080`** | TCP | Master Node Only | Slave Nodes | Command Execution Endpoint |

### Security Checklist:
- [x] **Store Passwords with Bcrypt:** Handled natively by DockerMind backend.
- [x] **Restrict Slave Ports:** Ensure port `8080` on slave nodes is only accessible from the Master node IP.
- [x] **mTLS Encryption:** Use certificates in `/app/certs` generated by `scripts/gen_certs.sh` for inter-node communication across public networks.
- [x] **Hardened File Permissions:** Verify `.env` is set to `chmod 600`.

---

## 9. Backup & Disaster Recovery

All stateful data in DockerMind resides in two files:
1. **SQLite Database:** `/app/data/dockermind.db` (Contains registered users, RBAC roles, audit trail, incidents, and dynamic settings).
2. **Environment File:** `.env` (Master tokens and bootstrap keys).

### Backup Procedure
```bash
# Snapshot SQLite database while running (safe online backup)
docker exec dockermind-master sqlite3 /app/data/dockermind.db ".backup '/app/data/backup.db'"

# Copy out to secure storage
docker cp dockermind-master:/app/data/backup.db /backups/backup-$(date +%F).db
cp .env /backups/.env.backup
```

### Restore Procedure
```bash
# Stop master container
docker stop dockermind-master

# Replace database file
docker cp /backups/backup-2026-10-16.db dockermind-master:/app/data/dockermind.db

# Restart container
docker start dockermind-master
```

---

## 10. Troubleshooting & Verification

### Verifying Service Health
```bash
# Check Master API status
curl -i http://localhost:8000/health

# Scrape Prometheus metrics
curl -s http://localhost:8000/metrics | grep dockermind_up

# Check Slave Node registration
curl -s http://localhost:8000/slaves | jq .
```

### Viewing Logs
```bash
# Master logs
docker logs -f dockermind-master

# Web Console logs
docker logs -f dockermind-dashboard

# Slave Agent logs
docker logs -f dockermind-slave
```

---

*For detailed architectural references, feature breakdowns, and API documentation, refer to the primary [README.md](file:///README.md).*
