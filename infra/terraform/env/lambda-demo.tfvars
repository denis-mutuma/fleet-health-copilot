environment = "dev"
aws_region  = "us-east-1"

enable_lambda_demo      = true
enable_ecs              = false
enable_single_instance  = false
enable_orchestrator_efs = false
enable_postgres         = false
enable_api_gateway      = false
enable_cloudfront       = false
enable_waf              = false
enable_s3_vectors_rag   = false
enable_managed_secrets  = false

github_actions_attach_administrator_access = false
manage_github_oidc_provider                = false

tags = {
  Stage = "lambda-demo"
}
