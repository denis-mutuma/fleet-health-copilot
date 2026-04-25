locals {
  managed_secret_names = var.enable_managed_secrets ? var.managed_secret_names : []
  managed_secret_arns = {
    for name, secret in aws_secretsmanager_secret.managed : name => secret.arn
  }
  managed_web_secret_names = toset(["CLERK_SECRET_KEY"])
  managed_web_secret_arns = {
    for name, arn in local.managed_secret_arns : name => arn
    if contains(local.managed_web_secret_names, name)
  }
}

resource "aws_secretsmanager_secret" "managed" {
  for_each = local.managed_secret_names

  name                    = "${local.name_prefix}/${each.value}"
  description             = "Runtime secret ${each.value} for ${local.name_prefix}. Populate value outside Terraform."
  recovery_window_in_days = 7

  tags = merge(local.common_tags, {
    RuntimeSecret = each.value
  })
}
