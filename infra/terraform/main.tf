locals {
  name_prefix = "${var.project_name}-${var.environment}"
}

# Placeholder baseline resource for environment bootstrapping.
resource "aws_s3_bucket" "artifacts" {
  bucket = "${local.name_prefix}-artifacts"
}
