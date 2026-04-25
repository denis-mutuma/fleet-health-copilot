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

  validation {
    condition     = contains(["dev", "test", "prod"], var.environment)
    error_message = "Environment must be one of: dev, test, prod."
  }
}

variable "tags" {
  type        = map(string)
  description = "Additional tags applied to all resources."
  default     = {}
}

variable "container_repositories" {
  type        = set(string)
  description = "Container image repositories to create in ECR."
  default     = ["web", "orchestrator"]
}

variable "github_repository" {
  type        = string
  description = "GitHub repository slug allowed to assume the deploy role, for example owner/repo. Leave empty to skip GitHub OIDC resources."
  default     = ""
}
