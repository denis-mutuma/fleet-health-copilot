environment = "dev"
aws_region  = "us-east-1"

# GitHub OIDC is one per AWS account. Use false when it already exists (409 EntityAlreadyExists).
# On a brand-new account with no provider yet, set true for the first apply only, then false.
manage_github_oidc_provider = false

tags = {
  Stage = "development"
}
