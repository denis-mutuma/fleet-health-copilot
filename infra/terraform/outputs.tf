output "artifacts_bucket_name" {
  value       = aws_s3_bucket.artifacts.bucket
  description = "Artifact bucket used by the selected environment."
}

output "ecr_repository_urls" {
  value = {
    for name, repository in aws_ecr_repository.service : name => repository.repository_url
  }
  description = "ECR repository URLs by service name."
}

output "github_actions_role_arn" {
  value       = local.github_oidc_enabled ? aws_iam_role.github_actions[0].arn : null
  description = "GitHub Actions role ARN for image push workflows, when OIDC is enabled."
}

output "managed_secret_arns" {
  value       = local.managed_secret_arns
  description = "Secrets Manager secret ARNs by runtime environment variable name. Populate values outside Terraform."
}

output "ecs_cluster_name" {
  value       = var.enable_ecs ? aws_ecs_cluster.main[0].name : null
  description = "ECS cluster name when the Fargate scaffold is enabled."
}

output "web_load_balancer_dns_name" {
  value       = var.enable_ecs ? aws_lb.web[0].dns_name : null
  description = "Public DNS name for the web application load balancer when ECS is enabled."
}

output "orchestrator_service_discovery_name" {
  value       = var.enable_ecs ? "orchestrator.${aws_service_discovery_private_dns_namespace.main[0].name}" : null
  description = "Private DNS name for the orchestrator service when ECS is enabled."
}

output "orchestrator_efs_file_system_id" {
  value       = local.orchestrator_efs_enabled ? aws_efs_file_system.orchestrator[0].id : null
  description = "EFS file system ID for durable orchestrator SQLite storage when enabled."
}

output "orchestrator_database_path" {
  value       = var.enable_ecs ? local.orchestrator_db_path : null
  description = "Database path configured for the orchestrator task when ECS is enabled."
}
