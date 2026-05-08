#!/usr/bin/env bash
set -euo pipefail

# Bootstrap runtime stack on EC2 instance:
# - install Docker + compose plugin if missing
# - install Ollama if missing
# - create persistent directories for data/models/db
# - pull recipe/orchestrator LLM models
#
# Usage:
#   REMOTE_HOST=13.x.x.x KEY_PATH=/abs/key.pem ./scripts/bootstrap_instance_runtime.sh

KEY_PATH="${KEY_PATH:-/home/saifakkari/PFE_Saif/saif_pipeline.pem}"
REMOTE_HOST="${REMOTE_HOST:-}"
SSH_USER="${SSH_USER:-ubuntu}"

if [[ -z "$REMOTE_HOST" ]]; then
  echo "Set REMOTE_HOST=<public-ip-or-dns>" >&2
  exit 1
fi
if [[ ! -f "$KEY_PATH" ]]; then
  echo "Key not found: $KEY_PATH" >&2
  exit 1
fi

chmod 600 "$KEY_PATH"
SSH_OPTS=(-i "$KEY_PATH" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null)

ssh "${SSH_OPTS[@]}" "$SSH_USER@$REMOTE_HOST" "$(cat <<'EOF'
set -euo pipefail

sudo mkdir -p /opt/harness/data /opt/harness/models /opt/harness/db /opt/harness/logs
sudo chown -R "$USER":"$USER" /opt/harness

if ! command -v docker >/dev/null 2>&1; then
  sudo apt-get update
  sudo apt-get install -y docker.io docker-compose-plugin
  sudo systemctl enable docker
  sudo systemctl start docker
fi

if ! command -v ollama >/dev/null 2>&1; then
  curl -fsSL https://ollama.com/install.sh | sh
fi
sudo systemctl enable ollama || true
sudo systemctl restart ollama || true

ollama pull mistral:7b
ollama pull qwen2.5:7b

echo "Runtime bootstrap finished."
EOF
)"

