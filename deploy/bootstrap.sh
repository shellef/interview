#!/usr/bin/env bash
# Run once on a fresh Ubuntu server to set up the interview app.
# Usage: bash bootstrap.sh <domain>
# Example: bash bootstrap.sh stream-capture.updatenowapp.com
set -euo pipefail

DOMAIN="${1:?Usage: bash bootstrap.sh <domain>}"
APP_DIR="/home/ubuntu/interview"
VENV_DIR="/home/ubuntu/venv"

echo "==> Installing system packages"
sudo apt-get update -q
sudo apt-get install -y -q debian-keyring debian-archive-keyring apt-transport-https curl

# Install Caddy if not present
if ! command -v caddy &>/dev/null; then
    echo "==> Installing Caddy"
    curl -fsSL https://dl.cloudsmith.io/public/caddy/stable/gpg.key \
        | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    curl -fsSL https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt \
        | sudo tee /etc/apt/sources.list.d/caddy-stable.list
    sudo apt-get update -q
    sudo apt-get install -y -q caddy
fi

echo "==> Creating Python venv"
python3 -m venv "$VENV_DIR"

echo "==> Installing Python dependencies"
"$VENV_DIR/bin/pip" install --quiet -r "$APP_DIR/requirements.txt"

echo "==> Setting file permissions for Caddy"
chmod o+x /home/ubuntu
chmod -R o+r "$APP_DIR/frontend/dist"

echo "==> Writing Caddy config"
sudo tee /etc/caddy/Caddyfile > /dev/null << CADDYEOF
$DOMAIN {
    root * $APP_DIR/frontend/dist
    file_server

    handle /interview/* {
        reverse_proxy localhost:8000
    }

    handle /voice/* {
        reverse_proxy localhost:8000
    }
}
CADDYEOF

sudo systemctl reload caddy

echo "==> Installing systemd services"
sudo tee /etc/systemd/system/interview-api.service > /dev/null << 'SVCEOF'
[Unit]
Description=Interview API (FastAPI)
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/interview/backend
EnvironmentFile=/home/ubuntu/interview/.env
ExecStart=/home/ubuntu/venv/bin/uvicorn app:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SVCEOF

sudo tee /etc/systemd/system/interview-agent.service > /dev/null << 'SVCEOF'
[Unit]
Description=Interview Voice Agent (LiveKit)
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/interview/backend
EnvironmentFile=/home/ubuntu/interview/.env
ExecStart=/home/ubuntu/venv/bin/python voice_agent.py start
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SVCEOF

sudo systemctl daemon-reload
sudo systemctl enable --now interview-api
sudo systemctl enable --now interview-agent

echo ""
echo "==> Done. Services status:"
sudo systemctl status interview-api --no-pager | grep -E "Active|running|failed"
sudo systemctl status interview-agent --no-pager | grep -E "Active|running|failed"
echo ""
echo "App live at https://$DOMAIN"
