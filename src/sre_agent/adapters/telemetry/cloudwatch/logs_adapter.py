"""
CloudWatch Logs Adapter — queries AWS CloudWatch Logs via FilterLogEvents API.

Implements LogQuery port for the CloudWatch telemetry stack.

Maps service names to CloudWatch Log Group names and translates
FilterLogEvents / CloudWatch Logs Insights results into CanonicalLogEntry
objects for downstream consumption by the RAG pipeline and LLM.

Implements: Area 3 — CloudWatch Logs Adapter
Validates: AC-CW-2.1 through AC-CW-2.6
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import structlog

from sre_agent.domain.models.canonical import (
    CanonicalLogEntry,
    DataQuality,
    ServiceLabels,
)
from sre_agent.ports.telemetry import LogQuery

logger = structlog.get_logger(__name__)

# Service name → log group pattern resolution
LOG_GROUP_PATTERNS: list[str] = [
    "/aws/lambda/{service}",
    "/ecs/{service}",
    "/aws/ecs/{service}",
]


class CloudWatchLogsAdapter(LogQuery):
    """LogQuery port backed by CloudWatch Logs FilterLogEvents API.

    Resolves service names to CloudWatch Log Group names and queries
    for log events, returning CanonicalLogEntry objects.
    """

    def __init__(
        self,
        logs_client: Any,
        log_group_overrides: dict[str, str] | None = None,
    ) -> None:
        """Initialise with an injected boto3 CloudWatch Logs client.

        Args:
            logs_client: A ``boto3.client("logs")`` instance.
            log_group_overrides: Optional service → log group mapping to
                override the default resolution logic.
        """
        self._client = logs_client
        self._overrides = log_group_overrides or {}
        # Cache of resolved log groups to avoid repeated DescribeLogGroups calls
        self._resolved_groups: dict[str, str | None] = {}

    async def query_logs(
        self,
        service: str,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        severity: str | None = None,
        trace_id: str | None = None,
        search_text: str | None = None,
        limit: int = 1000,
        # aliases used by tests / legacy callers
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[CanonicalLogEntry]:
        """Query CloudWatch Logs for entries matching filters.

        Uses ``FilterLogEvents`` with a filter pattern built from the
        severity, trace_id, and search_text parameters.
        """
        log_group = await self._resolve_log_group(service)
        if log_group is None:
            logger.warning("cloudwatch_logs_no_group", service=service)
            return []

        filter_pattern = self._build_filter(severity, trace_id, search_text)
        effective_start = start_time or start or datetime.now(timezone.utc)
        effective_end = end_time or end or datetime.now(timezone.utc)
        start_ms = int(effective_start.timestamp() * 1000)
        end_ms = int(effective_end.timestamp() * 1000)

        try:
            kwargs: dict[str, Any] = {
                "logGroupName": log_group,
                "startTime": start_ms,
                "endTime": end_ms,
                "limit": min(limit, 10000),
                "interleaved": True,
            }
            if filter_pattern:
                kwargs["filterPattern"] = filter_pattern

            response = self._client.filter_log_events(**kwargs)
        except Exception as exc:
            logger.error(
                "cloudwatch_logs_query_failed",
                log_group=log_group,
                error=str(exc),
            )
            return []

        return self._parse_events(response.get("events", []), service)

    async def query_by_trace_id(
        self,
        trace_id: str,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        service: str | None = None,
    ) -> list[CanonicalLogEntry]:
        """Retrieve log entries correlated with a trace ID.

        Searches across all known log groups for the trace ID string.
        This is a broad search — use with a constrained time window.
        """
        all_entries: list[CanonicalLogEntry] = []

        # If a specific service is requested, resolve its group and search there first
        if service is not None and service not in self._resolved_groups:
            await self._resolve_log_group(service)

        # Search in all resolved log groups
        for service, group in self._resolved_groups.items():
            if group is None:
                continue

            start_ms = int(start_time.timestamp() * 1000) if start_time else None
            end_ms = int(end_time.timestamp() * 1000) if end_time else None

            try:
                kwargs: dict[str, Any] = {
                    "logGroupName": group,
                    "filterPattern": f'"{trace_id}"',
                    "limit": 500,
                    "interleaved": True,
                }
                if start_ms is not None:
                    kwargs["startTime"] = start_ms
                if end_ms is not None:
                    kwargs["endTime"] = end_ms

                response = self._client.filter_log_events(**kwargs)
                all_entries.extend(
                    self._parse_events(response.get("events", []), service)
                )
            except Exception as exc:
                logger.warning(
                    "cloudwatch_logs_trace_query_failed",
                    log_group=group,
                    trace_id=trace_id,
                    error=str(exc),
                )

        return all_entries

    async def health_check(self) -> bool:
        """Check CloudWatch Logs is reachable."""
        try:
            self._client.describe_log_groups(limit=1)
            return True
        except Exception as exc:
            logger.warning("cloudwatch_logs_health_check_failed", error=str(exc))
            return False

    async def close(self) -> None:
        """No-op — boto3 clients do not require explicit closure."""

    # -------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------

    async def _resolve_log_group(self, service: str) -> str | None:
        """Resolve a service name to a CloudWatch Log Group name.

        Priority:
        1. Explicit override mapping
        2. Check known patterns against DescribeLogGroups
        3. Cache the result
        """
        if service in self._resolved_groups:
            return self._resolved_groups[service]

        # Check overrides first
        if service in self._overrides:
            group = self._overrides[service]
            self._resolved_groups[service] = group
            return group

        # Try known patterns
        for pattern in LOG_GROUP_PATTERNS:
            candidate = pattern.format(service=service)
            try:
                response = self._client.describe_log_groups(
                    logGroupNamePrefix=candidate,
                    limit=1,
                )
                groups = response.get("logGroups", [])
                if groups:
                    resolved = groups[0]["logGroupName"]
                    self._resolved_groups[service] = resolved
                    logger.debug(
                        "cloudwatch_logs_group_resolved",
                        service=service,
                        log_group=resolved,
                    )
                    return resolved
            except Exception:
                continue

        # Fallback: use the Lambda pattern directly (most common)
        fallback = f"/aws/lambda/{service}"
        self._resolved_groups[service] = fallback
        return fallback

    def _build_filter(
        self,
        severity: str | None = None,
        trace_id: str | None = None,
        search_text: str | None = None,
    ) -> str:
        """Build a CloudWatch Logs filter pattern.

        CloudWatch filter pattern syntax is different from LogQL.
        Uses simple string matching with quoted terms.
        """
        parts: list[str] = []

        if severity:
            parts.append(f'"{severity.upper()}"')
        if trace_id:
            parts.append(f'"{trace_id}"')
        if search_text:
            parts.append(f'"{search_text}"')

        return " ".join(parts) if parts else ""

    def _parse_events(
        self,
        events: list[dict[str, Any]],
        service: str,
    ) -> list[CanonicalLogEntry]:
        """Parse CloudWatch log events into CanonicalLogEntry objects."""
        entries: list[CanonicalLogEntry] = []

        for event in events:
            try:
                timestamp_ms = event.get("timestamp", 0)
                ts = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
                message = event.get("message", "")

                # Attempt to parse JSON-structured log messages
                severity = "INFO"
                trace_id = None
                span_id = None
                attributes: dict[str, Any] = {}

                try:
                    parsed = json.loads(message)
                    if isinstance(parsed, dict):
                        severity = str(
                            parsed.get("level", parsed.get("severity", "INFO"))
                        ).upper()
                        trace_id = parsed.get("trace_id", parsed.get("traceId"))
                        span_id = parsed.get("span_id", parsed.get("spanId"))
                        # Preserve the original message for LLM context
                        message = parsed.get("message", message)
                        attributes = {
                            k: v
                            for k, v in parsed.items()
                            if k not in {"level", "severity", "message",
                                         "trace_id", "traceId", "span_id", "spanId",
                                         "timestamp"}
                        }
                except (json.JSONDecodeError, TypeError):
                    # Plain text log — infer severity from content
                    severity = self._infer_severity(message)

                entries.append(
                    CanonicalLogEntry(
                        timestamp=ts,
                        message=message,
                        severity=severity,
                        labels=ServiceLabels(service=service),
                        trace_id=trace_id,
                        span_id=span_id,
                        attributes=attributes,
                        quality=DataQuality.HIGH,
                        provider_source="cloudwatch",
                        ingestion_timestamp=datetime.now(timezone.utc),
                    )
                )
            except Exception as exc:
                logger.warning("cloudwatch_logs_parse_failed", error=str(exc))

        return entries

    def _infer_severity(self, message: str) -> str:
        """Infer log severity from message content when not structured."""
        upper = message.upper()
        if "CRITICAL" in upper or "FATAL" in upper:
            return "CRITICAL"
        if "ERROR" in upper or "EXCEPTION" in upper or "TRACEBACK" in upper:
            return "ERROR"
        if "WARN" in upper:
            return "WARNING"
        if "DEBUG" in upper:
            return "DEBUG"
        return "INFO"
