# Terraform remote state bootstrap

The root module under [`infra/terraform`](../infra/terraform) defaults to local state for laptop use. Before shared or CI applies, provision a dedicated state bucket and lock table once per AWS account.

## Bootstrap module

[`infra/terraform/bootstrap-state`](../infra/terraform/bootstrap-state) creates:

- Versioned, encrypted, private S3 bucket for `*.tfstate`
- DynamoDB table for state locking

Pick a **globally unique** `state_bucket_name` (S3 bucket names are global).

Example (replace names and region):

```bash
cd infra/terraform/bootstrap-state
terraform init
terraform apply \
  -var='aws_region=us-east-1' \
  -var='state_bucket_name=YOUR_ACCOUNT-fleet-health-tf-state' \
  -var='lock_table_name=fleet-health-copilot-tf-locks'
```

## Wire the root module

[`infra/terraform/backend.tf.example`](../infra/terraform/backend.tf.example) is the canonical template. **`backend.tf` is gitignored** so bucket names stay local:

```bash
cd infra/terraform
cp backend.tf.example backend.tf
# Edit backend.tf: set bucket, region, dynamodb_table, key per environment
terraform init -migrate-state
```

Then continue with [`docs/aws-deployment-plan.md`](aws-deployment-plan.md).

## Automation

The [`deploy-dev`](../.github/workflows/deploy-dev.yml) workflow always runs `terraform fmt` / `init -backend=false` / `validate`. When repository secret **`AWS_ROLE_ARN`** is set (GitHub OIDC role for this repo), the same dispatch also runs **`terraform plan`** against AWS for `env/dev.tfvars` (still **local state in CI** unless you add a backend config step). Set the secret empty or unset to skip the AWS plan job.

From the repository root, **`bash scripts/validate_terraform.sh`** runs the same fmt/init/validate loop for both the root module and `bootstrap-state` (requires Terraform on `PATH`).
