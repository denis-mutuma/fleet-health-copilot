locals {
  orchestrator_data_mount_path = "/data"
  postgres_enabled             = var.enable_ecs && var.enable_postgres
  runtime_private_subnet_ids   = length(var.private_subnet_ids) > 0 ? var.private_subnet_ids : var.public_subnet_ids
  orchestrator_efs_enabled     = var.enable_ecs && var.enable_orchestrator_efs && !local.postgres_enabled
  orchestrator_db_path         = local.orchestrator_efs_enabled ? "${local.orchestrator_data_mount_path}/fleet-health.db" : lookup(var.orchestrator_environment, "FLEET_DB_PATH", "/tmp/fleet-health.db")
  web_orchestrator_api_base_url = (
    var.enable_api_gateway
    ? aws_apigatewayv2_stage.orchestrator_default[0].invoke_url
    : "http://orchestrator.${local.name_prefix}.local:8000"
  )
  public_orchestrator_api_base_url = (
    var.web_next_public_orchestrator_api_base_url != ""
    ? var.web_next_public_orchestrator_api_base_url
    : (var.enable_api_gateway ? aws_apigatewayv2_stage.orchestrator_default[0].invoke_url : "")
  )

  # When ECS and S3 Vectors RAG are both enabled, inject vector settings into the orchestrator task.
  orchestrator_s3_vectors_env = (var.enable_ecs && var.enable_s3_vectors_rag) ? {
    FLEET_RETRIEVAL_BACKEND        = "s3vectors"
    FLEET_S3_VECTORS_BUCKET        = aws_s3vectors_vector_bucket.rag[0].vector_bucket_name
    FLEET_S3_VECTORS_INDEX         = aws_s3vectors_index.rag[0].index_name
    FLEET_S3_VECTORS_INDEX_ARN     = aws_s3vectors_index.rag[0].index_arn
    FLEET_S3_VECTORS_EMBEDDING_DIM = tostring(var.s3_vectors_embedding_dimension)
  } : {}

  # Supports importing ECR repos one at a time (both keys are not in state yet).
  ecr_repository_url_by_key       = { for k, repo in aws_ecr_repository.service : k => repo.repository_url }
  ecr_import_placeholder_url      = "${data.aws_caller_identity.current.account_id}.dkr.ecr.${var.aws_region}.amazonaws.com/__terraform_import_pending__"
  ecr_web_repository_url          = lookup(local.ecr_repository_url_by_key, "web", local.ecr_import_placeholder_url)
  ecr_orchestrator_repository_url = lookup(local.ecr_repository_url_by_key, "orchestrator", local.ecr_import_placeholder_url)

  ecs_services = {
    web = {
      cpu       = 512
      memory    = 1024
      port      = 3000
      image     = "${local.ecr_web_repository_url}:${lookup(var.container_image_tags, "web", "latest")}"
      log_group = "/ecs/${local.name_prefix}/web"
      environment = merge(
        {
          NODE_ENV                              = "production"
          HOSTNAME                              = "0.0.0.0"
          PORT                                  = "3000"
          ORCHESTRATOR_API_BASE_URL             = local.web_orchestrator_api_base_url
          NEXT_PUBLIC_ORCHESTRATOR_API_BASE_URL = local.public_orchestrator_api_base_url
          NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY     = var.web_next_public_clerk_publishable_key
        }
      )
      secrets = merge(local.managed_web_secret_arns, var.web_secret_arns)
    }
    orchestrator = {
      cpu       = 512
      memory    = 1024
      port      = 8000
      image     = "${local.ecr_orchestrator_repository_url}:${lookup(var.container_image_tags, "orchestrator", "latest")}"
      log_group = "/ecs/${local.name_prefix}/orchestrator"
      environment = merge(
        var.orchestrator_environment,
        local.postgres_enabled ? {} : { FLEET_DB_PATH = local.orchestrator_db_path },
        local.orchestrator_s3_vectors_env
      )
      secrets = merge(local.managed_orchestrator_secret_arns, var.orchestrator_secret_arns)
    }
  }

  ecs_service_map = var.enable_ecs ? local.ecs_services : {}
  ecs_secret_arns = distinct(concat(values(local.managed_web_secret_arns), values(local.managed_orchestrator_secret_arns), values(var.web_secret_arns), values(var.orchestrator_secret_arns)))
  # Must not depend on secret ARNs (unknown until apply) or count on ecs_task_secret_access breaks at plan.
  ecs_secret_enabled = var.enable_ecs && (
    (var.enable_managed_secrets && length(setintersection(var.managed_secret_names, local.managed_web_secret_names)) > 0) ||
    (var.enable_managed_secrets && length(setintersection(var.managed_secret_names, local.managed_orchestrator_secret_names)) > 0) ||
    var.enable_postgres ||
    length(var.web_secret_arns) > 0 ||
    length(var.orchestrator_secret_arns) > 0
  )
}

data "aws_vpc" "selected" {
  count = var.enable_ecs ? 1 : 0

  id = var.vpc_id
}

data "aws_iam_policy_document" "ecs_tasks_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    effect  = "Allow"

    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ecs_task_execution" {
  count = var.enable_ecs ? 1 : 0

  name               = "${local.name_prefix}-ecs-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume_role.json

  tags = local.common_tags
}

resource "aws_iam_role_policy_attachment" "ecs_task_execution" {
  count = var.enable_ecs ? 1 : 0

  role       = aws_iam_role.ecs_task_execution[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

data "aws_iam_policy_document" "ecs_task_secret_access" {
  count = local.ecs_secret_enabled ? 1 : 0

  statement {
    actions = [
      "secretsmanager:GetSecretValue",
      "ssm:GetParameters"
    ]
    effect    = "Allow"
    resources = local.ecs_secret_arns
  }
}

resource "aws_iam_role_policy" "ecs_task_secret_access" {
  count = local.ecs_secret_enabled ? 1 : 0

  name   = "${local.name_prefix}-ecs-secret-access"
  role   = aws_iam_role.ecs_task_execution[0].id
  policy = data.aws_iam_policy_document.ecs_task_secret_access[0].json
}

resource "aws_iam_role" "ecs_task" {
  count = var.enable_ecs ? 1 : 0

  name               = "${local.name_prefix}-ecs-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume_role.json

  tags = local.common_tags
}

data "aws_iam_policy_document" "ecs_task_efs_access" {
  count = local.orchestrator_efs_enabled ? 1 : 0

  statement {
    actions = [
      "elasticfilesystem:ClientMount",
      "elasticfilesystem:ClientWrite"
    ]
    effect    = "Allow"
    resources = [aws_efs_file_system.orchestrator[0].arn]

    condition {
      test     = "StringEquals"
      variable = "elasticfilesystem:AccessPointArn"
      values   = [aws_efs_access_point.orchestrator[0].arn]
    }
  }
}

resource "aws_iam_role_policy" "ecs_task_efs_access" {
  count = local.orchestrator_efs_enabled ? 1 : 0

  name   = "${local.name_prefix}-ecs-efs-access"
  role   = aws_iam_role.ecs_task[0].id
  policy = data.aws_iam_policy_document.ecs_task_efs_access[0].json
}

resource "aws_cloudwatch_log_group" "service" {
  for_each = local.ecs_service_map

  name              = each.value.log_group
  retention_in_days = 14

  tags = local.common_tags
}

resource "aws_ecs_cluster" "main" {
  count = var.enable_ecs ? 1 : 0

  name = local.name_prefix

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = local.common_tags
}

resource "aws_service_discovery_private_dns_namespace" "main" {
  count = var.enable_ecs ? 1 : 0

  name        = "${local.name_prefix}.local"
  description = "Private service discovery for Fleet Health Copilot."
  vpc         = var.vpc_id

  tags = local.common_tags
}

resource "aws_service_discovery_service" "orchestrator" {
  count = var.enable_ecs ? 1 : 0

  name = "orchestrator"

  dns_config {
    namespace_id = aws_service_discovery_private_dns_namespace.main[0].id

    dns_records {
      ttl  = 10
      type = "A"
    }

    routing_policy = "MULTIVALUE"
  }

  tags = local.common_tags
}

resource "aws_security_group" "alb" {
  count = var.enable_ecs ? 1 : 0

  name        = "${local.name_prefix}-alb"
  description = "Allow public HTTP access to the web load balancer."
  vpc_id      = var.vpc_id

  ingress {
    description = "HTTP from the internet"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "Outbound to ECS tasks"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = local.common_tags
}

resource "aws_security_group" "web" {
  count = var.enable_ecs ? 1 : 0

  name        = "${local.name_prefix}-web"
  description = "Allow ALB traffic to the web service."
  vpc_id      = var.vpc_id

  ingress {
    description     = "Web traffic from ALB"
    from_port       = local.ecs_services.web.port
    to_port         = local.ecs_services.web.port
    protocol        = "tcp"
    security_groups = [aws_security_group.alb[0].id]
  }

  egress {
    description = "Outbound application traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = local.common_tags
}

resource "aws_security_group" "orchestrator" {
  count = var.enable_ecs ? 1 : 0

  name        = "${local.name_prefix}-orchestrator"
  description = "Allow private web traffic to the orchestrator service."
  vpc_id      = var.vpc_id

  ingress {
    description = "Orchestrator traffic from web tasks and internal ingress"
    from_port   = local.ecs_services.orchestrator.port
    to_port     = local.ecs_services.orchestrator.port
    protocol    = "tcp"
    security_groups = compact(concat(
      [aws_security_group.web[0].id],
      var.enable_api_gateway ? [aws_security_group.orchestrator_alb[0].id] : []
    ))
  }

  egress {
    description = "Outbound application traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = local.common_tags
}

resource "aws_security_group" "efs" {
  count = local.orchestrator_efs_enabled ? 1 : 0

  name        = "${local.name_prefix}-efs"
  description = "Allow orchestrator tasks to mount durable EFS storage."
  vpc_id      = var.vpc_id

  ingress {
    description     = "NFS from orchestrator tasks"
    from_port       = 2049
    to_port         = 2049
    protocol        = "tcp"
    security_groups = [aws_security_group.orchestrator[0].id]
  }

  egress {
    description = "Outbound EFS traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = local.common_tags
}

resource "aws_efs_file_system" "orchestrator" {
  count = local.orchestrator_efs_enabled ? 1 : 0

  creation_token = "${local.name_prefix}-orchestrator"
  encrypted      = true

  lifecycle_policy {
    transition_to_ia = "AFTER_30_DAYS"
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-orchestrator"
  })
}

resource "aws_efs_backup_policy" "orchestrator" {
  count = local.orchestrator_efs_enabled ? 1 : 0

  file_system_id = aws_efs_file_system.orchestrator[0].id

  backup_policy {
    status = "ENABLED"
  }
}

resource "aws_efs_access_point" "orchestrator" {
  count = local.orchestrator_efs_enabled ? 1 : 0

  file_system_id = aws_efs_file_system.orchestrator[0].id

  posix_user {
    gid = 1000
    uid = 1000
  }

  root_directory {
    path = "/fleet-health"

    creation_info {
      owner_gid   = 1000
      owner_uid   = 1000
      permissions = "0755"
    }
  }

  tags = local.common_tags
}

resource "aws_efs_mount_target" "orchestrator" {
  for_each = local.orchestrator_efs_enabled ? toset(var.public_subnet_ids) : toset([])

  file_system_id  = aws_efs_file_system.orchestrator[0].id
  security_groups = [aws_security_group.efs[0].id]
  subnet_id       = each.value
}

resource "aws_lb" "web" {
  count = var.enable_ecs ? 1 : 0

  name               = "${local.name_prefix}-web"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb[0].id]
  subnets            = var.public_subnet_ids

  tags = local.common_tags
}

resource "aws_lb_target_group" "web" {
  count = var.enable_ecs ? 1 : 0

  name        = "${local.name_prefix}-web"
  port        = local.ecs_services.web.port
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = var.vpc_id

  health_check {
    enabled             = true
    healthy_threshold   = 2
    interval            = 30
    matcher             = "200-399"
    path                = "/health"
    timeout             = 5
    unhealthy_threshold = 3
  }

  tags = local.common_tags
}

resource "aws_security_group" "orchestrator_alb" {
  count = var.enable_api_gateway ? 1 : 0

  name        = "${local.name_prefix}-orchestrator-alb"
  description = "Allow API Gateway VPC link traffic to the internal orchestrator ALB."
  vpc_id      = var.vpc_id

  ingress {
    description     = "HTTP from API Gateway VPC link"
    from_port       = 80
    to_port         = 80
    protocol        = "tcp"
    security_groups = [aws_security_group.apigateway_vpc_link[0].id]
  }

  egress {
    description = "Outbound to orchestrator tasks"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = local.common_tags
}

resource "aws_lb" "orchestrator" {
  count = var.enable_api_gateway ? 1 : 0

  name               = substr("${local.name_prefix}-orchestrator", 0, 32)
  internal           = true
  load_balancer_type = "application"
  security_groups    = [aws_security_group.orchestrator_alb[0].id]
  subnets            = local.runtime_private_subnet_ids

  tags = local.common_tags
}

resource "aws_lb_target_group" "orchestrator" {
  count = var.enable_api_gateway ? 1 : 0

  name        = substr("${local.name_prefix}-orch", 0, 32)
  port        = local.ecs_services.orchestrator.port
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = var.vpc_id

  health_check {
    enabled             = true
    healthy_threshold   = 2
    interval            = 30
    matcher             = "200-399"
    path                = "/health"
    timeout             = 5
    unhealthy_threshold = 3
  }

  tags = local.common_tags
}

resource "aws_lb_listener" "orchestrator_http" {
  count = var.enable_api_gateway ? 1 : 0

  load_balancer_arn = aws_lb.orchestrator[0].arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.orchestrator[0].arn
  }
}

resource "aws_lb_listener" "web_http" {
  count = var.enable_ecs ? 1 : 0

  load_balancer_arn = aws_lb.web[0].arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.web[0].arn
  }
}

resource "aws_ecs_task_definition" "service" {
  for_each = local.ecs_service_map

  family                   = "${local.name_prefix}-${each.key}"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = each.value.cpu
  memory                   = each.value.memory
  execution_role_arn       = aws_iam_role.ecs_task_execution[0].arn
  task_role_arn            = aws_iam_role.ecs_task[0].arn

  container_definitions = jsonencode([
    {
      name      = each.key
      image     = each.value.image
      essential = true
      portMappings = [
        {
          containerPort = each.value.port
          hostPort      = each.value.port
          protocol      = "tcp"
        }
      ]
      mountPoints = each.key == "orchestrator" && local.orchestrator_efs_enabled ? [
        {
          sourceVolume  = "orchestrator-data"
          containerPath = local.orchestrator_data_mount_path
          readOnly      = false
        }
      ] : []
      environment = [
        for name, value in each.value.environment : {
          name  = name
          value = value
        }
      ]
      secrets = [
        for name, arn in each.value.secrets : {
          name      = name
          valueFrom = arn
        }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = each.value.log_group
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = each.key
        }
      }
    }
  ])

  dynamic "volume" {
    for_each = each.key == "orchestrator" && local.orchestrator_efs_enabled ? [1] : []

    content {
      name = "orchestrator-data"

      efs_volume_configuration {
        file_system_id     = aws_efs_file_system.orchestrator[0].id
        transit_encryption = "ENABLED"

        authorization_config {
          access_point_id = aws_efs_access_point.orchestrator[0].id
          iam             = "ENABLED"
        }
      }
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.service
  ]

  tags = local.common_tags
}

resource "aws_ecs_service" "service" {
  for_each = local.ecs_service_map

  name            = each.key
  cluster         = aws_ecs_cluster.main[0].id
  task_definition = aws_ecs_task_definition.service[each.key].arn
  desired_count   = var.ecs_desired_count
  launch_type     = "FARGATE"
  # Give new tasks time to boot before ALB health checks can mark them unhealthy.
  health_check_grace_period_seconds = (
    (each.key == "web") || (each.key == "orchestrator" && var.enable_api_gateway)
  ) ? 300 : null

  network_configuration {
    assign_public_ip = true
    security_groups = [
      each.key == "web" ? aws_security_group.web[0].id : aws_security_group.orchestrator[0].id
    ]
    subnets = var.public_subnet_ids
  }

  dynamic "load_balancer" {
    for_each = each.key == "web" ? [1] : []

    content {
      target_group_arn = aws_lb_target_group.web[0].arn
      container_name   = each.key
      container_port   = each.value.port
    }
  }

  dynamic "load_balancer" {
    for_each = each.key == "orchestrator" && var.enable_api_gateway ? [1] : []

    content {
      target_group_arn = aws_lb_target_group.orchestrator[0].arn
      container_name   = each.key
      container_port   = each.value.port
    }
  }

  dynamic "service_registries" {
    for_each = each.key == "orchestrator" ? [1] : []

    content {
      registry_arn = aws_service_discovery_service.orchestrator[0].arn
    }
  }

  depends_on = [
    aws_efs_mount_target.orchestrator,
    aws_lb_listener.web_http,
    aws_lb_listener.orchestrator_http,
    aws_iam_role_policy_attachment.ecs_task_execution,
    aws_iam_role_policy.ecs_task_efs_access
  ]

  tags = local.common_tags
}
