"""Canonical PostgreSQL configuration for local persistence flows."""

from __future__ import annotations

EXPECTED_POSTGRES_USER = "test"
EXPECTED_POSTGRES_PASSWORD = "test"
EXPECTED_POSTGRES_HOST = "localhost"
EXPECTED_POSTGRES_PORT = 5434
EXPECTED_POSTGRES_DB = "sre_demo"
EXPECTED_POSTGRES_DSN = (
    f"postgresql://{EXPECTED_POSTGRES_USER}:{EXPECTED_POSTGRES_PASSWORD}"
    f"@{EXPECTED_POSTGRES_HOST}:{EXPECTED_POSTGRES_PORT}/{EXPECTED_POSTGRES_DB}"
)


def normalize_postgres_dsn(dsn: str) -> str:
    """Normalize SQLAlchemy-style Postgres URLs to the canonical scheme."""
    return dsn.strip().replace("postgresql+psycopg2://", "postgresql://", 1)


def ensure_expected_postgres_dsn(dsn: str, *, context: str = "PostgreSQL") -> str:
    """Validate that a DSN matches the canonical local demo database."""
    normalized = normalize_postgres_dsn(dsn)
    if normalized != EXPECTED_POSTGRES_DSN:
        raise ValueError(
            f"{context} must use {EXPECTED_POSTGRES_DSN}; got {normalized or '<empty>'}"
        )
    return normalized