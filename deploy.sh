#!/usr/bin/env bash
# One-click deployment script for the Funding Rate Arbitrage Monitor on Linux (systemd).
# Usage: sudo bash deploy.sh

set -euo pipefail

APP_NAME="${APP_NAME:-funding-monitor}"
APP_DIR="${APP_DIR:-$(pwd)}"
APP_USER="${APP_USER:-$(whoami)}"
PORT="${PORT:-8000}"
HOST="${HOST:-0.0.0.0}"
WORKERS="${WORKERS:-1}"
VENV_PATH="${VENV_PATH:-$APP_DIR/.venv}"

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Error: missing required command '$1'. Please install it and rerun." >&2
    exit 1
  fi
}

echo "==> Checking prerequisites"
need_cmd python3
need_cmd pip
need_cmd systemctl

echo "==> Creating virtual environment at $VENV_PATH"
python3 -m venv "$VENV_PATH"
# shellcheck source=/dev/null
source "$VENV_PATH/bin/activate"
pip install --upgrade pip
pip install -r "$APP_DIR/requirements.txt"

SERVICE_FILE="/etc/systemd/system/${APP_NAME}.service"

echo "==> Writing systemd service to $SERVICE_FILE"
sudo tee "$SERVICE_FILE" >/dev/null <<EOF
[Unit]
Description=Funding Rate Arbitrage Monitor
After=network.target

[Service]
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$APP_DIR
Environment="PORT=$PORT" "HOST=$HOST" "WORKERS=$WORKERS"
ExecStart=$VENV_PATH/bin/uvicorn app:app --host $HOST --port $PORT --workers $WORKERS
Restart=on-failure
RestartSec=5
KillSignal=SIGINT
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
EOF

echo "==> Enabling and starting ${APP_NAME}.service"
sudo systemctl daemon-reload
sudo systemctl enable --now "${APP_NAME}.service"

echo "==> Done. Service status:"
sudo systemctl status "${APP_NAME}.service" --no-pager || true
echo "Visit: http://$HOST:$PORT"
