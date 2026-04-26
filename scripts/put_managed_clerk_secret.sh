#!/usr/bin/env bash
# Put Clerk secret key into the Terraform-managed Secrets Manager placeholder for an environment.
#
# Usage:
#   export CLERK_SECRET_KEY='sk_live_...'
#   bash scripts/put_managed_clerk_secret.sh dev
set -euo pipefail
ENV="${1:?usage: $0 dev|test|prod}"
case "${ENV}" in dev | test | prod) ;; *)
  echo "usage: $0 dev|test|prod" >&2
  exit 1
  ;;
esac
: "${CLERK_SECRET_KEY:?set CLERK_SECRET_KEY (Clerk secret key)}"
SID="fleet-health-copilot-${ENV}/CLERK_SECRET_KEY"
aws secretsmanager put-secret-value --secret-id "${SID}" --secret-string "${CLERK_SECRET_KEY}"
echo "Updated ${SID}"
