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
