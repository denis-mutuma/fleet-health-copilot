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

  validation {
    condition     = !var.enable_ecs || (contains(var.container_repositories, "web") && contains(var.container_repositories, "orchestrator"))
    error_message = "container_repositories must include web and orchestrator when enable_ecs is true."
  }
}

variable "github_repository" {
  type        = string
  description = "GitHub repository slug allowed to assume the deploy role, for example owner/repo. Leave empty to skip GitHub OIDC resources."
  default     = ""
}

variable "enable_managed_secrets" {
  type        = bool
  description = "Whether to create AWS Secrets Manager placeholders for runtime secrets."
  default     = true
}

variable "managed_secret_names" {
  type        = set(string)
  description = "Runtime secret environment variable names to create as AWS Secrets Manager placeholders. Values are populated outside Terraform."
  default     = ["CLERK_SECRET_KEY"]
}

variable "enable_ecs" {
  type        = bool
  description = "Whether to create the ECS Fargate runtime scaffold."
  default     = false
}

variable "vpc_id" {
  type        = string
  description = "VPC ID for ECS and load balancer resources. Required when enable_ecs is true."
  default     = ""

  validation {
    condition     = !var.enable_ecs || var.vpc_id != ""
    error_message = "vpc_id must be provided when enable_ecs is true."
  }
}

variable "public_subnet_ids" {
  type        = list(string)
  description = "Public subnet IDs for the load balancer and Fargate services. At least two are recommended when enable_ecs is true."
  default     = []

  validation {
    condition     = !var.enable_ecs || length(var.public_subnet_ids) >= 2
    error_message = "At least two public_subnet_ids must be provided when enable_ecs is true."
  }
}

variable "container_image_tags" {
  type        = map(string)
  description = "Image tags to deploy from the generated ECR repositories, keyed by service name."
  default = {
    web          = "latest"
    orchestrator = "latest"
  }
}

variable "ecs_desired_count" {
  type        = number
  description = "Desired task count for each ECS service."
  default     = 1
}

variable "enable_orchestrator_efs" {
  type        = bool
  description = "Whether to mount durable EFS storage for the orchestrator SQLite database when ECS is enabled."
  default     = true
}

variable "web_next_public_clerk_publishable_key" {
  type        = string
  description = "Clerk publishable key exposed to the browser for the web service."
  default     = ""
}

variable "web_next_public_orchestrator_api_base_url" {
  type        = string
  description = "Browser-facing orchestrator API base URL for the web service."
  default     = ""
}

variable "web_secret_arns" {
  type        = map(string)
  description = "Secret environment variables for the web task, keyed by environment variable name with Secrets Manager or SSM parameter ARNs as values."
  default     = {}
}

variable "orchestrator_environment" {
  type        = map(string)
  description = "Non-secret environment variables for the orchestrator task."
  default = {
    FLEET_DB_PATH           = "/tmp/fleet-health.db"
    FLEET_RETRIEVAL_BACKEND = "lexical"
  }
}

variable "orchestrator_secret_arns" {
  type        = map(string)
  description = "Secret environment variables for the orchestrator task, keyed by environment variable name with Secrets Manager or SSM parameter ARNs as values."
  default     = {}
}
