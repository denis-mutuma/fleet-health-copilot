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
# Edit backend.tf: set bucket, region, dynamodb_table (keep default key as dev until you use fragments)
```

### One state file per environment (required)

Remote state keys must match GitHub Actions and your tfvars:

| Environment | State key in S3 |
|-------------|-----------------|
| dev | `fleet-health-copilot/dev/terraform.tfstate` |
| test | `fleet-health-copilot/test/terraform.tfstate` |
| prod | `fleet-health-copilot/prod/terraform.tfstate` |

After `backend.tf` exists, **always** select the environment before `plan` / `apply`:

```bash
# From repository root
bash scripts/terraform_init_env.sh dev
terraform -chdir=infra/terraform plan -var-file=env/dev.tfvars -var='github_repository=OWNER/REPO'
```

Committed fragments live under [`infra/terraform/backend-config/`](../infra/terraform/backend-config/). They only set `key`; `bucket` / `region` / `dynamodb_table` / `encrypt` still come from your local `backend.tf`.

**Symptom of a mixed state:** `terraform plan -var-file=env/prod.tfvars` refreshes `fleet-health-copilot-dev-*` resources and plans mass destroy/replace. That means the backend `key` you initialized does **not** match prod, or the **prod** state object incorrectly holds dev stack entries (see recovery below).

### Recover a contaminated `prod` state (tracks dev AWS names)

Do **not** apply that plan. After `bash scripts/terraform_init_env.sh prod`, if `terraform state show 'aws_ecr_repository.service["web"]'` shows `fleet-health-copilot-dev-web`, prod state is wrong for prod tfvars.

1. Confirm dev state is healthy: `bash scripts/terraform_init_env.sh dev` → `terraform state list` → should list your dev stack.
2. Re-init prod: `bash scripts/terraform_init_env.sh prod`.
3. Remove **all** resource addresses from prod state (this does **not** delete AWS; it only edits the prod state file):

   ```bash
   cd infra/terraform
   terraform state list | while read -r addr; do terraform state rm "$addr"; done
   ```

4. Run `terraform plan -var-file=env/prod.tfvars -var='github_repository=OWNER/REPO'`. You should see **creates** for prod-named resources, **no** destroys of existing dev resources.

If step 4’s **`apply`** instead fails with **`EntityAlreadyExists`**, **`BucketAlreadyExists`**, or **`RepositoryAlreadyExistsException`**, the **prod** AWS objects are already there but this **state file is still empty** (for example resources were created earlier with **local** state or a **different key**). Do **not** delete the AWS resources; run **`bash scripts/import_terraform_existing_bootstrap.sh prod`** after **`terraform init`** for prod, then **`plan`** / **`apply`** again. Details: [github-actions-aws-deploy.md](github-actions-aws-deploy.md) (troubleshooting).

5. **OIDC:** `manage_github_oidc_provider` should stay `false` in `env/prod.tfvars` if another environment’s state already created the account GitHub OIDC provider (typical). First greenfield account: create the provider from **one** stack (e.g. dev with `manage_github_oidc_provider = true`) before relying on prod CI.

Then continue with [`docs/aws-deployment-plan.md`](aws-deployment-plan.md).

In the root module, set **`enable_s3_vectors_rag = true`** (and optional **`s3_vectors_*`** overrides) to create an Amazon S3 Vectors bucket and index; use Terraform outputs **`s3_vectors_orchestrator_env_hint`** for suggested orchestrator environment variables after `apply`.

## Automation

Continuous deploy is **[`.github/workflows/deploy-aws.yml`](../.github/workflows/deploy-aws.yml)**: pushes to **`develop`**, **`staging`**, and **`main`** run **`terraform init`** with the **S3 remote backend**, **`terraform apply`**, Docker **build/push** to ECR, then **`terraform apply`** again to pin image tags to the commit SHA. See [aws-deployment-plan.md](aws-deployment-plan.md) and the operator checklist [github-actions-aws-deploy.md](github-actions-aws-deploy.md).

From the repository root, **`bash scripts/validate_terraform.sh`** runs **fmt** / **init `-backend=false`** / **validate** for the root module and `bootstrap-state` (no AWS credentials; used locally and can be mirrored in CI for PRs).

## First-time OIDC role (chicken and egg)

**`deploy-aws`** needs **`AWS_ROLE_ARN`** in each GitHub Environment, but that role is created by the root module when **`github_repository`** is set. Bootstrap order:

1. Apply **bootstrap-state** (this directory).
2. With **administrator credentials** (local AWS profile or CI outside this repo), run **one** root module **`terraform apply`** using remote state and **`-var="github_repository=OWNER/REPO"`** so Terraform creates the **`github_actions`** role. The **OIDC provider** is only created when **`manage_github_oidc_provider = true`** in the tfvars you use; **`env/*.tfvars`** default to **`false`** so an account that already has `token.actions.githubusercontent.com` does not hit **409 EntityAlreadyExists**. On a **greenfield** account with no GitHub OIDC provider yet, set **`manage_github_oidc_provider = true`** in **`env/dev.tfvars`** for that first apply, then set it back to **`false`**. By default **`github_actions_attach_administrator_access`** is **`false`**: attach a customer-managed policy to that role for state + Terraform + ECR, or set **`github_actions_attach_administrator_access = true`** in tfvars for a one-time bootstrap (see [iam-github-actions.md](iam-github-actions.md)).
3. Copy **`terraform output github_actions_role_arn`** into GitHub Environment secrets **`AWS_ROLE_ARN`** for **dev**, **test**, and **prod** (or start with **dev** only).
4. From then on, **`deploy-aws`** can run on every push without long-lived keys.

## Remote init helper

To point the root module at the bootstrap bucket without committing `backend.tf`, run:

```bash
export TF_STATE_BUCKET=YOUR_STATE_BUCKET
export TF_LOCK_TABLE=YOUR_LOCK_TABLE
export TF_ENV=dev   # dev | test | prod — default key fleet-health-copilot/${TF_ENV}/terraform.tfstate
export AWS_REGION=us-east-1
bash scripts/terraform_remote_backend_init.sh
# Or override explicitly: export TF_STATE_KEY=fleet-health-copilot/prod/terraform.tfstate
```

## CI apply (GitHub Actions)

After the bootstrap steps above, configure each GitHub Environment (**`dev`**, **`test`**, **`prod`**) with **`TF_STATE_BUCKET`**, **`TF_LOCK_TABLE`**, **`AWS_ROLE_ARN`**, and **`NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`** as described in [aws-deployment-plan.md](aws-deployment-plan.md). State keys in Actions are **`fleet-health-copilot/<environment>/terraform.tfstate`**.
