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
  managed_orchestrator_secret_arns = var.enable_postgres ? {
    FLEET_DATABASE_URL = aws_secretsmanager_secret.postgres_database_url[0].arn
  } : {}
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

resource "aws_secretsmanager_secret" "postgres_database_url" {
  count = var.enable_postgres ? 1 : 0

  name                    = "${local.name_prefix}/FLEET_DATABASE_URL"
  description             = "PostgreSQL connection URL for ${local.name_prefix} orchestrator runtime."
  recovery_window_in_days = 7

  tags = merge(local.common_tags, {
    RuntimeSecret = "FLEET_DATABASE_URL"
  })
}

resource "aws_secretsmanager_secret_version" "postgres_database_url" {
  count = var.enable_postgres ? 1 : 0

  secret_id = aws_secretsmanager_secret.postgres_database_url[0].id
  secret_string = format(
    "postgresql://%s:%s@%s:%s/%s",
    var.postgres_username,
    random_password.postgres[0].result,
    aws_db_instance.orchestrator[0].address,
    aws_db_instance.orchestrator[0].port,
    var.postgres_database_name,
  )
}
