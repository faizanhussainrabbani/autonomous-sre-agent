"""
Production migration runner for the SRE Agent persistence layer.

Usage:
    python scripts/dev/migrate.py

DSN resolution order:
    1. POSTGRES_DSN environment variable
    2. config.persistence.postgres_dsn from config/agent.yaml

Applies all unapplied .sql files from
    src/sre_agent/adapters/persistence/migrations/
in ascending numeric order, tracking applied migrations in the
``schema_migrations`` table.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MIGRATIONS_DIR = _REPO_ROOT / "src" / "sre_agent" / "adapters" / "persistence" / "migrations"
_CONFIG_YAML = _REPO_ROOT / "config" / "agent.yaml"

_CREATE_TRACKING_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    filename   TEXT        PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


def _resolve_dsn() -> str:
    """Return the Postgres DSN from env or config, raise if neither is set."""
    dsn = os.environ.get("POSTGRES_DSN", "").strip()
    if dsn:
        return dsn

    # Fall back to AgentConfig from YAML.
    sys.path.insert(0, str(_REPO_ROOT / "src"))
    from sre_agent.config.settings import AgentConfig

    config = AgentConfig.from_yaml(_CONFIG_YAML)
    dsn = (config.persistence.postgres_dsn or "").strip()
    if dsn:
        return dsn

    raise RuntimeError(
        "No Postgres DSN found. Set the POSTGRES_DSN environment variable "
        "or configure persistence.postgres_dsn in config/agent.yaml."
    )


def _sorted_migration_files() -> list[Path]:
    """Return .sql migration files sorted by their numeric prefix."""
    files = sorted(
        _MIGRATIONS_DIR.glob("*.sql"),
        key=lambda p: p.name,
    )
    return files


async def run_migrations(dsn: str) -> None:
    """Apply all unapplied migrations in order."""
    import asyncpg  # type: ignore[import]

    pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=2)
    try:
        # Ensure the tracking table exists (outside a migration transaction).
        async with pool.acquire() as conn:
            await conn.execute(_CREATE_TRACKING_TABLE)
            logger.debug("schema_migrations_table_ensured")

        migration_files = _sorted_migration_files()
        if not migration_files:
            logger.warning("no_migration_files_found", directory=str(_MIGRATIONS_DIR))
            print(f"WARNING: no .sql files found in {_MIGRATIONS_DIR}")
            return

        for migration_path in migration_files:
            filename = migration_path.name

            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT filename FROM schema_migrations WHERE filename = $1",
                    filename,
                )

            if row is not None:
                print(f"SKIP  {filename}")
                logger.info("migration_skipped", filename=filename)
                continue

            # Apply the migration inside a transaction.
            sql = migration_path.read_text(encoding="utf-8")
            async with pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute(sql)
                    await conn.execute(
                        "INSERT INTO schema_migrations (filename) VALUES ($1)",
                        filename,
                    )

            print(f"APPLY {filename}")
            logger.info("migration_applied", filename=filename)

    finally:
        await pool.close()


def main() -> None:
    """Entry point: resolve DSN, run migrations, exit with appropriate code."""
    try:
        dsn = _resolve_dsn()
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        logger.error("dsn_resolution_failed", error=str(exc))
        sys.exit(1)

    try:
        asyncio.run(run_migrations(dsn))
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        logger.error("migration_failed", error=str(exc))
        sys.exit(1)


if __name__ == "__main__":
    main()
