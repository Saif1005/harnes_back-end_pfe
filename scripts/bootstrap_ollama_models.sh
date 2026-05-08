#!/usr/bin/env bash
set -euo pipefail

# Install Ollama (if missing) and pull required models on remote instance.
#
# Usage:
#   REMOTE_HOST=<public-ip> KEY_PATH=/abs/key.pem ./scripts/bootstrap_ollama_models.sh

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
if ! command -v ollama >/dev/null 2>&1; then
  curl -fsSL https://ollama.com/install.sh | sh
fi
sudo systemctl enable ollama || true
sudo systemctl restart ollama || true
ollama pull mistral:7b
ollama pull qwen2.5:7b
echo "Ollama models ready."
EOF
)"

