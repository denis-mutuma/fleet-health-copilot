"""Request identity and authorization context helpers.

This module provides a transport-agnostic identity object that can be attached
to each request by middleware and consumed by endpoint dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from fastapi import Request

from fleet_health_orchestrator.config import OrchestratorSettings


def _parse_roles(raw_value: str) -> set[str]:
    roles: set[str] = set()
    for token in raw_value.split(","):
        normalized = token.strip().lower()
        if normalized:
            roles.add(normalized)
    return roles


@dataclass(frozen=True)
class RequestIdentity:
    actor_id: str | None
    tenant_id: str | None
    fleet_id: str | None
    auth_provider: str | None
    roles: frozenset[str]
    authenticated: bool

    def has_any_role(self, expected_roles: Iterable[str]) -> bool:
        expected = {role.strip().lower() for role in expected_roles if role.strip()}
        if not expected:
            return True
        return bool(self.roles.intersection(expected))


def anonymous_identity(default_roles: Iterable[str] = ()) -> RequestIdentity:
    return RequestIdentity(
        actor_id=None,
        tenant_id=None,
        fleet_id=None,
        auth_provider=None,
        roles=frozenset(role.strip().lower() for role in default_roles if role.strip()),
        authenticated=False,
    )


def resolve_request_identity(request: Request, settings: OrchestratorSettings) -> RequestIdentity:
    actor_id = request.headers.get(settings.auth_actor_header, "").strip() or None
    tenant_id = request.headers.get(settings.auth_tenant_header, "").strip() or None
    fleet_id = request.headers.get(settings.auth_fleet_header, "").strip() or None
    auth_provider = request.headers.get(settings.auth_provider_header, "").strip() or None

    roles_header = request.headers.get(settings.auth_roles_header, "")
    roles = _parse_roles(roles_header)
    if not roles:
        roles = set(settings.auth_default_roles_list)

    authenticated = actor_id is not None
    return RequestIdentity(
        actor_id=actor_id,
        tenant_id=tenant_id,
        fleet_id=fleet_id,
        auth_provider=auth_provider,
        roles=frozenset(roles),
        authenticated=authenticated,
    )