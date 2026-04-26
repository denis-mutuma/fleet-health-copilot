# Merge with dev.tfvars (or pass multiple -var-file) when creating S3 Vectors RAG infra.
# Requires AWS provider 6.x (root module). After apply, use output s3_vectors_orchestrator_env_hint.

enable_s3_vectors_rag          = true
s3_vectors_embedding_dimension = 384
s3_vectors_distance_metric     = "cosine"
# s3_vectors_bucket_name = "my-globally-unique-vector-bucket"
# s3_vectors_force_destroy = true   # dev only: allow terraform destroy to empty vectors
