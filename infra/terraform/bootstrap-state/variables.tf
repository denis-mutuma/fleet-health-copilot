variable "aws_region" {
  type        = string
  description = "Region for the state bucket and lock table."
  default     = "us-east-1"
}

variable "project_name" {
  type        = string
  description = "Tag value for Project."
  default     = "fleet-health-copilot"
}

variable "state_bucket_name" {
  type        = string
  description = "Globally unique S3 bucket name for Terraform state objects."
}

variable "lock_table_name" {
  type        = string
  description = "DynamoDB table name for Terraform state locks."
  default     = "fleet-health-copilot-tf-locks"
}
