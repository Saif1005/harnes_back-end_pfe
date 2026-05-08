#!/usr/bin/env bash
set -euo pipefail

# Trigger classification + prediction training jobs on remote EC2.
# Assumes project already synced to REMOTE_DIR.
#
# Usage:
#   REMOTE_HOST=13.x.x.x KEY_PATH=/abs/key.pem ./scripts/run_remote_training.sh

KEY_PATH="${KEY_PATH:-/home/saifakkari/PFE_Saif/saif_pipeline.pem}"
REMOTE_HOST="${REMOTE_HOST:-}"
SSH_USER="${SSH_USER:-ubuntu}"
REMOTE_DIR="${REMOTE_DIR:-/home/ubuntu/projet_industriel_agi}"

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

ssh "${SSH_OPTS[@]}" "$SSH_USER@$REMOTE_HOST" \
  "cd '$REMOTE_DIR' && docker compose -f harness_backend/docker/training/docker-compose.training.yml run --rm harness-train-classification && docker compose -f harness_backend/docker/training/docker-compose.training.yml run --rm harness-train-prediction"

echo "Remote training finished."

