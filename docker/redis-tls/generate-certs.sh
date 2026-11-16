#!/usr/bin/env bash
# Self-signed CA + server certificate for the local TLS Redis (UN-4123).
#
# Only for local development: it stands in for a managed Redis endpoint so the
# TLS path can be exercised without cloud access or a VPN. Never use these
# anywhere else — the private keys are written unencrypted, right here.
#
# The SAN list covers both names the same server answers to: containers reach it
# as `unstract-redis-managed`, while a backend running on the host reaches the
# published port as `localhost`. A certificate valid for only one of them fails
# verification from the other side, which looks like a code bug and is not one.
set -euo pipefail

CERT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/certs"
mkdir -p "$CERT_DIR"
cd "$CERT_DIR"

if [[ -f server.crt && "${FORCE:-}" != "1" ]]; then
    echo "Certificates already exist in $CERT_DIR (FORCE=1 to regenerate)."
    exit 0
fi

openssl genrsa -out ca.key 4096 2>/dev/null
openssl req -x509 -new -nodes -key ca.key -sha256 -days 825 -out ca.crt \
    -subj "/CN=Unstract Local Redis Dev CA" 2>/dev/null

openssl genrsa -out server.key 2048 2>/dev/null
openssl req -new -key server.key -out server.csr \
    -subj "/CN=unstract-redis-managed" 2>/dev/null

cat > server.ext <<'EXT'
subjectAltName = DNS:unstract-redis-managed, DNS:localhost, IP:127.0.0.1
extendedKeyUsage = serverAuth
EXT

openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial \
    -out server.crt -days 825 -sha256 -extfile server.ext 2>/dev/null

# Redis runs as uid 999 in the official image and must read the key.
chmod 644 ca.crt server.crt server.key
rm -f server.csr server.ext ca.srl

echo "Wrote CA + server certificate to $CERT_DIR"
echo "  CA (for REDIS_SSL_CA_CERTS): $CERT_DIR/ca.crt"
