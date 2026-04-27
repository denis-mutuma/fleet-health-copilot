resource "random_password" "postgres" {
  count = var.enable_postgres ? 1 : 0

  length  = 24
  special = false
}

resource "aws_security_group" "postgres" {
  count = var.enable_postgres ? 1 : 0

  name        = "${local.name_prefix}-postgres"
  description = "Allow orchestrator tasks to reach PostgreSQL."
  vpc_id      = var.vpc_id

  ingress {
    description     = "PostgreSQL from orchestrator tasks"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.orchestrator[0].id]
  }

  egress {
    description = "Outbound database traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = local.common_tags
}

resource "aws_db_subnet_group" "orchestrator" {
  count = var.enable_postgres ? 1 : 0

  name       = "${local.name_prefix}-postgres"
  subnet_ids = local.runtime_private_subnet_ids

  tags = local.common_tags
}

resource "aws_db_instance" "orchestrator" {
  count = var.enable_postgres ? 1 : 0

  identifier                   = "${local.name_prefix}-postgres"
  engine                       = "postgres"
  engine_version               = "16.3"
  instance_class               = var.postgres_instance_class
  allocated_storage            = var.postgres_allocated_storage
  max_allocated_storage        = var.postgres_max_allocated_storage
  db_name                      = var.postgres_database_name
  username                     = var.postgres_username
  password                     = random_password.postgres[0].result
  db_subnet_group_name         = aws_db_subnet_group.orchestrator[0].name
  vpc_security_group_ids       = [aws_security_group.postgres[0].id]
  backup_retention_period      = 7
  storage_encrypted            = true
  deletion_protection          = var.environment == "prod"
  skip_final_snapshot          = var.environment != "prod"
  final_snapshot_identifier    = var.environment == "prod" ? "${local.name_prefix}-postgres-final" : null
  publicly_accessible          = false
  auto_minor_version_upgrade   = true
  apply_immediately            = true
  performance_insights_enabled = true
  copy_tags_to_snapshot        = true
  monitoring_interval          = 0

  tags = local.common_tags
}