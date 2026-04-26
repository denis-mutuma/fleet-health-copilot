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

output "s3_vectors_bucket_name" {
  value       = var.enable_s3_vectors_rag ? aws_s3vectors_vector_bucket.rag[0].vector_bucket_name : null
  description = "S3 Vectors bucket name when enable_s3_vectors_rag is true."
}

output "s3_vectors_index_name" {
  value       = var.enable_s3_vectors_rag ? aws_s3vectors_index.rag[0].index_name : null
  description = "S3 Vectors index name when enable_s3_vectors_rag is true."
}

output "s3_vectors_index_arn" {
  value       = var.enable_s3_vectors_rag ? aws_s3vectors_index.rag[0].index_arn : null
  description = "S3 Vectors index ARN for FLEET_S3_VECTORS_INDEX_ARN when enable_s3_vectors_rag is true."
}

output "s3_vectors_orchestrator_env_hint" {
  value = var.enable_s3_vectors_rag ? {
    FLEET_RETRIEVAL_BACKEND        = "s3vectors"
    FLEET_S3_VECTORS_BUCKET        = aws_s3vectors_vector_bucket.rag[0].vector_bucket_name
    FLEET_S3_VECTORS_INDEX         = aws_s3vectors_index.rag[0].index_name
    FLEET_S3_VECTORS_INDEX_ARN     = aws_s3vectors_index.rag[0].index_arn
    FLEET_S3_VECTORS_EMBEDDING_DIM = tostring(var.s3_vectors_embedding_dimension)
  } : null
  description = "Suggested orchestrator environment variables after apply (set FLEET_EMBEDDING_PROVIDER to match index_s3_vectors.py)."
}
