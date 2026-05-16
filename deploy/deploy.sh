#!/bin/bash
# Build frontend, commit dist, push to git, then pull and restart on server.
# Usage: ./deploy/deploy.sh <host>
# Example: ./deploy/deploy.sh stream-capture.updatenowapp.com
set -euo pipefail

HOST=${1:?Usage: deploy.sh <host>}
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Sync .env to server if present locally
if [ -f "$REPO_ROOT/.env.prod" ]; then
    echo "==> Syncing .env.prod to server"
    scp "$REPO_ROOT/.env.prod" ubuntu@"$HOST":/home/ubuntu/interview/.env
elif ! ssh ubuntu@"$HOST" "test -f /home/ubuntu/interview/.env"; then
    echo "ERROR: .env.prod not found locally and .env missing on server"
    exit 1
fi

# Update Caddyfile
echo "==> Updating Caddyfile"
scp "$SCRIPT_DIR/Caddyfile" ubuntu@"$HOST":/tmp/Caddyfile
ssh -n ubuntu@"$HOST" "sudo cp /tmp/Caddyfile /etc/caddy/Caddyfile && sudo systemctl reload caddy"

# Build frontend and commit dist
echo "==> Building frontend"
cd "$REPO_ROOT/frontend"
npm install --silent
npm run build

echo "==> Committing dist and pushing"
cd "$REPO_ROOT"
git add frontend/dist
git diff --cached --quiet || git commit -m "deploy: update frontend dist"
git push

# Pull and restart on server
echo "==> Deploying on server"
ssh -n ubuntu@"$HOST" '
    cd ~/interview
    git pull
    export PATH="$HOME/.local/bin:$PATH"
    uv sync
    chmod -R o+r frontend/dist
    sudo systemctl restart interview-api interview-agent
'

echo ""
echo "==> Done."
ssh -n ubuntu@"$HOST" 'sudo systemctl status interview-api interview-agent --no-pager | grep -E "Active|running|failed"'
