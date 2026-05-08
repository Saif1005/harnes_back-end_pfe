#!/usr/bin/env bash
set -euo pipefail

# Deploy harness stack to a specific EC2 instance.
# Default values aligned with provided infrastructure details.
#
# Usage:
#   ./scripts/deploy_harness_to_instance.sh
#   INSTANCE_ID=i-xxxx KEY_PATH=/abs/path/key.pem ./scripts/deploy_harness_to_instance.sh
#   SSH_USER=ubuntu REMOTE_DIR=/home/ubuntu/projet_industriel_agi ./scripts/deploy_harness_to_instance.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

INSTANCE_ID="${INSTANCE_ID:-i-04a73e357a7343429}"
KEY_PATH="${KEY_PATH:-/home/saifakkari/PFE_Saif/saif_pipeline.pem}"
SSH_USER="${SSH_USER:-ubuntu}"
REMOTE_DIR="${REMOTE_DIR:-/home/ubuntu/projet_industriel_agi}"

command -v aws >/dev/null || {
  echo "aws CLI is required (install and configure credentials)." >&2
  exit 1
}
command -v ssh >/dev/null || {
  echo "ssh is required." >&2
  exit 1
}

if [[ ! -f "$KEY_PATH" ]]; then
  echo "Key not found: $KEY_PATH" >&2
  exit 1
fi

chmod 600 "$KEY_PATH"

PUBLIC_HOST="$(aws ec2 describe-instances \
  --instance-ids "$INSTANCE_ID" \
  --query 'Reservations[0].Instances[0].PublicIpAddress' \
  --output text)"

if [[ -z "$PUBLIC_HOST" || "$PUBLIC_HOST" == "None" ]]; then
  echo "Unable to resolve public IP for instance $INSTANCE_ID" >&2
  exit 1
fi

echo "Deploy target: $INSTANCE_ID ($PUBLIC_HOST)"

RSYNC_SSH_KEY="$KEY_PATH" RSYNC_HOST="$PUBLIC_HOST" RSYNC_USER="$SSH_USER" REMOTE_DIR="$REMOTE_DIR" \
  "$SCRIPT_DIR/rsync_to_ec2.sh" full

SSH_OPTS=(-i "$KEY_PATH" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null)

REMOTE_HOST="$PUBLIC_HOST" KEY_PATH="$KEY_PATH" SSH_USER="$SSH_USER" "$SCRIPT_DIR/bootstrap_instance_runtime.sh"

ssh "${SSH_OPTS[@]}" "$SSH_USER@$PUBLIC_HOST" \
  "cd '$REMOTE_DIR' && docker compose -f docker-compose.harness.yml up -d --build"

echo "Harness deployment finished on $PUBLIC_HOST"

