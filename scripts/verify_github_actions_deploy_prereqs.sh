#!/usr/bin/env bash
# Non-destructive checks before you run bootstrap / root Terraform locally.
# Does not apply infrastructure. See docs/github-actions-aws-deploy.md.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "==> Fleet Health Copilot — GitHub Actions AWS deploy prereqs"
echo ""

if command -v terraform >/dev/null 2>&1; then
  echo "Terraform: $(terraform version -json 2>/dev/null | head -c 200 || terraform version | head -1)"
else
  echo "WARN: terraform not on PATH (install Terraform 1.9.x for parity with deploy-aws)."
fi

if command -v aws >/dev/null 2>&1; then
  if aws sts get-caller-identity >/dev/null 2>&1; then
    echo "AWS CLI: identity OK"
    aws sts get-caller-identity --output text --query Arn
  else
    echo "INFO: aws CLI present but sts get-caller-identity failed (configure credentials for bootstrap apply)."
  fi
else
  echo "INFO: aws CLI not on PATH (optional until you run bootstrap / put-secret-value)."
fi

if command -v git >/dev/null 2>&1; then
  echo "Git remote (for github_repository var):"
  git remote -v 2>/dev/null | head -2 || true
fi

echo ""
echo "Terraform fmt/validate (no remote backend):"
bash scripts/validate_terraform.sh

echo ""
echo "Next: docs/github-actions-aws-deploy.md"
