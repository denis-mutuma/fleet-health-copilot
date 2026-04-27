# S3 Vectors operations checklist

Use this when demoing **Amazon S3 Vectors** alongside the orchestrator ([`rag.py`](../services/orchestrator/src/fleet_health_orchestrator/rag.py), [`embeddings.py`](../services/orchestrator/src/fleet_health_orchestrator/embeddings.py)).

## 0. Optional Terraform provisioning

The root module can create an S3 Vectors **vector bucket** and **index** when **`enable_s3_vectors_rag = true`** (AWS provider 6.35+). Configure this directly in [infra/terraform/env/dev.tfvars](../infra/terraform/env/dev.tfvars) or [infra/terraform/env/prod.tfvars](../infra/terraform/env/prod.tfvars). With **`enable_ecs`**, the orchestrator task role receives **`s3vectors:PutVectors`**, **`QueryVectors`**, and **`GetVectors`** on those resources. You still run **`index_s3_vectors.py`** after **`index_documents.py`** with the same embedding settings as production queries.

## 1. Index and query must match

- Set **`FLEET_S3_VECTORS_EMBEDDING_DIM`** to the **index dimension** (e.g. `384` for `all-MiniLM-L6-v2`, or the OpenAI embedding model output size).
- Set **`FLEET_EMBEDDING_PROVIDER`** the same way for **indexing** and **query** (default `hash` is deterministic only; use `openai`, `http`, or `sentence_transformers` for meaningful ANN).
- Run indexing **after** SQLite has documents (`index_documents.py` against the API), then:

```bash
.venv/bin/python services/orchestrator/scripts/index_s3_vectors.py \
  --bucket YOUR_VECTOR_BUCKET \
  --index YOUR_INDEX_NAME \
  --embedding-provider openai
# or: --index-arn arn:aws:s3vectors:...
```

Optional **`--embedding-provider`** matches **`FLEET_EMBEDDING_PROVIDER`** on the orchestrator (defaults follow the environment). The script prints the resolved provider and dimension to **stderr** before **`put_vectors`** so you can confirm parity with query-time settings.

Use **`--dry-run`** first to confirm batch counts.

## 2. IAM

- **`s3vectors:PutVectors`** for `index_s3_vectors.py`
- **`s3vectors:QueryVectors`** and **`s3vectors:GetVectors`** for the orchestrator (metadata is returned on query)

## 3. Orchestrator environment

- `FLEET_RETRIEVAL_BACKEND=s3vectors`
- `FLEET_S3_VECTORS_BUCKET` + `FLEET_S3_VECTORS_INDEX`, **or** `FLEET_S3_VECTORS_INDEX_ARN`
- Optional: `FLEET_S3_VECTORS_QUERY_VECTOR_JSON` for fixed-vector integration tests only

## 4. Verify

- Hit **`GET /v1/rag/search?query=...`** or orchestrate an event and confirm evidence runbook IDs match expectations.
- Cross-check CloudWatch / S3 Vectors metrics in the AWS console if something fails silently.
