# Merge when enabling ECS (Fargate + ALB). Use multiple -var-file with env/<env>.tfvars:
#   terraform plan -var-file=env/dev.tfvars -var-file=env/ecs.example.tfvars \
#     -var='github_repository=OWNER/REPO'
#
# GitHub Actions: set repository variable ENABLE_ECS=true and Environment secrets VPC_ID,
# PUBLIC_SUBNET_IDS_JSON, WEB_NEXT_PUBLIC_ORCHESTRATOR_API_BASE_URL (see deploy-aws.yml).

enable_ecs = true
vpc_id     = "vpc-REPLACE_WITH_YOUR_VPC"
public_subnet_ids = [
  "subnet-REPLACE_PUBLIC_A",
  "subnet-REPLACE_PUBLIC_B",
]

# After first apply, set to the public orchestrator URL (ALB DNS or custom domain) if the browser calls the API directly.
web_next_public_orchestrator_api_base_url = "https://REPLACE_ORCHESTRATOR_ALB_DNS"

# Optional CORS: add to env/dev.tfvars (or here) as a full map — overriding orchestrator_environment replaces
# the module default, so include FLEET_DB_PATH and FLEET_RETRIEVAL_BACKEND from variables.tf defaults plus CORS:
# orchestrator_environment = {
#   FLEET_DB_PATH           = "/tmp/fleet-health.db"
#   FLEET_RETRIEVAL_BACKEND = "lexical"
#   FLEET_CORS_ORIGINS      = "https://REPLACE_WEB_ALB_DNS"
# }
