output "state_bucket_id" {
  value       = aws_s3_bucket.tf_state.id
  description = "S3 bucket for terraform.tfstate files."
}

output "lock_table_name" {
  value       = aws_dynamodb_table.tf_locks.name
  description = "DynamoDB table used as the S3 backend lock."
}
