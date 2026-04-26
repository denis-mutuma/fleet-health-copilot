# Partial backend config: use with terraform init -reconfigure -backend-config=backend-config/dev.hcl
# Requires bucket/region/dynamodb_table in backend.tf (or additional -backend-config flags).
key = "fleet-health-copilot/dev/terraform.tfstate"
