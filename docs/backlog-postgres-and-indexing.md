# Backlog: managed Postgres and automated indexing

This repository’s AWS path today uses **SQLite on EFS** (or `/tmp` when EFS is off) for the orchestrator and **manual / script-driven** S3 Vectors indexing. The [AWS deployment plan](aws-deployment-plan.md) lists the following as **not implemented**.

## Managed Postgres (RDS or Aurora)

**Goal:** Durable, multi-AZ-friendly persistence for the orchestrator instead of SQLite + EFS.

**Design sketch:**

1. **Terraform:** `aws_db_subnet_group`, `aws_security_group` (allow ECS task SG on 5432), `aws_rds_cluster` (Aurora Serverless v2) or `aws_db_instance` (RDS Postgres), `aws_secretsmanager_secret` for master URL (rotation optional).
2. **Orchestrator:** Replace or abstract the SQLite repository layer with SQLAlchemy/asyncpg (or equivalent) targeting `DATABASE_URL` from Secrets Manager; run migrations (Alembic) on task startup or as a one-shot job.
3. **ECS:** Grant the task execution/task role `secretsmanager:GetSecretValue` on the DB secret; inject `DATABASE_URL` or discrete `PGHOST`/`PGUSER`/… env vars.
4. **Cutover:** For existing demos, export SQLite → import Postgres once; for greenfield, start on Postgres.

## Automated embedding and corpus upsert

**Goal:** After documents change in SQLite/Postgres or in object storage, **refresh S3 Vectors** without a human running [`index_s3_vectors.py`](../services/orchestrator/scripts/index_s3_vectors.py) on a laptop.

**Design sketch:**

1. **Trigger:** EventBridge on S3 `PutObject` for a runbooks prefix, or on a schedule, or after API “ingest complete” events.
2. **Compute:** Lambda (small batches), **ECS Fargate task** (heavy embedding models), or **AWS Batch** for `index_s3_vectors.py` / a thin wrapper that calls the same Python module.
3. **IAM:** Task role with `s3vectors:PutVectors` on the vector bucket/index; read access to source docs if needed.
4. **Embedding service:** Same constraint as today — query-time `FLEET_EMBEDDING_PROVIDER` must match indexing (OpenAI, HTTP endpoint, or `sentence_transformers` in the job container image).

## Suggested sequencing

1. Stabilize **ECS + ALB + Clerk** in dev/prod.
2. Add **S3 Vectors** + manual indexing for demos.
3. Introduce **Postgres** when you need concurrency, backups, or capstone requirements.
4. Add **automation** for indexing once the ingestion path is stable and idempotent.
