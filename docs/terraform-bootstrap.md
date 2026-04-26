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

In [`infra/terraform`](../infra/terraform), add a `backend "s3"` block to a new `backend.tf` (do not commit real bucket names if the file is public; use a private tfvars or environment-specific snippet):

```hcl
terraform {
  backend "s3" {
    bucket         = "YOUR_ACCOUNT-fleet-health-tf-state"
    key            = "fleet-health-copilot/dev/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "fleet-health-copilot-tf-locks"
    encrypt        = true
  }
}
```

Then `terraform init -migrate-state` from `infra/terraform` and continue with [`docs/aws-deployment-plan.md`](aws-deployment-plan.md).

## Automation

The [`deploy-dev`](../.github/workflows/deploy-dev.yml) workflow runs `terraform fmt`, `init -backend=false`, and `validate` for both the root module and the bootstrap module. Add `plan` / `apply` jobs after you configure AWS credentials and backend settings appropriate for your account.
