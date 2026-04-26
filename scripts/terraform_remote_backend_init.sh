#!/usr/bin/env bash
# Write infra/terraform/backend.ci.hcl from environment variables, then run terraform init.
# Use after bootstrap-state (S3 + DynamoDB) is applied. Example:
#   export TF_STATE_BUCKET=my-account-fleet-health-tf-state
#   export TF_LOCK_TABLE=fleet-health-copilot-tf-locks
#   export TF_STATE_KEY=fleet-health-copilot/dev/terraform.tfstate
#   export AWS_REGION=us-east-1
#   bash scripts/terraform_remote_backend_init.sh
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TF_DIR="${ROOT}/infra/terraform"
: "${TF_STATE_BUCKET:?set TF_STATE_BUCKET (S3 state bucket name)}"
: "${TF_LOCK_TABLE:?set TF_LOCK_TABLE (DynamoDB lock table name)}"
AWS_REGION="${AWS_REGION:-us-east-1}"
TF_STATE_KEY="${TF_STATE_KEY:-fleet-health-copilot/dev/terraform.tfstate}"

cat >"${TF_DIR}/backend.ci.hcl" <<EOF
bucket         = "${TF_STATE_BUCKET}"
key            = "${TF_STATE_KEY}"
region         = "${AWS_REGION}"
dynamodb_table = "${TF_LOCK_TABLE}"
encrypt        = true
EOF

echo "Wrote ${TF_DIR}/backend.ci.hcl (add backend.ci.hcl to .gitignore if you keep it locally)."
terraform -chdir="${TF_DIR}" init -input=false -backend-config=backend.ci.hcl "$@"
