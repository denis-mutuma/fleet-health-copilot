environment = "prod"
aws_region  = "us-east-1"

enable_ecs              = true
enable_orchestrator_efs = true
enable_s3_vectors_rag   = false

manage_github_oidc_provider = false
# Same bootstrap pattern as dev: lets deploy-aws run full terraform apply. Replace with a scoped
# policy before production hardening.
github_actions_attach_administrator_access = true

tags = {
  Stage = "production"
}
