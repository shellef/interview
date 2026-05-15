# Deployment

## Fresh server

Requirements: Ubuntu 22.04+, SSH access as `ubuntu`, `.env` already on the server at `~/interview/.env`.

1. Copy the project to the server:
   ```bash
   rsync -az --exclude='.git' --exclude='node_modules' --exclude='__pycache__' \
       ./ ubuntu@<host>:~/interview/
   ```

2. SSH in and run bootstrap:
   ```bash
   ssh ubuntu@<host>
   bash ~/interview/deploy/bootstrap.sh <domain>
   ```

## .env required keys

```
ANTHROPIC_API_KEY=
LIVEKIT_URL=wss://...
LIVEKIT_API_KEY=
LIVEKIT_API_SECRET=
CEREBRAS_API_KEY=
DEEPGRAM_API_KEY=
```

## Push updates

From your local machine:
```bash
bash deploy/deploy.sh
# or for a different host:
bash deploy/deploy.sh ubuntu@other-host.example.com
```

## Services

| Service | Description |
|---|---|
| `interview-api` | FastAPI backend on `127.0.0.1:8000` |
| `interview-agent` | LiveKit voice agent worker |
| `caddy` | HTTPS reverse proxy + static file server |

```bash
# Check logs
sudo journalctl -u interview-api -f
sudo journalctl -u interview-agent -f
```
