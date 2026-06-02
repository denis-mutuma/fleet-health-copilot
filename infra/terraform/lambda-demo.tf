locals {
  lambda_demo_enabled = var.enable_lambda_demo
}

data "aws_iam_policy_document" "lambda_demo_assume_role" {
  count = local.lambda_demo_enabled ? 1 : 0

  statement {
    actions = ["sts:AssumeRole"]
    effect  = "Allow"

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "lambda_demo_logs" {
  count = local.lambda_demo_enabled ? 1 : 0

  statement {
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents"
    ]
    effect = "Allow"
    resources = [
      "${aws_cloudwatch_log_group.lambda_demo[0].arn}:*"
    ]
  }
}

resource "aws_iam_role" "lambda_demo" {
  count = local.lambda_demo_enabled ? 1 : 0

  name               = "${local.name_prefix}-lambda-demo"
  assume_role_policy = data.aws_iam_policy_document.lambda_demo_assume_role[0].json

  tags = local.common_tags
}

resource "aws_cloudwatch_log_group" "lambda_demo" {
  count = local.lambda_demo_enabled ? 1 : 0

  name              = "/aws/lambda/${local.name_prefix}-demo"
  retention_in_days = 1

  tags = local.common_tags
}

resource "aws_iam_role_policy" "lambda_demo_logs" {
  count = local.lambda_demo_enabled ? 1 : 0

  name   = "${local.name_prefix}-lambda-demo-logs"
  role   = aws_iam_role.lambda_demo[0].id
  policy = data.aws_iam_policy_document.lambda_demo_logs[0].json
}

resource "aws_lambda_function" "demo" {
  count = local.lambda_demo_enabled ? 1 : 0

  function_name = "${local.name_prefix}-demo"
  role          = aws_iam_role.lambda_demo[0].arn
  filename      = var.lambda_demo_package_path
  handler       = "fleet_health_orchestrator.lambda_handler.handler"
  runtime       = "python3.12"
  architectures = ["x86_64"]
  memory_size   = var.lambda_demo_memory_size
  timeout       = var.lambda_demo_timeout_seconds

  reserved_concurrent_executions = var.lambda_demo_reserved_concurrency
  source_code_hash               = filebase64sha256(var.lambda_demo_package_path)

  environment {
    variables = {
      FLEET_LAMBDA_DEMO                            = "true"
      FLEET_DB_PATH                                = "/tmp/fleet-health.db"
      FLEET_RETRIEVAL_BACKEND                      = "lexical"
      FLEET_EMBEDDING_PROVIDER                     = "hash"
      FLEET_OPENAI_REPORT_REFINE                   = "false"
      FLEET_OPENAI_DIAGNOSIS_ENRICH                = "false"
      FLEET_LLM_CHAT_ENABLED                       = "false"
      FLEET_AUDIT_RETENTION_SWEEP_INTERVAL_SECONDS = "0"
      FLEET_LOG_LEVEL                              = "WARNING"
      FLEET_AUTH_REQUIRED                          = "false"
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.lambda_demo,
    aws_iam_role_policy.lambda_demo_logs
  ]

  tags = local.common_tags
}

resource "aws_lambda_function_url" "demo" {
  count = local.lambda_demo_enabled ? 1 : 0

  function_name      = aws_lambda_function.demo[0].function_name
  authorization_type = "NONE"

  cors {
    allow_credentials = false
    allow_headers     = ["content-type", "x-actor-id", "x-roles", "x-tenant-id"]
    allow_methods     = ["GET", "POST", "PATCH"]
    allow_origins     = ["*"]
    expose_headers    = ["x-correlation-id"]
    max_age           = 300
  }
}

resource "aws_lambda_permission" "demo_function_url_public" {
  count = local.lambda_demo_enabled ? 1 : 0

  statement_id           = "AllowPublicFunctionUrlInvoke"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = aws_lambda_function.demo[0].function_name
  principal              = "*"
  function_url_auth_type = "NONE"
}

resource "aws_budgets_budget" "zero_bill_alert" {
  count = var.cost_alert_email != "" ? 1 : 0

  name         = "${local.name_prefix}-zero-bill-alert"
  budget_type  = "COST"
  limit_amount = "0.01"
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.cost_alert_email]
  }
}
