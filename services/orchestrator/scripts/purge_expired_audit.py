"""CLI script — purge expired audit events.

Reads all rows from ``audit_retention_policy`` where ``retention_days`` is
not NULL and deletes matching ``audit_events`` rows whose ``occurred_at``
timestamp falls before the computed cutoff.

Usage
-----
# From the project root with the virtualenv active:
python services/orchestrator/scripts/purge_expired_audit.py

# Against a specific SQLite database:
python services/orchestrator/scripts/purge_expired_audit.py \\
    --db-path /var/data/fleet_health.db

# Against a PostgreSQL instance (overrides --db-path):
python services/orchestrator/scripts/purge_expired_audit.py \\
    --database-url postgresql://user:pass@host:5432/fleet

Exit codes
----------
0 — success (even if no rows were deleted)
1 — error (exception raised during purge)
"""

import argparse
import json
import logging
import sys
from pathlib import Path


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Purge audit events that exceed their configured retention period.",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=None,
        help=(
            "Path to the SQLite database file.  "
            "Defaults to the orchestrator's built-in data/ path.  "
            "Ignored when --database-url is supplied."
        ),
    )
    parser.add_argument(
        "--database-url",
        default="",
        help=(
            "PostgreSQL connection URL "
            "(e.g. postgresql://user:pass@host:5432/fleet).  "
            "Takes precedence over --db-path."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Print what would be deleted without committing any changes.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Log verbosity level (default: INFO).",
    )
    return parser


def main() -> None:
    parser = _build_arg_parser()
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s [purge_expired_audit] %(message)s",
    )
    logger = logging.getLogger("fleet.retention")

    # Resolve database path / URL
    database_url: str = args.database_url.strip()

    if database_url:
        db_path = Path("/tmp/unused.db")  # value is ignored when database_url is set
        logger.info("Connecting to PostgreSQL: %s", database_url.split("@")[-1])
    else:
        if args.db_path is not None:
            db_path = args.db_path
        else:
            # Mirror the default used by OrchestratorSettings
            db_path = (
                Path(__file__).resolve().parents[2]
                / "src"
                / "fleet_health_orchestrator"
                / ".."
                / ".."
                / "data"
                / "fleet_health.db"
            ).resolve()
        logger.info("Connecting to SQLite: %s", db_path)

    try:
        # Import here so the script can be called from the project root after
        # activating the virtualenv or installing the package.
        from fleet_health_orchestrator.repository import FleetRepository

        repo = FleetRepository(db_path=db_path, database_url=database_url)
    except Exception as exc:
        logger.error("Failed to initialize repository: %s", exc)
        sys.exit(1)

    if args.dry_run:
        # Run the purge against a read-only preview by reading policy rows directly
        # without committing — we just log what the cutoffs would be.
        _dry_run_preview(repo, logger)
        return

    try:
        result = repo.purge_expired_audit_events()
        logger.info(
            "Audit retention sweep complete: %s",
            json.dumps(result),
            extra={"event": "audit_retention_sweep", **result},
        )
        print(json.dumps(result))
    except Exception as exc:
        logger.error("Audit retention sweep failed: %s", exc)
        sys.exit(1)


def _dry_run_preview(repo, logger) -> None:  # type: ignore[no-untyped-def]
    """Log what would be deleted without making any changes."""
    from datetime import datetime, timedelta, timezone

    logger.info("[dry-run] Scanning audit_retention_policy ...")

    with repo._connect() as connection:
        policies = connection.execute(
            "SELECT policy_id, tenant_id, entity_type, retention_days "
            "FROM audit_retention_policy "
            "WHERE retention_days IS NOT NULL"
        ).fetchall()

    if not policies:
        logger.info("[dry-run] No retention policies configured. Nothing to purge.")
        return

    now = datetime.now(timezone.utc)
    for policy in policies:
        retention_days = int(policy["retention_days"])
        cutoff = (now - timedelta(days=retention_days)).isoformat()
        scope_parts = []
        if policy["tenant_id"]:
            scope_parts.append(f"tenant_id={policy['tenant_id']}")
        if policy["entity_type"]:
            scope_parts.append(f"entity_type={policy['entity_type']}")
        scope = ", ".join(scope_parts) if scope_parts else "global"
        logger.info(
            "[dry-run] policy=%s scope=%s retention_days=%d cutoff=%s",
            policy["policy_id"],
            scope,
            retention_days,
            cutoff,
        )


if __name__ == "__main__":
    main()
