"""CloudWatch log-group resolver shared across adapters.

Provides a single implementation for mapping service names to CloudWatch
log groups with deterministic resolution order and caching.
"""

from __future__ import annotations

from typing import Any

# Service name -> log group pattern resolution
LOG_GROUP_PATTERNS: list[str] = [
    "/aws/lambda/{service}",
    "/ecs/{service}",
    "/aws/ecs/{service}",
]


class CloudWatchLogGroupResolver:
    """Resolve service names to CloudWatch log group names.

    Resolution order:
    1. Explicit override mapping
    2. Pattern-based discovery via DescribeLogGroups
    3. Lambda fallback convention
    """

    def __init__(
        self,
        logs_client: Any,
        overrides: dict[str, str] | None = None,
        patterns: list[str] | None = None,
    ) -> None:
        self._client = logs_client
        self._overrides = overrides or {}
        self._patterns = patterns or list(LOG_GROUP_PATTERNS)
        self._resolved_groups: dict[str, str | None] = {}

    @property
    def resolved_groups(self) -> dict[str, str | None]:
        """Expose cache for read-only consumers that need iteration."""
        return self._resolved_groups

    async def resolve(self, service: str) -> str:
        """Resolve and cache a log-group name for the given service."""
        if service in self._resolved_groups:
            cached = self._resolved_groups[service]
            if cached is not None:
                return cached

        if service in self._overrides:
            group = self._overrides[service]
            self._resolved_groups[service] = group
            return group

        for pattern in self._patterns:
            candidate = pattern.format(service=service)
            try:
                response = self._client.describe_log_groups(
                    logGroupNamePrefix=candidate,
                    limit=1,
                )
            except Exception:  # noqa: BLE001
                continue

            groups = response.get("logGroups", [])
            if groups:
                resolved = groups[0]["logGroupName"]
                self._resolved_groups[service] = resolved
                return resolved

        fallback = f"/aws/lambda/{service}"
        self._resolved_groups[service] = fallback
        return fallback
