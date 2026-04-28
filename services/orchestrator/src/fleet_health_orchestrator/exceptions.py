"""Application exception hierarchy for Fleet Health Orchestrator."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class OrchestratorError(Exception):
    """Base domain exception with HTTP mapping metadata."""

    message: str
    status_code: int = 500
    error_code: str = "internal_error"
    details: dict[str, Any] = field(default_factory=dict)

    def to_response(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "error": {
                "code": self.error_code,
                "message": self.message,
            }
        }
        if self.details:
            payload["error"]["details"] = self.details
        return payload


class InvalidRequestError(OrchestratorError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message=message,
            status_code=400,
            error_code="invalid_request",
            details=details or {},
        )


class ResourceNotFoundError(OrchestratorError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message=message,
            status_code=404,
            error_code="resource_not_found",
            details=details or {},
        )


class ReadinessError(OrchestratorError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message=message,
            status_code=503,
            error_code="service_not_ready",
            details=details or {},
        )


class AuthenticationRequiredError(OrchestratorError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message=message,
            status_code=401,
            error_code="authentication_required",
            details=details or {},
        )


class AuthorizationError(OrchestratorError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message=message,
            status_code=403,
            error_code="forbidden",
            details=details or {},
        )


class DependencyInitializationError(OrchestratorError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message=message,
            status_code=500,
            error_code="dependency_initialization_failed",
            details=details or {},
        )


class AnomalyThresholdError(InvalidRequestError):
    def __init__(self, message: str = "Event does not exceed threshold.") -> None:
        super().__init__(message=message)
