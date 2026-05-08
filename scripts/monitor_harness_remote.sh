#!/usr/bin/env bash
set -euo pipefail

# Remote monitoring probe for Jenkins.
# Checks docker services + health endpoints on EC2 target.

: "${SSH_HOST:?Set SSH_HOST}"
: "${SSH_KEY_PATH:?Set SSH_KEY_PATH}"
SSH_USER="${SSH_USER:-ubuntu}"
REMOTE_DIR="${REMOTE_DIR:-/home/ubuntu/projet_industriel_agi}"

SSH_OPTS=(-i "$SSH_KEY_PATH" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null)

ssh "${SSH_OPTS[@]}" "$SSH_USER@$SSH_HOST" "cd '$REMOTE_DIR' && docker compose -f docker-compose.harness.yml ps"

ssh "${SSH_OPTS[@]}" "$SSH_USER@$SSH_HOST" "curl -fsS http://127.0.0.1:8030/health"
ssh "${SSH_OPTS[@]}" "$SSH_USER@$SSH_HOST" "curl -fsS http://127.0.0.1:8030/system/protocols"
ssh "${SSH_OPTS[@]}" "$SSH_USER@$SSH_HOST" "curl -fsS -X POST http://127.0.0.1:8040/mcp/tool-call -H 'Content-Type: application/json' -d '{\"source_agent\":\"monitor\",\"target_tool\":\"stock_check\",\"payload\":{\"query\":\"probe\"},\"context\":{\"trace_id\":\"jenkins-probe\"}}'"

echo "Remote harness monitoring checks passed."

