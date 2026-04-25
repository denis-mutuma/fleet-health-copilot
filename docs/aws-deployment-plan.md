# AWS Deployment Plan

This document defines the safe AWS deployment path for Fleet Health Copilot. It keeps the current repository deployable locally while preparing a clear dev/test/prod cloud progression.

## Current State

Implemented:

- Terraform provider configuration under `infra/terraform`.
- Environment variables for `dev`, `test`, and `prod` in `infra/terraform/env`.
- Baseline artifact S3 bucket with encryption, tags, and public-access blocking.
- ECR repositories for deployable container images.
- Optional GitHub Actions OIDC role scaffolding for ECR image pushes.
- Optional ECS Fargate scaffold for the web and orchestrator containers.
- Optional Secrets Manager placeholders for runtime secrets.
- GitHub Actions workflows for PR tests, dev validation, and production Terraform validation.

Not implemented yet:

- Terraform remote state backend.
- Managed database.
- AWS S3 Vectors integration.

## Environment Model

| Environment | Purpose | Trigger |
| --- | --- | --- |
| `dev` | Integration environment for feature validation | Pushes to development branches |
| `test` | Pre-production validation | Manual or release candidate workflow |
| `prod` | Final capstone demo or production-like environment | Version tags or manual approval |

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

Before applying real infrastructure, create a separate Terraform state bootstrap outside this root module:

- S3 bucket for state files.
- DynamoDB table for state locks.
- Bucket versioning and encryption.
- Separate state key per environment, for example:
  - `fleet-health-copilot/dev/terraform.tfstate`
  - `fleet-health-copilot/test/terraform.tfstate`
  - `fleet-health-copilot/prod/terraform.tfstate`

Do not store AWS credentials in the repository.

## GitHub Actions Credentials

Use GitHub OIDC instead of long-lived AWS keys.

Required GitHub configuration:

- AWS IAM OIDC provider for `token.actions.githubusercontent.com`.
- IAM role trusted by this repository when `github_repository` is set.
- Least-privilege ECR image push policy for generated repositories.
- GitHub environment protection for production.

Future workflow steps:

```yaml
- uses: aws-actions/configure-aws-credentials@v4
  with:
    role-to-assume: arn:aws:iam::<account-id>:role/fleet-health-copilot-github
    aws-region: us-east-1
```

## Image Publish Workflow

`.github/workflows/publish-images.yml` is manually triggered and publishes both container images to ECR.

Required inputs:

- `aws_region`: AWS region for ECR.
- `role_to_assume`: value from Terraform output `github_actions_role_arn`.
- `web_repository_url`: `web` entry from Terraform output `ecr_repository_urls`.
- `orchestrator_repository_url`: `orchestrator` entry from Terraform output `ecr_repository_urls`.
- `image_tag`: image tag to publish, for example a git SHA or release tag.
- `next_public_clerk_publishable_key`: Clerk publishable key required during the web build.

Recommended first run:

1. Apply Terraform with `github_repository=OWNER/REPO`.
2. Copy the ECR URLs and GitHub Actions role ARN from Terraform outputs.
3. Trigger `publish-images` manually.
4. Use a commit SHA as `image_tag` for traceability.

## MVP Cloud Resource Sequence

Add cloud resources in this order:

1. **State backend**: S3 and DynamoDB lock table.
2. **Artifact and container storage**: S3 artifacts bucket and ECR repositories. Current Terraform covers this baseline.
3. **Image publishing**: GitHub Actions OIDC role and ECR push workflow.
4. **Compute**: ECS Fargate cluster, web load balancer, private orchestrator discovery, and task definitions. Current Terraform includes an opt-in scaffold.
5. **Secrets**: Clerk keys and app configuration through Secrets Manager placeholders. Current Terraform creates secret containers but leaves values to be populated outside Terraform.
6. **Data**: encrypted EFS for MVP SQLite durability now; managed Postgres or DynamoDB remains the recommended production-grade next step.
7. **Retrieval**: AWS S3 Vectors backend behind `RetrievalBackend`.
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
4. Publish images with `.github/workflows/publish-images.yml`.
5. Enable or update ECS with the image tag and runtime config.

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
- `FLEET_RETRIEVAL_BACKEND`
- `FLEET_S3_VECTORS_BUCKET`
- `FLEET_S3_VECTORS_INDEX`

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
- Whether S3 Vectors should be implemented before or after the first ECS deployment.

## Near-Term Next Step

The next safe implementation step is deployment automation: a manual `deploy-dev` GitHub Actions workflow that uses OIDC, published image tags, Terraform variables, and populated secret ARNs to run a dev environment plan/apply.
