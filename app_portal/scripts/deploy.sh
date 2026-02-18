#!/bin/bash
set -e

echo "=== Subseatec App Portal - Deployment Setup ==="
echo ""

cd "$(dirname "$0")/.."

# 1. Generate .env if missing
if [ ! -f .env ]; then
    echo "Generating .env with random secrets..."
    cat > .env << EOF
# Portal
PORTAL_SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
ADMIN_USERNAME=admin
ADMIN_PASSWORD=$(python3 -c "import secrets; print(secrets.token_urlsafe(16))")

# App secrets
ACCRUEDINCOME_SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
DURABLER2_SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
HEATSIM_SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
MG5_SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
EOF
    echo "  .env created. Review and adjust as needed."
    echo "  Admin password: $(grep ADMIN_PASSWORD .env | cut -d= -f2)"
    echo ""
else
    echo "  .env already exists, skipping."
fi

# 2. Generate SSL certificate if missing
if [ ! -f nginx/ssl/server.crt ]; then
    echo "Generating self-signed SSL certificate..."
    mkdir -p nginx/ssl
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout nginx/ssl/server.key \
        -out nginx/ssl/server.crt \
        -subj "/C=SE/ST=VastraGotaland/L=Gothenburg/O=Subseatec/CN=$(hostname -I 2>/dev/null | awk '{print $1}' || echo 'localhost')" \
        2>/dev/null
    echo "  SSL certificate generated."
    echo ""
else
    echo "  SSL certificate already exists, skipping."
fi

# 3. Build and start
echo ""
echo "Building Docker images..."
docker compose build

echo ""
echo "Starting services..."
docker compose up -d

echo ""
echo "=== Deployment Complete ==="
echo ""
echo "Services:"
docker compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"
echo ""
echo "Access the portal at: https://$(hostname -I 2>/dev/null | awk '{print $1}' || echo 'localhost')"
echo ""
