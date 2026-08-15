from __future__ import annotations

import pytest

from sre_agent.config.postgres import (
    EXPECTED_POSTGRES_DSN,
    ensure_expected_postgres_dsn,
    normalize_postgres_dsn,
)


def test_normalize_postgres_dsn_strips_sqlalchemy_scheme() -> None:
    assert normalize_postgres_dsn(
        "postgresql+psycopg2://test:test@localhost:5434/sre_demo"
    ) == EXPECTED_POSTGRES_DSN


def test_ensure_expected_postgres_dsn_rejects_non_canonical_target() -> None:
    with pytest.raises(ValueError, match="5434/sre_demo"):
        ensure_expected_postgres_dsn("postgresql://test:test@localhost:5432/sre_agent")