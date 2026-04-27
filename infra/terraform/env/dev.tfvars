environment = "dev"
aws_region  = "us-east-1"

enable_ecs              = true
enable_orchestrator_efs = true
enable_s3_vectors_rag   = false

# GitHub OIDC provider is one per AWS account. This dev stack creates it (true). test/prod tfvars
# use false so only one stack manages the provider. If you ever get 409 EntityAlreadyExists, the
# provider already exists: set false here and run terraform import on aws_iam_openid_connect_provider.github_actions[0].
manage_github_oidc_provider                = true
github_actions_attach_administrator_access = true

tags = {
  Stage = "development"
}
