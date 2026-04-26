#!/usr/bin/env bash
# Point the root module at the correct remote state key for dev | test | prod, then terraform init.
# Your infra/terraform/backend.tf must define bucket, region, dynamodb_table, encrypt (see backend.tf.example).
#
# Usage (from repo root):
#   bash scripts/terraform_init_env.sh dev
#   terraform plan -var-file=env/dev.tfvars -var='github_repository=OWNER/REPO'
#
# Never run plan/apply with env/prod.tfvars unless you initialized with backend-config/prod.hcl
# and terraform state list shows prod resources (or an empty state for a greenfield prod).
set -euo pipefail
ENV="${1:-}"
case "${ENV}" in
  dev | test | prod) ;;
  *)
    echo "usage: $0 dev|test|prod" >&2
    exit 1
    ;;
esac
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TF_DIR="${ROOT}/infra/terraform"
BACKEND_FRAG="${TF_DIR}/backend-config/${ENV}.hcl"
if [[ ! -f "${BACKEND_FRAG}" ]]; then
  echo "missing ${BACKEND_FRAG}" >&2
  exit 1
fi
if [[ ! -f "${TF_DIR}/backend.tf" ]]; then
  echo "missing ${TF_DIR}/backend.tf — copy infra/terraform/backend.tf.example and edit bucket/region/dynamodb_table." >&2
  exit 1
fi
terraform -chdir="${TF_DIR}" init -reconfigure -backend-config="${BACKEND_FRAG}" "${@:2}"
