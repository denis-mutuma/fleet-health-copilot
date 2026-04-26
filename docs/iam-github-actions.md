# GitHub Actions OIDC IAM (least privilege)

## One OIDC provider per AWS account

The GitHub OIDC provider (`token.actions.githubusercontent.com`) is **account-wide**. Variable **`manage_github_oidc_provider`** (see [`variables.tf`](../infra/terraform/variables.tf)) controls whether this workspace **creates** that provider or **reads** it with a data source. **At most one** workspace per account should use **`true`** (typical pattern: temporarily **`true`** in **`env/dev.tfvars`** on a greenfield account for the first apply, then **`false`** everywhere; this repo defaults **`dev`** / **`test`** / **`prod`** to **`false`** so existing accounts reuse the provider). If you previously applied with **`manage_github_oidc_provider = true`** and then set **`false`**, remove the provider from that workspace’s state (it stays in AWS):

```bash
cd infra/terraform
terraform state rm 'aws_iam_openid_connect_provider.github_actions[0]'
```

The Terraform-managed role **`${project}-${environment}-github-actions`** (when **`github_repository`** is set) always receives an **inline policy for ECR push** to the repositories this module creates.

**`github_actions_attach_administrator_access`** defaults to **`false`**. With that default, **no** `AdministratorAccess` is attached; you must grant enough permissions for:

1. **Terraform remote state** — S3 bucket + objects used in `backend.ci.hcl`, and the **DynamoDB lock table** from bootstrap-state.
2. **Terraform apply** for resources in [`infra/terraform`](../infra/terraform) (ECR, S3, IAM, ECS, ELB, EFS, Secrets Manager placeholders, optional S3 Vectors, etc.).

## Minimum policy sketch (replace ARNs and bucket names)

Use this as a starting point; tighten `Resource` ARNs to your account after the first `plan` shows required services.

- **S3 state:** `ListBucket` on the state bucket; `GetObject`, `PutObject`, `DeleteObject` on `arn:aws:s3:::YOUR_STATE_BUCKET/*`.
- **DynamoDB:** `DescribeTable`, `GetItem`, `PutItem`, `DeleteItem`, `UpdateItem` on `arn:aws:dynamodb:REGION:ACCOUNT:table/YOUR_LOCK_TABLE`.
- **ECR:** Already covered by Terraform’s **`github_actions_ecr`** inline policy if you use the **same role** Terraform outputs as **`AWS_ROLE_ARN`**. If you use a **separate** CI role, copy the ECR statements from [`infra/terraform/iam.tf`](../infra/terraform/iam.tf).
- **Terraform-managed AWS resources:** The smallest practical path is often **`PowerUserAccess`** plus **`IAMFullAccess`** (still broad), or **`AdministratorAccess`** only for bootstrap (set **`github_actions_attach_administrator_access = true`** in `env/*.tfvars` temporarily, apply, then set **`false`** and replace with a custom policy).

## Bootstrap convenience

For a class demo or first greenfield apply, you may set **`github_actions_attach_administrator_access = true`** in **`env/dev.tfvars`** (or pass `-var` once), run **`terraform apply`**, then flip to **`false`** and attach a scoped customer-managed policy before production traffic.

See also [aws-deployment-plan.md](aws-deployment-plan.md) and [terraform-bootstrap.md](terraform-bootstrap.md).
