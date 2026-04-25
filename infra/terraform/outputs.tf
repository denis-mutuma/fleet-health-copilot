output "artifacts_bucket_name" {
  value       = aws_s3_bucket.artifacts.bucket
  description = "Artifact bucket used by the selected environment."
}
