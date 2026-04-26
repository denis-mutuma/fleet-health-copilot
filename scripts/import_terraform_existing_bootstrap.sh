#!/usr/bin/env bash
# Import bootstrap resources that already exist in AWS into the current Terraform
# state (e.g. after a new remote backend, empty state, or drift from a partial apply).
# Run with AWS credentials and the same backend/init as deploy-aws.
#
# Usage (after terraform init in infra/terraform with the correct backend):
#   bash scripts/import_terraform_existing_bootstrap.sh prod
#
# Optional: GITHUB_REPOSITORY=owner/repo (defaults from `git remote get-url origin`)
# Optional: PROJECT_NAME=fleet-health-copilot (must match Terraform project_name)
set -euo pipefail

ENVIRONMENT="${1:?usage: $0 <dev|test|prod>}"
case "$ENVIRONMENT" in dev|test|prod) ;; *)
  echo "error: environment must be dev, test, or prod" >&2
  exit 1
  ;;
esac

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_NAME="${PROJECT_NAME:-fleet-health-copilot}"
NAME_PREFIX="${PROJECT_NAME}-${ENVIRONMENT}"

resolve_github_repository() {
  if [[ -n "${GITHUB_REPOSITORY:-}" ]]; then
    printf '%s' "$GITHUB_REPOSITORY"
    return 0
  fi
  local url
  url=$(git -C "$ROOT" remote get-url origin 2>/dev/null || true)
  [[ -n "$url" ]] || return 1
  if [[ "$url" =~ ^git@github\.com:([^/]+)/([^/.]+)(\.git)?$ ]]; then
    printf '%s/%s' "${BASH_REMATCH[1]}" "${BASH_REMATCH[2]}"
    return 0
  fi
  if [[ "$url" =~ ^https://github\.com/([^/]+)/([^/.]+)(\.git)?$ ]]; then
    printf '%s/%s' "${BASH_REMATCH[1]}" "${BASH_REMATCH[2]}"
    return 0
  fi
  return 1
}

GH_REPO="$(resolve_github_repository)" || {
  echo "error: set GITHUB_REPOSITORY=owner/repo (Terraform needs github_repository for IAM/ECR resources)." >&2
  exit 1
}

cd "$ROOT/infra/terraform"

common_tf_args=(
  -var-file="env/${ENVIRONMENT}.tfvars"
  -var="github_repository=${GH_REPO}"
)

import_or_skip() {
  local addr="$1"
  local id="$2"
  local out rc
  set +e
  out=$(terraform import "${common_tf_args[@]}" "$addr" "$id" 2>&1)
  rc=$?
  set -e
  if [[ "$rc" -eq 0 ]]; then
    printf '%s\n' "$out"
    return 0
  fi
  if grep -qE 'Resource already managed by Terraform|already in state' <<<"$out"; then
    echo "skip (already in state): $addr"
    return 0
  fi
  printf '%s\n' "$out" >&2
  return "$rc"
}

echo "==> Importing bootstrap resources for ${NAME_PREFIX} (github_repository=${GH_REPO})"
echo "    Terraform cwd: $(pwd)"
echo ""

import_or_skip aws_s3_bucket.artifacts "${NAME_PREFIX}-artifacts"
import_or_skip 'aws_ecr_repository.service["web"]' "${NAME_PREFIX}-web"
import_or_skip 'aws_ecr_repository.service["orchestrator"]' "${NAME_PREFIX}-orchestrator"
import_or_skip 'aws_iam_role.github_actions[0]' "${NAME_PREFIX}-github-actions"
import_or_skip 'aws_secretsmanager_secret.managed["CLERK_SECRET_KEY"]' "${NAME_PREFIX}/CLERK_SECRET_KEY"

echo ""
echo "==> Done. Run: terraform plan ${common_tf_args[*]}"
echo "    Resolve any remaining creates (e.g. ECR lifecycle, S3 encryption, IAM policy) with a normal apply,"
echo "    or import those addresses too if AWS already has them and apply reports a conflict."
