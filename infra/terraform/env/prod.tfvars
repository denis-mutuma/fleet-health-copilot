environment = "prod"
aws_region  = "us-east-1"

enable_ecs              = false
enable_single_instance  = true
enable_orchestrator_efs = false
enable_postgres         = false
enable_api_gateway      = false
enable_cloudfront       = true
enable_waf              = false
enable_s3_vectors_rag   = false

# Optional: set private subnets for PostgreSQL, internal ALB, and API Gateway VPC Link.
# When omitted, Terraform falls back to public_subnet_ids from deploy workflow secrets.
# private_subnet_ids = ["subnet-0123456789abcdef0", "subnet-0fedcba9876543210"]

manage_github_oidc_provider = false
# Same bootstrap pattern as dev: lets deploy-aws run full terraform apply. Replace with a scoped
# policy before production hardening.
github_actions_attach_administrator_access = true

tags = {
  Stage = "production"
}
