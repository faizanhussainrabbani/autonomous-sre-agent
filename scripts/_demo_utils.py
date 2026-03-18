"""Shared utility helpers for live demo scripts."""

from __future__ import annotations

import os
from typing import Any


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def aws_region(default: str = "us-east-1") -> str:
    return os.getenv("AWS_DEFAULT_REGION", default)


def boto_localstack_kwargs(endpoint: str, region: str | None = None) -> dict[str, Any]:
    return {
        "endpoint_url": endpoint,
        "region_name": region or aws_region(),
        "aws_access_key_id": "test",
        "aws_secret_access_key": "test",
    }


def pause_if_interactive(skip_pauses: bool, prompt: str = "Press ENTER to continue...") -> None:
    if skip_pauses:
        print()
        return
    input(f"\n{prompt}\n")
