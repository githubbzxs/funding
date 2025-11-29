#!/usr/bin/env bash
# One-click deployment script for the Funding Rate Arbitrage Monitor on Linux (systemd).
# Usage: sudo bash deploy.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_NAME="${APP_NAME:-funding-monitor}"
APP_DIR="${APP_DIR:-$SCRIPT_DIR}"
APP_USER="${APP_USER:-${SUDO_USER:-$(whoami)}}"
PORT="${PORT:-8000}"
HOST="${HOST:-0.0.0.0}"
WORKERS="${WORKERS:-1}"
VENV_PATH="${VENV_PATH:-$APP_DIR/.venv}"

pkg_install() {
  if command -v apt-get >/dev/null 2>&1; then
    apt-get update -y && apt-get install -y "$@"
  elif command -v dnf >/dev/null 2>&1; then
    dnf install -y "$@"
  elif command -v yum >/dev/null 2>&1; then
    yum install -y "$@"
  else
    echo "No supported package manager found (apt, dnf, yum)." >&2
    exit 1
  fi
}

ensure_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "==> Installing dependency '$1'"
    case "$1" in
      python3) pkg_install python3 ;;
      pip|pip3) pkg_install python3-pip ;;
      systemctl) pkg_install systemd ;;
      git) pkg_install git ;;
      *) pkg_install "$1" ;;
    esac
  fi
}

echo "==> Checking prerequisites (python3, pip, git, systemd)"
ensure_cmd python3
ensure_cmd pip3 || ensure_cmd pip
ensure_cmd git
ensure_cmd systemctl

ensure_venv() {
  if python3 - <<'PY' >/dev/null 2>&1; then
import venv, ensurepip  # noqa: F401
PY
  then
    return
  fi
  echo "==> Installing python3 venv/ensurepip support"
  pyver="$(python3 -c 'import sys; print(f\"{sys.version_info.major}.{sys.version_info.minor}\")' || echo '3')"
  set +e
  if command -v apt-get >/dev/null 2>&1; then
    apt-get update -y
    apt-get install -y python3-venv "python${pyver}-venv" python3-pip
  elif command -v dnf >/dev/null 2>&1; then
    dnf install -y python3-virtualenv python3-pip || true
    dnf install -y python3-venv || true
  elif command -v yum >/dev/null 2>&1; then
    yum install -y python3-virtualenv python3-pip || true
    yum install -y python3-venv || true
  else
    echo "No supported package manager found for python venv." >&2
    exit 1
  fi
  set -e
}

ensure_venv

echo "==> Creating virtual environment at $VENV_PATH"
python3 -m venv "$VENV_PATH"
# shellcheck source=/dev/null
if ! "$VENV_PATH/bin/python" -m ensurepip --upgrade >/dev/null 2>&1; then
  echo "Warning: ensurepip inside venv failed; pip may already be present."
fi
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
