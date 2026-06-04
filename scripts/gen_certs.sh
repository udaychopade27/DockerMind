#!/usr/bin/env bash
# gen_certs.sh — Generate CA + master + slave mTLS certificates
# Run ONCE before first deploy: bash scripts/gen_certs.sh
# Re-run with --force to regenerate all certs

set -euo pipefail

CERTS_DIR="./master/certs"
DAYS=825   # ~2.25 years

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

info()    { echo -e "${GREEN}[cert]${NC} $*"; }
warn()    { echo -e "${YELLOW}[warn]${NC} $*"; }
die()     { echo -e "${RED}[error]${NC} $*"; exit 1; }

command -v openssl >/dev/null 2>&1 || die "openssl not found — install it first"

FORCE="${1:-}"
if [[ -f "$CERTS_DIR/ca.crt" && "$FORCE" != "--force" ]]; then
  warn "Certs already exist in $CERTS_DIR — skipping. Use --force to regenerate."
  exit 0
fi

mkdir -p "$CERTS_DIR"
cd "$CERTS_DIR"

# ── 1. Certificate Authority ──────────────────────────────────────────────────
info "Generating CA key and certificate..."
openssl genrsa -out ca.key 4096 2>/dev/null
openssl req -x509 -new -nodes \
  -key ca.key \
  -sha256 \
  -days $DAYS \
  -out ca.crt \
  -subj "/C=IN/O=DockerMind/CN=DockerMind-CA" 2>/dev/null
info "CA certificate: $CERTS_DIR/ca.crt"

# ── 2. Master certificate ─────────────────────────────────────────────────────
info "Generating Master server key and certificate..."
openssl genrsa -out master.key 2048 2>/dev/null

# SAN extension — add your master server IPs/hostnames here
cat > master.ext <<EOF
[req]
req_extensions = v3_req
distinguished_name = req_distinguished_name

[req_distinguished_name]

[v3_req]
basicConstraints = CA:FALSE
keyUsage = nonRepudiation, digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth
subjectAltName = @alt_names

[alt_names]
DNS.1 = master
DNS.2 = localhost
DNS.3 = dockermind-master
IP.1  = 127.0.0.1
IP.2  = 0.0.0.0
EOF

openssl req -new \
  -key master.key \
  -out master.csr \
  -subj "/C=IN/O=DockerMind/CN=dockermind-master" 2>/dev/null

openssl x509 -req \
  -in master.csr \
  -CA ca.crt -CAkey ca.key -CAcreateserial \
  -out master.crt \
  -days $DAYS \
  -sha256 \
  -extensions v3_req \
  -extfile master.ext 2>/dev/null

rm -f master.csr master.ext
info "Master certificate: $CERTS_DIR/master.crt"

# ── 3. Slave certificate ──────────────────────────────────────────────────────
info "Generating Slave client key and certificate..."
openssl genrsa -out slave.key 2048 2>/dev/null

cat > slave.ext <<EOF
[req]
req_extensions = v3_req
distinguished_name = req_distinguished_name

[req_distinguished_name]

[v3_req]
basicConstraints = CA:FALSE
keyUsage = nonRepudiation, digitalSignature, keyEncipherment
extendedKeyUsage = clientAuth
EOF

openssl req -new \
  -key slave.key \
  -out slave.csr \
  -subj "/C=IN/O=DockerMind/CN=dockermind-slave" 2>/dev/null

openssl x509 -req \
  -in slave.csr \
  -CA ca.crt -CAkey ca.key -CAcreateserial \
  -out slave.crt \
  -days $DAYS \
  -sha256 \
  -extensions v3_req \
  -extfile slave.ext 2>/dev/null

rm -f slave.csr slave.ext

# ── 4. Set permissions ────────────────────────────────────────────────────────
chmod 600 *.key
chmod 644 *.crt

cd - >/dev/null

info ""
info "Certificates generated in $CERTS_DIR:"
ls -lh "$CERTS_DIR"

# ── 5. Copy slave certs to slave directory ────────────────────────────────────
mkdir -p ./slave/certs
cp "$CERTS_DIR/ca.crt"    ./slave/certs/ca.crt
cp "$CERTS_DIR/slave.crt" ./slave/certs/slave.crt
cp "$CERTS_DIR/slave.key" ./slave/certs/slave.key
info "Slave certs copied to ./slave/certs/"

echo ""
echo -e "${GREEN}Done!${NC} Next step: docker compose up --build"