#!/bin/bash
# One-time server setup for the interview app.
# Run as root: sudo bash bootstrap.sh
set -euo pipefail

APP_DIR="/home/ubuntu/interview"
DOMAIN="stream-capture.updatenowapp.com"

echo "==> Installing system packages"
apt-get update -q
apt-get install -y -q git

# Install uv for ubuntu user if not present
if ! su - ubuntu -c "command -v uv" &>/dev/null; then
    echo "==> Installing uv"
    su - ubuntu -c "curl -LsSf https://astral.sh/uv/install.sh | sh"
fi

# Install Caddy if not present
if ! command -v caddy &>/dev/null; then
    echo "==> Installing Caddy"
    apt-get install -y -q debian-keyring debian-archive-keyring apt-transport-https curl
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
        | gpg --batch --no-tty --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
        | tee /etc/apt/sources.list.d/caddy-stable.list
    apt-get update -q
    apt-get install -y -q caddy
fi

echo "==> Cloning repo"
if [ ! -d "$APP_DIR/.git" ]; then
    git clone https://github.com/shellef/interview.git "$APP_DIR"
    chown -R ubuntu:ubuntu "$APP_DIR"
fi

echo "==> Installing Python dependencies"
su - ubuntu -c "cd $APP_DIR && ~/.local/bin/uv sync"

echo "==> Setting file permissions for Caddy"
chmod o+x /home/ubuntu
chmod -R o+r "$APP_DIR/frontend/dist"

echo "==> Writing Caddyfile"
cp "$APP_DIR/deploy/Caddyfile" /etc/caddy/Caddyfile
systemctl reload caddy

echo "==> Installing systemd services"
cat > /etc/systemd/system/interview-api.service << 'EOF'
[Unit]
Description=Interview API (FastAPI)
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/interview/backend
EnvironmentFile=/home/ubuntu/interview/.env
ExecStart=/home/ubuntu/.local/bin/uv run --directory /home/ubuntu/interview uvicorn app:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/interview-agent.service << 'EOF'
[Unit]
Description=Interview Voice Agent (LiveKit)
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/interview/backend
EnvironmentFile=/home/ubuntu/interview/.env
ExecStart=/home/ubuntu/.local/bin/uv run --directory /home/ubuntu/interview python voice_agent.py start
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now interview-api
systemctl enable --now interview-agent

echo ""
echo "=== Setup complete ==="
echo ""
echo "Next steps:"
echo "  1. Place .env at $APP_DIR/.env"
echo "  2. sudo systemctl restart interview-api interview-agent"
echo ""
echo "App will be live at https://$DOMAIN"
