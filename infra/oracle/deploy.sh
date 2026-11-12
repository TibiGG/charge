#!/usr/bin/env bash
# Ship the live Charge backend (this checkout) to the Oracle VM and (re)start it. Safe to run again.
# CI does the same on every push to main; the dev stack is deployed by CI from the `dev` branch.
#   infra/oracle/deploy.sh            # IP from `terraform output`
#   infra/oracle/deploy.sh 1.2.3.4
# Secrets live in ~/.config/charge/oracle.env (made on first run, chmod 600, never committed).
# Optional in that file: SMTP_HOST SMTP_PORT SMTP_USER SMTP_PASSWORD SMTP_SENDER,
# GOOGLE_CLIENT_ID GOOGLE_CLIENT_SECRET, APPLE_CLIENT_ID APPLE_CLIENT_SECRET, CONTACT_EMAIL.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
IP="${1:-$(cd "$HERE" && terraform output -raw public_ip)}"
KEY="${SSH_KEY:-$HOME/.ssh/charge_oracle_ed25519}"
SSH="ssh -i $KEY -o StrictHostKeyChecking=accept-new ubuntu@$IP"
BASE="${IP//./-}.sslip.io"
SECRETS="$HOME/.config/charge/oracle.env"

mkdir -p "$(dirname "$SECRETS")"
if [ ! -f "$SECRETS" ]; then
  umask 077
  cat > "$SECRETS" <<ENV
PB_ADMIN_EMAIL=admin@charge.local
PB_ADMIN_PASSWORD=$(openssl rand -base64 30 | tr -dc 'A-Za-z0-9' | head -c 32)
ENV
fi
set -a; . "$SECRETS"; set +a
API_HOST="${API_HOST:-api.$BASE}"
PB_HOST="${PB_HOST:-pb.$BASE}"
API_DEV_HOST="${API_DEV_HOST:-api-dev.$BASE}"
PB_DEV_HOST="${PB_DEV_HOST:-pb-dev.$BASE}"
CORS_ORIGINS="${CORS_ORIGINS:-https://charge-bupa.vercel.app}"

echo "→ waiting for cloud-init on $IP"
$SSH 'cloud-init status --wait >/dev/null 2>&1 || true; docker --version'

echo "→ copying code"
rsync -az --delete -e "ssh -i $KEY" \
  --exclude __pycache__ --exclude .pytest_cache --exclude pb_data --exclude '.terraform*' --exclude '*.tfstate*' \
  --exclude terraform.tfvars --exclude plan.out \
  "$ROOT/backend" "$ROOT/pocketbase" "$ROOT/infra" "ubuntu@$IP:/opt/charge/"
printf 'PB_ADMIN_EMAIL=%s\nPB_ADMIN_PASSWORD=%s\nAPI_HOST=%s\nPB_HOST=%s\nAPI_DEV_HOST=%s\nPB_DEV_HOST=%s\nCORS_ORIGINS=%s\n' \
  "$PB_ADMIN_EMAIL" "$PB_ADMIN_PASSWORD" "$API_HOST" "$PB_HOST" "$API_DEV_HOST" "$PB_DEV_HOST" "$CORS_ORIGINS" \
  | $SSH 'umask 077; cat > /opt/charge/infra/oracle/.env'

echo "→ building and starting (first build takes a few minutes)"
$SSH "cd /opt/charge/infra/oracle && (sudo docker network create charge-edge >/dev/null 2>&1 || true) && \
  sudo docker compose up -d --build --remove-orphans && sleep 3 && \
  sudo docker compose exec -T pocketbase /pb/pocketbase superuser upsert '$PB_ADMIN_EMAIL' '$PB_ADMIN_PASSWORD' --dir /pb/pb_data >/dev/null"

echo "→ configuring PocketBase"
for i in $(seq 1 30); do curl -fsS "https://$PB_HOST/api/health" >/dev/null 2>&1 && break; sleep 5; done
PB_URL="https://$PB_HOST" python3 "$HERE/configure_pb.py"

curl -fsS "https://$API_HOST/api/health" && echo
echo "API:        https://$API_HOST"
echo "PocketBase: https://$PB_HOST   (admin UI: https://$PB_HOST/_/ ; login in $SECRETS)"
