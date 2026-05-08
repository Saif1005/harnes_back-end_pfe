#!/usr/bin/env bash
# Synchronise le dossier projet (docker-compose.yml, .env, code, etc.) vers l’EC2.
# Même exclusions que Terraform (variables.tf → deploy_rsync_excludes). Le fichier
# .env n’est jamais exclu : il est copié s’il existe localement (pensez à le créer
# avant le rsync ; il reste hors Git via .gitignore).
#
# Usage :
#   export RSYNC_SSH_KEY=/chemin/vers/saif_pipeline.pem
#   export RSYNC_HOST=<IP_publique_ou_DNS>
#   # optionnel : RSYNC_USER=ubuntu REMOTE_DIR=/home/ubuntu/projet_industriel_agi
#
#   # Déploiement complet (code + docker-compose.yml + .env)
#   ./scripts/rsync_to_ec2.sh
#
#   # Rapide : uniquement docker-compose.yml et .env (mises à jour config / secrets)
#   ./scripts/rsync_to_ec2.sh compose-env
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

: "${RSYNC_SSH_KEY:?Définir RSYNC_SSH_KEY (chemin absolu vers la clé .pem)}"
: "${RSYNC_HOST:?Définir RSYNC_HOST (IP ou DNS public de l’instance)}"

RSYNC_USER="${RSYNC_USER:-ubuntu}"
REMOTE_DIR="${REMOTE_DIR:-/home/ubuntu/projet_industriel_agi}"

# Même options SSH que le provisioner Terraform (main.tf → deploy_compose_rsync).
SSH_CMD=(ssh -i "${RSYNC_SSH_KEY}" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ServerAliveInterval=30 -o ServerAliveCountMax=240)

command -v rsync >/dev/null || {
  echo "Erreur : installez rsync (ex. sudo apt install rsync)" >&2
  exit 1
}

MODE="${1:-full}"

if [[ "$MODE" == "compose-env" ]]; then
  echo "Sync rapide : docker-compose.yml (+ .env si présent) → $RSYNC_USER@$RSYNC_HOST:$REMOTE_DIR/"
  rsync -az --partial --human-readable \
    -e "${SSH_CMD[*]}" \
    "${PROJECT_ROOT}/docker-compose.yml" \
    "${RSYNC_USER}@${RSYNC_HOST}:${REMOTE_DIR}/"
  if [[ -f "${PROJECT_ROOT}/.env" ]]; then
    rsync -az --partial --human-readable \
      -e "${SSH_CMD[*]}" \
      "${PROJECT_ROOT}/.env" \
      "${RSYNC_USER}@${RSYNC_HOST}:${REMOTE_DIR}/"
  else
    echo "Note : pas de ${PROJECT_ROOT}/.env localement — rien à copier pour les secrets." >&2
  fi
  echo "OK (compose-env). Sur l’instance : cd $REMOTE_DIR && docker compose up -d --build"
  exit 0
fi

if [[ "$MODE" != "full" ]]; then
  echo "Usage: $0 [full|compose-env]" >&2
  exit 1
fi

# Aligné sur terraform/variables.tf — default deploy_rsync_excludes
EXCLUDES=(
  ".git/"
  "local_models/"
  ".terraform/"
  "__pycache__/"
  ".cursor/"
  "*.pyc"
  "agent_pdr_microservice/models_saved/xlm_roberta_large_mp_chimie/"
)

EXCLUDE_ARGS=()
for x in "${EXCLUDES[@]}"; do
  EXCLUDE_ARGS+=(--exclude="$x")
done

echo "Sync : $PROJECT_ROOT/ → $RSYNC_USER@$RSYNC_HOST:$REMOTE_DIR/"
rsync -az --partial --human-readable \
  "${EXCLUDE_ARGS[@]}" \
  -e "${SSH_CMD[*]}" \
  "${PROJECT_ROOT}/" \
  "${RSYNC_USER}@${RSYNC_HOST}:${REMOTE_DIR}/"

echo "OK. Sur l’instance : cd $REMOTE_DIR && docker compose pull && docker compose up -d --build (selon besoin)."
