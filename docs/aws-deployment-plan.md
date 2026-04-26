# AWS Deployment Plan

This document defines the safe AWS deployment path for Fleet Health Copilot. It keeps the current repository deployable locally while preparing a clear dev/test/prod cloud progression.

**Step-by-step checklist (operators):** [github-actions-aws-deploy.md](github-actions-aws-deploy.md)

## Current State

Implemented:

- Terraform under `infra/terraform` with **dev / test / prod** tfvars in `infra/terraform/env`.
- **S3 + DynamoDB** remote state via the **bootstrap-state** module (see [terraform-bootstrap.md](terraform-bootstrap.md)).
- **GitHub Actions OIDC** role when `github_repository` is set at apply time. **`github_actions_attach_administrator_access`** defaults to **`false`** (no **AdministratorAccess**); attach least-privilege policies to the role or opt in to admin for bootstrap only (see [iam-github-actions.md](iam-github-actions.md)).
- **[`.github/workflows/deploy-aws.yml`](../.github/workflows/deploy-aws.yml)**: on every push to **`develop`**, **`staging`**, or **`main`**, runs **`terraform init`** with the **S3 backend**, **`terraform apply`**, **Docker build/push** to ECR, then **`terraform apply`** again to pin **`container_image_tags`** to the commit SHA. Uses **GitHub Environments** `dev`, `test`, and `prod` for secrets.
- PR quality gates in **`test.yml`** (no AWS credentials required).
- Baseline S3 artifacts bucket, ECR, optional ECS, optional S3 Vectors RAG, Secrets Manager placeholders.

Not implemented yet:

- **Managed Postgres** wired into the app (orchestrator remains SQLite / EFS by default).
- **Embedding inference** and automatic corpus upsert in AWS (you still run [`index_s3_vectors.py`](../services/orchestrator/scripts/index_s3_vectors.py) with matching `FLEET_EMBEDDING_PROVIDER`).

See [backlog-postgres-and-indexing.md](backlog-postgres-and-indexing.md) for a concise design sketch.

## GitHub Actions: `deploy-aws` (mandatory S3 state + OIDC)

See **[`.github/workflows/deploy-aws.yml`](../.github/workflows/deploy-aws.yml)** for the full job graph and comments.

Summary:

1. One-time: apply **`infra/terraform/bootstrap-state`** and record the **state bucket** and **DynamoDB lock table** name.
2. One-time: from a privileged principal, run **root module** `terraform apply` with **`-var="github_repository=OWNER/REPO"`** so Terraform creates the **OIDC provider** (only in the workspace where **`manage_github_oidc_provider`** is true; see [iam-github-actions.md](iam-github-actions.md)) and **`github_actions` IAM role** (ECR push is always inline on that role; broader **Terraform** permissions require your own policy unless you set **`github_actions_attach_administrator_access = true`** in tfvars). Copy output **`github_actions_role_arn`** into each GitHub Environment secret **`AWS_ROLE_ARN`** (or use one shared Environment if you accept the same role for all three).
3. In GitHub **Settings → Environments**, create **`dev`**, **`test`**, and **`prod`**. On each environment, add secrets **`AWS_ROLE_ARN`**, **`TF_STATE_BUCKET`**, **`TF_LOCK_TABLE`**, and **`NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`**. Add optional secrets **`VPC_ID`**, **`PUBLIC_SUBNET_IDS_JSON`**, **`WEB_NEXT_PUBLIC_ORCHESTRATOR_API_BASE_URL`** when you enable ECS (see workflow file).
4. Set repository variable **`ENABLE_ECS`** to **`true`** only after the first successful deploy path (ECR exists). When true, **VPC** and **subnet** secrets must satisfy Terraform validation (`vpc_id` non-empty, at least two subnet IDs).
5. **Branch mapping**: `develop` → environment **dev** + `env/dev.tfvars`; `staging` → **test** + `env/test.tfvars`; `main` → **prod** + `env/prod.tfvars`. **Manual re-run**: **Actions → deploy-aws → Run workflow** and pick the target environment.

State keys in CI: **`fleet-health-copilot/<dev|test|prod>/terraform.tfstate`**. Local init with the same backend: set **`TF_ENV`** (or **`TF_STATE_KEY`**) and run **`bash scripts/terraform_remote_backend_init.sh`** (see [terraform-bootstrap.md](terraform-bootstrap.md)).

When **`enable_ecs`** and **`enable_s3_vectors_rag`** are both true, the orchestrator ECS task receives **S3 Vectors** env vars from Terraform (see `ecs.tf`).

## Environment Model

| GitHub Environment | Terraform `environment` / tfvars | Automatic deploy branch |
| --- | --- | --- |
| `dev` | `dev` / `env/dev.tfvars` | `develop` |
| `test` | `test` / `env/test.tfvars` | `staging` |
| `prod` | `prod` / `env/prod.tfvars` | `main` |

Terraform variable files:

- `infra/terraform/env/dev.tfvars`
- `infra/terraform/env/test.tfvars`
- `infra/terraform/env/prod.tfvars`

## Terraform Commands

Format and validate:

```bash
terraform -chdir=infra/terraform fmt -check
terraform -chdir=infra/terraform init -backend=false
terraform -chdir=infra/terraform validate
```

Plan one environment:

```bash
terraform -chdir=infra/terraform plan -var-file=env/dev.tfvars
```

Enable GitHub OIDC role scaffolding by adding the repository slug at plan/apply time:

```bash
terraform -chdir=infra/terraform plan \
  -var-file=env/dev.tfvars \
  -var='github_repository=OWNER/REPO'
```

Apply only after credentials and state backend are configured:

```bash
terraform -chdir=infra/terraform apply -var-file=env/dev.tfvars
```

Plan ECS compute after ECR images are published and a VPC is selected:

```bash
terraform -chdir=infra/terraform plan \
  -var-file=env/dev.tfvars \
  -var='enable_ecs=true' \
  -var='vpc_id=vpc-xxxxxxxx' \
  -var='public_subnet_ids=["subnet-aaaaaaaa","subnet-bbbbbbbb"]' \
  -var='container_image_tags={web="GIT_SHA",orchestrator="GIT_SHA"}' \
  -var='web_next_public_clerk_publishable_key=pk_test_xxx' \
  -var='web_next_public_orchestrator_api_base_url=http://ALB_DNS_NAME'
```

By default, ECS also creates an encrypted EFS file system for the orchestrator SQLite database. Disable it with `enable_orchestrator_efs=false` only for throwaway environments.

Terraform creates Secrets Manager secret placeholders for names in `managed_secret_names` without storing secret values in state. Populate values after apply, for example:

```bash
aws secretsmanager put-secret-value \
  --secret-id fleet-health-copilot-dev/CLERK_SECRET_KEY \
  --secret-string "$CLERK_SECRET_KEY"
```

## Remote State Plan

Use the bootstrap module and wiring steps in **[terraform-bootstrap.md](terraform-bootstrap.md)** (`infra/terraform/bootstrap-state`) to create:

- S3 bucket for state files (versioned, encrypted, private)
- DynamoDB table for state locks
- Separate state key per environment, for example:
  - `fleet-health-copilot/dev/terraform.tfstate`
  - `fleet-health-copilot/test/terraform.tfstate`
  - `fleet-health-copilot/prod/terraform.tfstate`

Do not store long-lived AWS access keys in the repository. PR checks use **`test.yml`** (lint, tests, Terraform **validate** with **`-backend=false`** only). Continuous deploy uses OIDC via **`deploy-aws.yml`** and the S3 remote backend described above.

## GitHub Actions credentials

**`deploy-aws`** uses **`aws-actions/configure-aws-credentials`** with **`role-to-assume: ${{ secrets.AWS_ROLE_ARN }}`** on each GitHub Environment. That role is normally the Terraform output **`github_actions_role_arn`** created when **`github_repository`** is set at apply time. The same workflow runs **Terraform** and **Docker push**, so the role must allow both. Terraform always grants **ECR push** inline; **`terraform apply`** needs additional IAM unless you attach **AdministratorAccess** via **`github_actions_attach_administrator_access = true`** (bootstrap only) or a scoped customer-managed policy—see [iam-github-actions.md](iam-github-actions.md).

Use **GitHub Environment protection rules** (required reviewers, wait timers) on **`prod`** for safer production deploys.

## MVP Cloud Resource Sequence

Add cloud resources in this order:

1. **State backend**: S3 and DynamoDB lock table.
2. **Artifact and container storage**: S3 artifacts bucket and ECR repositories. Current Terraform covers this baseline.
3. **Image publishing**: handled inside **`deploy-aws.yml`** (ECR login + build/push after Terraform creates repos).
4. **Compute**: ECS Fargate cluster, web load balancer, private orchestrator discovery, and task definitions. Current Terraform includes an opt-in scaffold.
5. **Secrets**: Clerk keys and app configuration through Secrets Manager placeholders. Current Terraform creates secret containers but leaves values to be populated outside Terraform.
6. **Data**: encrypted EFS for MVP SQLite durability now; managed Postgres or DynamoDB remains the recommended production-grade next step.
7. **Retrieval**: Configure orchestrator env for S3 Vectors (`FLEET_RETRIEVAL_BACKEND`, bucket/index or `FLEET_S3_VECTORS_INDEX_ARN`, IAM, embedding model); index population remains outside this repo until you add an ingestion job.
8. **Observability**: logs, metrics, and alarms for demo reliability.

## Recommended Compute Choice

For the capstone MVP, prefer a simple container deployment path:

- ECR for images.
- ECS Fargate for `web` and `orchestrator`.
- Application Load Balancer routing to the web service.
- AWS Cloud Map private DNS from web to orchestrator.

This keeps the deployment story production-like without introducing Kubernetes complexity.

Current ECS scaffold:

- Disabled by default with `enable_ecs = false`.
- Creates one ECS cluster per environment.
- Publishes the web service through an HTTP Application Load Balancer.
- Registers the orchestrator as `orchestrator.<project>-<environment>.local`.
- Creates CloudWatch log groups with 14-day retention.
- Uses ECR images from the generated repositories and deploys tags from `container_image_tags`.
- Accepts secret ARNs through `web_secret_arns` and `orchestrator_secret_arns`.
- Injects managed `CLERK_SECRET_KEY` into the web task by default when `enable_managed_secrets=true`.
- Mounts encrypted EFS storage into the orchestrator task at `/data` when `enable_orchestrator_efs=true`.

## Runtime Secrets

Terraform creates Secrets Manager placeholders from `managed_secret_names`; it does not create secret versions or store secret values. This keeps sensitive values out of the repository and Terraform state.

Default managed secret:

- `CLERK_SECRET_KEY`: injected into the web ECS task as a secret environment variable.

First-run sequence:

1. Apply Terraform with `enable_managed_secrets=true`.
2. Read `managed_secret_arns` from Terraform outputs.
3. Populate the secret values with the AWS CLI or console.
4. Images are built and pushed by **`deploy-aws`**; the second **`terraform apply`** in that workflow pins **`container_image_tags`** to the commit SHA.
5. Set repository variable **`ENABLE_ECS=true`** and supply **VPC / subnet** secrets when you are ready for ECS; then pushes will roll the Fargate services.

If a secret already exists outside this module, pass its ARN through `web_secret_arns` or `orchestrator_secret_arns`. Explicit ARNs override generated managed secret ARNs for the same environment variable name.

## MVP Data Persistence

The orchestrator already stores events, incidents, and RAG documents in SQLite. For a low-risk capstone deployment, Terraform mounts an encrypted EFS file system into the ECS orchestrator task and sets:

```bash
FLEET_DB_PATH=/data/fleet-health.db
```

This avoids code churn while making incident history survive task restarts and redeploys. Treat this as an MVP persistence mode:

- Keep `ecs_desired_count = 1` while using SQLite on EFS.
- Use the EFS outputs to confirm the mounted file system for each environment.
- Move to managed Postgres or DynamoDB before scaling orchestrator writers horizontally.

## Required Runtime Configuration

Web:

- `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`
- `CLERK_SECRET_KEY`
- `ORCHESTRATOR_API_BASE_URL`
- `NEXT_PUBLIC_ORCHESTRATOR_API_BASE_URL`

Orchestrator:

- `FLEET_DB_PATH` for local SQLite mode.
- `FLEET_RETRIEVAL_BACKEND` (`lexical` default, or `s3vectors`)
- For `s3vectors`: `FLEET_S3_VECTORS_BUCKET` and `FLEET_S3_VECTORS_INDEX`, or `FLEET_S3_VECTORS_INDEX_ARN`, plus optional `FLEET_S3_VECTORS_EMBEDDING_DIM` and `FLEET_S3_VECTORS_QUERY_VECTOR_JSON` (see README)

Terraform outputs when ECS is enabled:

- `managed_secret_arns`
- `ecs_cluster_name`
- `web_load_balancer_dns_name`
- `orchestrator_service_discovery_name`
- `orchestrator_efs_file_system_id`
- `orchestrator_database_path`

## Open Decisions

- Whether the deployed persistence layer should be managed Postgres, DynamoDB, or a simpler S3-backed MVP store.
- Whether to deploy MCP servers as independent services or keep them as local/demo tool servers.
- Whether to wire S3 Vectors env and IAM before or after the first ECS deployment (query path exists in code; indexing and embeddings are separate decisions).

## Near-term next steps

- Prefer **`github_actions_attach_administrator_access = false`** and a scoped **`github_actions`** policy from day one in real accounts; use admin attach only for classroom bootstrap, then replace with least privilege ([iam-github-actions.md](iam-github-actions.md)).
- Populate **Secrets Manager** values for **`CLERK_SECRET_KEY`** and any custom secret ARNs, then re-deploy.
- Point **`WEB_NEXT_PUBLIC_ORCHESTRATOR_API_BASE_URL`** at your public API URL (ALB or custom domain) and re-run **`deploy-aws`** so the web task picks up the correct browser-facing API base URL.
