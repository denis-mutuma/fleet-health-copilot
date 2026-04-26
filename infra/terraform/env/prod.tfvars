environment = "prod"
aws_region  = "us-east-1"

manage_github_oidc_provider = false
# Same bootstrap pattern as dev: lets deploy-aws run full terraform apply. Replace with a scoped
# policy per docs/iam-github-actions.md before production hardening.
github_actions_attach_administrator_access = true

tags = {
  Stage = "production"
}
