# Optional Amazon S3 Vectors bucket + index for RAG (orchestrator FLEET_RETRIEVAL_BACKEND=s3vectors).
# Requires AWS provider >= 6.35. Enable with enable_s3_vectors_rag = true.

data "aws_caller_identity" "current" {}

locals {
  s3_vectors_bucket_effective_name = var.s3_vectors_bucket_name != "" ? var.s3_vectors_bucket_name : substr(
    replace(lower("${local.name_prefix}-vec-${data.aws_caller_identity.current.account_id}"), "_", "-"),
    0,
    63
  )
  s3_vectors_index_effective_name = var.s3_vectors_index_name != "" ? var.s3_vectors_index_name : "${local.name_prefix}-rag"
}

resource "aws_s3vectors_vector_bucket" "rag" {
  count = var.enable_s3_vectors_rag ? 1 : 0

  vector_bucket_name = local.s3_vectors_bucket_effective_name

  encryption_configuration {
    sse_type = "AES256"
  }

  force_destroy = var.s3_vectors_force_destroy

  tags = local.common_tags
}

resource "aws_s3vectors_index" "rag" {
  count = var.enable_s3_vectors_rag ? 1 : 0

  index_name         = local.s3_vectors_index_effective_name
  vector_bucket_name = aws_s3vectors_vector_bucket.rag[0].vector_bucket_name

  data_type       = "float32"
  dimension       = var.s3_vectors_embedding_dimension
  distance_metric = var.s3_vectors_distance_metric

  metadata_configuration {
    non_filterable_metadata_keys = ["document_id", "title", "source", "excerpt"]
  }

  tags = local.common_tags
}

data "aws_iam_policy_document" "ecs_task_s3vectors" {
  count = var.enable_ecs && var.enable_s3_vectors_rag ? 1 : 0

  statement {
    sid = "S3VectorsRag"
    actions = [
      "s3vectors:PutVectors",
      "s3vectors:QueryVectors",
      "s3vectors:GetVectors"
    ]
    effect = "Allow"
    resources = [
      aws_s3vectors_index.rag[0].index_arn,
      aws_s3vectors_vector_bucket.rag[0].vector_bucket_arn,
    ]
  }
}

resource "aws_iam_role_policy" "ecs_task_s3vectors" {
  count = var.enable_ecs && var.enable_s3_vectors_rag ? 1 : 0

  name   = "${local.name_prefix}-ecs-s3vectors-rag"
  role   = aws_iam_role.ecs_task[0].id
  policy = data.aws_iam_policy_document.ecs_task_s3vectors[0].json
}
