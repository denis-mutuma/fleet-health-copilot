#!/usr/bin/env bash
# Print values to copy into GitHub → Settings → Environments → <dev|test|prod> → Secrets.
# Requires: infra/terraform/backend.tf, AWS credentials, and an applied stack for the environment.
#
# Usage: bash scripts/print_github_environment_hints.sh dev
set -euo pipefail
ENV="${1:?usage: $0 dev|test|prod}"
case "${ENV}" in dev | test | prod) ;; *)
  echo "usage: $0 dev|test|prod" >&2
  exit 1
  ;;
esac
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
bash "${ROOT}/scripts/terraform_init_env.sh" "$ENV"
cd "${ROOT}/infra/terraform"

echo ""
echo "=== GitHub Environment: ${ENV} ==="
echo ""
echo "Secret: AWS_ROLE_ARN"
terraform output -raw github_actions_role_arn 2>/dev/null && echo "" || echo "  (empty: set github_repository and apply first)"
echo ""
echo "Secrets: TF_STATE_BUCKET and TF_LOCK_TABLE — use the same names as in infra/terraform/backend.tf"
echo "  (bootstrap S3 bucket + DynamoDB lock table from infra/terraform/bootstrap-state)."
echo ""
echo "Secret: NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY — Clerk dashboard (publishable key)."
echo ""
echo "When ENABLE_ECS=true on the repo, add Environment secrets:"
echo "  VPC_ID, PUBLIC_SUBNET_IDS_JSON, WEB_NEXT_PUBLIC_ORCHESTRATOR_API_BASE_URL"
echo ""
echo "Populate runtime secrets after apply, e.g.:"
echo "  CLERK_SECRET_KEY=... bash scripts/put_managed_clerk_secret.sh ${ENV}"
