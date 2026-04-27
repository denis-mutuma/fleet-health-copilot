resource "aws_security_group" "apigateway_vpc_link" {
  count = var.enable_api_gateway ? 1 : 0

  name        = "${local.name_prefix}-apigw-vpc-link"
  description = "Security group for API Gateway VPC link ENIs."
  vpc_id      = var.vpc_id

  egress {
    description = "Outbound to internal orchestrator ALB"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = [data.aws_vpc.selected[0].cidr_block]
  }

  tags = local.common_tags
}

resource "aws_apigatewayv2_vpc_link" "orchestrator" {
  count = var.enable_api_gateway ? 1 : 0

  name               = "${local.name_prefix}-orchestrator"
  security_group_ids = [aws_security_group.apigateway_vpc_link[0].id]
  subnet_ids         = var.public_subnet_ids

  tags = local.common_tags
}

resource "aws_cloudwatch_log_group" "apigateway" {
  count = var.enable_api_gateway ? 1 : 0

  name              = "/apigateway/${local.name_prefix}/orchestrator"
  retention_in_days = 14

  tags = local.common_tags
}

resource "aws_apigatewayv2_api" "orchestrator" {
  count = var.enable_api_gateway ? 1 : 0

  name          = "${local.name_prefix}-orchestrator"
  protocol_type = "HTTP"

  cors_configuration {
    allow_headers  = ["authorization", "content-type", "x-correlation-id"]
    allow_methods  = ["GET", "POST", "PATCH", "OPTIONS"]
    allow_origins  = var.enable_cloudfront ? ["https://${aws_cloudfront_distribution.web[0].domain_name}"] : ["*"]
    expose_headers = ["x-correlation-id"]
    max_age        = 300
  }

  tags = local.common_tags
}

resource "aws_apigatewayv2_integration" "orchestrator" {
  count = var.enable_api_gateway ? 1 : 0

  api_id                 = aws_apigatewayv2_api.orchestrator[0].id
  connection_id          = aws_apigatewayv2_vpc_link.orchestrator[0].id
  connection_type        = "VPC_LINK"
  integration_method     = "ANY"
  integration_type       = "HTTP_PROXY"
  integration_uri        = aws_lb_listener.orchestrator_http[0].arn
  payload_format_version = "1.0"
  timeout_milliseconds   = 30000
}

resource "aws_apigatewayv2_route" "orchestrator_root" {
  count = var.enable_api_gateway ? 1 : 0

  api_id    = aws_apigatewayv2_api.orchestrator[0].id
  route_key = "ANY /"
  target    = "integrations/${aws_apigatewayv2_integration.orchestrator[0].id}"
}

resource "aws_apigatewayv2_route" "orchestrator_proxy" {
  count = var.enable_api_gateway ? 1 : 0

  api_id    = aws_apigatewayv2_api.orchestrator[0].id
  route_key = "ANY /{proxy+}"
  target    = "integrations/${aws_apigatewayv2_integration.orchestrator[0].id}"
}

resource "aws_apigatewayv2_stage" "orchestrator_default" {
  count = var.enable_api_gateway ? 1 : 0

  api_id      = aws_apigatewayv2_api.orchestrator[0].id
  name        = "$default"
  auto_deploy = true

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.apigateway[0].arn
    format = jsonencode({
      requestId      = "$context.requestId"
      ip             = "$context.identity.sourceIp"
      requestTime    = "$context.requestTime"
      httpMethod     = "$context.httpMethod"
      routeKey       = "$context.routeKey"
      status         = "$context.status"
      responseLength = "$context.responseLength"
    })
  }

  tags = local.common_tags
}

data "aws_cloudfront_cache_policy" "caching_disabled" {
  count = var.enable_cloudfront ? 1 : 0
  name  = "Managed-CachingDisabled"
}

data "aws_cloudfront_cache_policy" "caching_optimized" {
  count = var.enable_cloudfront ? 1 : 0
  name  = "Managed-CachingOptimized"
}

data "aws_cloudfront_origin_request_policy" "all_viewer_except_host_header" {
  count = var.enable_cloudfront ? 1 : 0
  name  = "Managed-AllViewerExceptHostHeader"
}

resource "aws_wafv2_web_acl" "cloudfront" {
  count = var.enable_waf ? 1 : 0

  name  = "${local.name_prefix}-cloudfront"
  scope = "CLOUDFRONT"

  default_action {
    allow {}
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "${replace(local.name_prefix, "-", "")}-cloudfront"
    sampled_requests_enabled   = true
  }

  rule {
    name     = "AWSManagedRulesCommonRuleSet"
    priority = 1

    override_action {
      none {}
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesCommonRuleSet"
        vendor_name = "AWS"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${replace(local.name_prefix, "-", "")}-common"
      sampled_requests_enabled   = true
    }
  }

  rule {
    name     = "AWSManagedRulesKnownBadInputsRuleSet"
    priority = 2

    override_action {
      none {}
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesKnownBadInputsRuleSet"
        vendor_name = "AWS"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${replace(local.name_prefix, "-", "")}-badinputs"
      sampled_requests_enabled   = true
    }
  }

  tags = local.common_tags
}

resource "aws_cloudfront_distribution" "web" {
  count = var.enable_cloudfront ? 1 : 0

  enabled             = true
  is_ipv6_enabled     = true
  comment             = "${local.name_prefix} web edge"
  default_root_object = ""
  web_acl_id          = var.enable_waf ? aws_wafv2_web_acl.cloudfront[0].arn : null

  origin {
    domain_name = aws_lb.web[0].dns_name
    origin_id   = "web-alb"

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "http-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  default_cache_behavior {
    target_origin_id         = "web-alb"
    viewer_protocol_policy   = "redirect-to-https"
    allowed_methods          = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods           = ["GET", "HEAD", "OPTIONS"]
    compress                 = true
    cache_policy_id          = data.aws_cloudfront_cache_policy.caching_disabled[0].id
    origin_request_policy_id = data.aws_cloudfront_origin_request_policy.all_viewer_except_host_header[0].id
  }

  ordered_cache_behavior {
    path_pattern             = "/_next/static/*"
    target_origin_id         = "web-alb"
    viewer_protocol_policy   = "redirect-to-https"
    allowed_methods          = ["GET", "HEAD", "OPTIONS"]
    cached_methods           = ["GET", "HEAD", "OPTIONS"]
    compress                 = true
    cache_policy_id          = data.aws_cloudfront_cache_policy.caching_optimized[0].id
    origin_request_policy_id = data.aws_cloudfront_origin_request_policy.all_viewer_except_host_header[0].id
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }

  tags = local.common_tags
}