"""Migration registry — all migrations in declaration order."""

from fleet_health_orchestrator.migrations.m001_baseline_tables import MIGRATION as M001
from fleet_health_orchestrator.migrations.m002_add_tenant_id import MIGRATION as M002
from fleet_health_orchestrator.migrations.m003_audit_events_table import MIGRATION as M003
from fleet_health_orchestrator.migrations.m004_tenant_indexes import MIGRATION as M004
from fleet_health_orchestrator.migrations.m005_audit_retention_policy import MIGRATION as M005

ALL_MIGRATIONS: list[dict] = [M001, M002, M003, M004, M005]
