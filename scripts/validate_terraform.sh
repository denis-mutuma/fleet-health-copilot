#!/usr/bin/env bash
# Run terraform fmt -check, init (no remote backend), and validate for root and bootstrap modules.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

for dir in "$ROOT/infra/terraform" "$ROOT/infra/terraform/bootstrap-state"; do
  echo "==> $dir"
  (cd "$dir" && terraform fmt -check && terraform init -backend=false -input=false && terraform validate)
done

echo "Terraform fmt/init/validate OK for root and bootstrap-state."
