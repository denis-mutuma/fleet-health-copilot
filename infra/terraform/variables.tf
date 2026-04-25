variable "project_name" {
  type        = string
  description = "Project name prefix for resources."
  default     = "fleet-health-copilot"
}

variable "aws_region" {
  type        = string
  description = "AWS region for deployment."
  default     = "us-east-1"
}

variable "environment" {
  type        = string
  description = "Environment name: dev, test, prod."
}
