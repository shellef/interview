#!/usr/bin/env bash
# Push local changes to the server and restart services.
# Usage: bash deploy.sh [host]
# Default host: ubuntu@stream-capture.updatenowapp.com
set -euo pipefail

HOST="${1:-ubuntu@stream-capture.updatenowapp.com}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "==> Building frontend"
cd "$REPO_ROOT/frontend"
npm install --silent
npm run build

echo "==> Syncing files to $HOST"
rsync -az --delete \
    --exclude='.git' \
    --exclude='.claude' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='node_modules' \
    --exclude='frontend/src' \
    --exclude='research' \
    "$REPO_ROOT/" "$HOST:~/interview/"

echo "==> Installing any new Python dependencies"
ssh "$HOST" '/home/ubuntu/venv/bin/pip install --quiet -r /home/ubuntu/interview/requirements.txt'

echo "==> Fixing permissions"
ssh "$HOST" 'chmod -R o+r /home/ubuntu/interview/frontend/dist'

echo "==> Restarting services"
ssh "$HOST" 'sudo systemctl restart interview-api interview-agent'

echo ""
echo "==> Done. Service status:"
ssh "$HOST" 'sudo systemctl status interview-api interview-agent --no-pager | grep -E "Active|running|failed"'
