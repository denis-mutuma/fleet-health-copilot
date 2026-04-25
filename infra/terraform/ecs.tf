locals {
  ecs_services = {
    web = {
      cpu       = 512
      memory    = 1024
      port      = 3000
      image     = "${aws_ecr_repository.service["web"].repository_url}:${lookup(var.container_image_tags, "web", "latest")}"
      log_group = "/ecs/${local.name_prefix}/web"
      environment = merge(
        {
          NODE_ENV                              = "production"
          HOSTNAME                              = "0.0.0.0"
          PORT                                  = "3000"
          ORCHESTRATOR_API_BASE_URL             = "http://orchestrator.${local.name_prefix}.local:8000"
          NEXT_PUBLIC_ORCHESTRATOR_API_BASE_URL = var.web_next_public_orchestrator_api_base_url
          NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY     = var.web_next_public_clerk_publishable_key
        }
      )
      secrets = var.web_secret_arns
    }
    orchestrator = {
      cpu         = 512
      memory      = 1024
      port        = 8000
      image       = "${aws_ecr_repository.service["orchestrator"].repository_url}:${lookup(var.container_image_tags, "orchestrator", "latest")}"
      log_group   = "/ecs/${local.name_prefix}/orchestrator"
      environment = var.orchestrator_environment
      secrets     = var.orchestrator_secret_arns
    }
  }

  ecs_service_map    = var.enable_ecs ? local.ecs_services : {}
  ecs_secret_arns    = concat(values(var.web_secret_arns), values(var.orchestrator_secret_arns))
  ecs_secret_enabled = var.enable_ecs && length(local.ecs_secret_arns) > 0
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

  health_check_custom_config {
    failure_threshold = 1
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
    description     = "Orchestrator traffic from web tasks"
    from_port       = local.ecs_services.orchestrator.port
    to_port         = local.ecs_services.orchestrator.port
    protocol        = "tcp"
    security_groups = [aws_security_group.web[0].id]
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
    path                = "/"
    timeout             = 5
    unhealthy_threshold = 3
  }

  tags = local.common_tags
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

  dynamic "service_registries" {
    for_each = each.key == "orchestrator" ? [1] : []

    content {
      registry_arn = aws_service_discovery_service.orchestrator[0].arn
    }
  }

  depends_on = [
    aws_lb_listener.web_http,
    aws_iam_role_policy_attachment.ecs_task_execution
  ]

  tags = local.common_tags
}
