# Merge with env/<env>.tfvars when creating S3 Vectors RAG infra:
#   terraform plan -var-file=env/dev.tfvars -var-file=env/s3vectors.example.tfvars -var='github_repository=OWNER/REPO'
# Requires AWS provider 6.x (root module). After apply, use output s3_vectors_orchestrator_env_hint;
# then run services/orchestrator/scripts/index_s3_vectors.py (see docs/s3-vectors-operations.md).

enable_s3_vectors_rag          = true
s3_vectors_embedding_dimension = 384
s3_vectors_distance_metric     = "cosine"
# s3_vectors_bucket_name = "my-globally-unique-vector-bucket"
# s3_vectors_force_destroy = true   # dev only: allow terraform destroy to empty vectors
