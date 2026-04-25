FROM python:3.12-slim
WORKDIR /app

COPY services/orchestrator/pyproject.toml ./pyproject.toml
COPY services/orchestrator/src ./src
RUN pip install --no-cache-dir .

ENV PYTHONPATH=/app/src

CMD ["uvicorn", "fleet_health_orchestrator.main:app", "--host", "0.0.0.0", "--port", "8000"]
