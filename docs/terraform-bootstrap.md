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

In the root module, set **`enable_s3_vectors_rag = true`** (and optional **`s3_vectors_*`** overrides) to create an Amazon S3 Vectors bucket and index; use Terraform outputs **`s3_vectors_orchestrator_env_hint`** for suggested orchestrator environment variables after `apply`.

## Automation

Continuous deploy is **[`.github/workflows/deploy-aws.yml`](../.github/workflows/deploy-aws.yml)**: pushes to **`develop`**, **`staging`**, and **`main`** run **`terraform init`** with the **S3 remote backend**, **`terraform apply`**, Docker **build/push** to ECR, then **`terraform apply`** again to pin image tags to the commit SHA. See [aws-deployment-plan.md](aws-deployment-plan.md) and the operator checklist [github-actions-aws-deploy.md](github-actions-aws-deploy.md).

From the repository root, **`bash scripts/validate_terraform.sh`** runs **fmt** / **init `-backend=false`** / **validate** for the root module and `bootstrap-state` (no AWS credentials; used locally and can be mirrored in CI for PRs).

## First-time OIDC role (chicken and egg)

**`deploy-aws`** needs **`AWS_ROLE_ARN`** in each GitHub Environment, but that role is created by the root module when **`github_repository`** is set. Bootstrap order:

1. Apply **bootstrap-state** (this directory).
2. With **administrator credentials** (local AWS profile or CI outside this repo), run **one** root module **`terraform apply`** using remote state and **`-var="github_repository=OWNER/REPO"`** so Terraform creates the **OIDC provider** and **`github_actions`** role. By default **`github_actions_attach_administrator_access`** is **`false`**: attach a customer-managed policy to that role for state + Terraform + ECR, or set **`github_actions_attach_administrator_access = true`** in tfvars for a one-time bootstrap (see [iam-github-actions.md](iam-github-actions.md)).
3. Copy **`terraform output github_actions_role_arn`** into GitHub Environment secrets **`AWS_ROLE_ARN`** for **dev**, **test**, and **prod** (or start with **dev** only).
4. From then on, **`deploy-aws`** can run on every push without long-lived keys.

## Remote init helper

To point the root module at the bootstrap bucket without committing `backend.tf`, run:

```bash
export TF_STATE_BUCKET=YOUR_STATE_BUCKET
export TF_LOCK_TABLE=YOUR_LOCK_TABLE
export TF_STATE_KEY=fleet-health-copilot/dev/terraform.tfstate   # optional
export AWS_REGION=us-east-1
bash scripts/terraform_remote_backend_init.sh
```

## CI apply (GitHub Actions)

After the bootstrap steps above, configure each GitHub Environment (**`dev`**, **`test`**, **`prod`**) with **`TF_STATE_BUCKET`**, **`TF_LOCK_TABLE`**, **`AWS_ROLE_ARN`**, and **`NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`** as described in [aws-deployment-plan.md](aws-deployment-plan.md). State keys in Actions are **`fleet-health-copilot/<environment>/terraform.tfstate`**.
