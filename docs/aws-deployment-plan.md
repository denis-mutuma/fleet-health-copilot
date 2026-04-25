# AWS Deployment Plan

This document defines the safe AWS deployment path for Fleet Health Copilot. It keeps the current repository deployable locally while preparing a clear dev/test/prod cloud progression.

## Current State

Implemented:

- Terraform provider configuration under `infra/terraform`.
- Environment variables for `dev`, `test`, and `prod` in `infra/terraform/env`.
- Baseline artifact S3 bucket with encryption, tags, and public-access blocking.
- ECR repositories for deployable container images.
- Optional GitHub Actions OIDC role scaffolding for ECR image pushes.
- GitHub Actions workflows for PR tests, dev validation, and production Terraform validation.

Not implemented yet:

- Terraform remote state backend.
- Deployed compute.
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
4. **Secrets**: Clerk keys and app configuration through a managed secret store.
5. **Compute**: simplest viable container runtime for web and orchestrator.
6. **Data**: managed relational or file-backed store replacing local SQLite.
7. **Retrieval**: AWS S3 Vectors backend behind `RetrievalBackend`.
8. **Observability**: logs, metrics, and alarms for demo reliability.

## Recommended Compute Choice

For the capstone MVP, prefer a simple container deployment path:

- ECR for images.
- ECS Fargate for `web` and `orchestrator`.
- Application Load Balancer routing to the web service.
- Internal service discovery or private endpoint from web to orchestrator.

This keeps the deployment story production-like without introducing Kubernetes complexity.

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

## Open Decisions

- Whether the deployed persistence layer should be managed Postgres, DynamoDB, or a simpler S3-backed MVP store.
- Whether to deploy MCP servers as independent services or keep them as local/demo tool servers.
- Whether S3 Vectors should be implemented before or after the first ECS deployment.

## Near-Term Next Step

The next safe implementation step is a GitHub Actions image build workflow that authenticates with OIDC and pushes the `web` and `orchestrator` images to ECR. Keep it manually triggered until the AWS account, state backend, and environment protection rules are finalized.
