"""AWS Lambda entrypoint for the ephemeral demo deployment."""

from mangum import Mangum

from fleet_health_orchestrator.main import app


handler = Mangum(app, lifespan="off")
