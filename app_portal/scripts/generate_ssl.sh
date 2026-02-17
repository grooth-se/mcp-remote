#!/bin/bash
# Generate self-signed SSL certificate for the portal

SSL_DIR="$(dirname "$0")/../nginx/ssl"
mkdir -p "$SSL_DIR"

openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout "$SSL_DIR/server.key" \
    -out "$SSL_DIR/server.crt" \
    -subj "/C=SE/ST=VastraGotaland/L=Gothenburg/O=Subseatec/CN=172.27.55.104"

echo "SSL certificate generated in $SSL_DIR"
