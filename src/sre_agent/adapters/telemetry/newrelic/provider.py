"""
New Relic NerdGraph Adapter — queries New Relic via the NerdGraph GraphQL API.

Implements all four telemetry query ports (MetricsQuery, TraceQuery, LogQuery,
DependencyGraphQuery) for organizations using New Relic as their telemetry backend.

Implements: Task 13.4 — New Relic adapter
Validates: AC-1.4.1 through AC-1.4.4
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx
import structlog

from sre_agent.domain.models.canonical import (
    CanonicalLogEntry,
    CanonicalMetric,
    CanonicalTrace,
    DataQuality,
    ServiceEdge,
    ServiceGraph,
    ServiceLabels,
    ServiceNode,
    TraceSpan,
)
from sre_agent.ports.telemetry import (
    DependencyGraphQuery,
    LogQuery,
    MetricsQuery,
    TelemetryProvider,
    TraceQuery,
)
from sre_agent.config.settings import NewRelicConfig

logger = structlog.get_logger(__name__)


class NerdGraphClient:
    """Low-level client for New Relic NerdGraph GraphQL API.

    Shared by all New Relic query adapters. Handles authentication
    and request formatting.
    """

    def __init__(
        self,
        api_key: str,
        account_id: str,
        nerdgraph_url: str = "https://api.newrelic.com/graphql",
        timeout: float = 15.0,
    ) -> None:
        self._account_id = account_id
        self._client = httpx.AsyncClient(
            base_url=nerdgraph_url,
            headers={
                "Content-Type": "application/json",
                "API-Key": api_key,
            },
            timeout=timeout,
        )

    async def query(self, nrql: str) -> list[dict[str, Any]]:
        """Execute a NRQL query via NerdGraph and return results."""
        graphql_query = {
            "query": """
            {
                actor {
                    account(id: %s) {
                        nrql(query: "%s") {
                            results
                        }
                    }
                }
            }
            """ % (self._account_id, nrql.replace('"', '\\"'))
        }

        try:
            response = await self._client.post("", json=graphql_query)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as exc:
            logger.error("nerdgraph_query_failed", nrql=nrql, error=str(exc))
            return []

        try:
            return data["data"]["actor"]["account"]["nrql"]["results"]
        except (KeyError, TypeError):
            logger.warning("nerdgraph_unexpected_response", data=data)
            return []

    async def graphql(self, query: str, variables: dict | None = None) -> dict[str, Any]:
        """Execute a raw GraphQL query."""
        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables

        try:
            response = await self._client.post("", json=payload)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as exc:
            logger.error("nerdgraph_graphql_failed", error=str(exc))
            return {}

    async def health_check(self) -> bool:
        """Verify API key and account access."""
        data = await self.graphql("{ actor { user { name } } }")
        return bool(data.get("data", {}).get("actor", {}).get("user"))

    async def close(self) -> None:
        await self._client.aclose()


# ---------------------------------------------------------------------------
# Metrics Adapter
# ---------------------------------------------------------------------------

class NewRelicMetricsAdapter(MetricsQuery):
    """Queries New Relic metrics via NRQL and returns canonical metrics.

    Validates: AC-1.4.1
    """

    def __init__(self, client: NerdGraphClient) -> None:
        self._client = client

    async def query(
        self,
        service: str,
        metric: str,
        start_time: datetime,
        end_time: datetime,
        labels: dict[str, str] | None = None,
        step_seconds: int = 15,
    ) -> list[CanonicalMetric]:
        duration_secs = int((end_time - start_time).total_seconds())
        nrql = (
            f"SELECT average({metric}) FROM Metric "
            f"WHERE service.name = '{service}' "
            f"SINCE {duration_secs} seconds ago "
            f"TIMESERIES {step_seconds} seconds"
        )

        results = await self._client.query(nrql)
        return self._parse_timeseries(results, service, metric)

    async def query_instant(
        self,
        service: str,
        metric: str,
        timestamp: datetime | None = None,
        labels: dict[str, str] | None = None,
    ) -> CanonicalMetric | None:
        nrql = (
            f"SELECT latest({metric}) FROM Metric "
            f"WHERE service.name = '{service}' SINCE 1 minute ago"
        )

        results = await self._client.query(nrql)
        if not results:
            return None

        value = results[0].get(f"latest.{metric}", results[0].get("latest", 0))
        return CanonicalMetric(
            name=metric,
            value=float(value) if value else 0.0,
            timestamp=datetime.now(timezone.utc),
            labels=ServiceLabels(service=service, namespace=""),
            provider_source="newrelic",
            ingestion_timestamp=datetime.now(timezone.utc),
        )

    async def list_metrics(self, service: str) -> list[str]:
        nrql = (
            f"SELECT uniques(metricName) FROM Metric "
            f"WHERE service.name = '{service}' SINCE 1 hour ago LIMIT MAX"
        )
        results = await self._client.query(nrql)
        if results:
            return results[0].get("uniques.metricName", [])
        return []

    def _parse_timeseries(
        self, results: list[dict], service: str, metric: str
    ) -> list[CanonicalMetric]:
        metrics: list[CanonicalMetric] = []
        for point in results:
            begin_time = point.get("beginTimeSeconds", 0)
            value = point.get(f"average.{metric}", point.get("average", 0))

            if begin_time and value is not None:
                metrics.append(
                    CanonicalMetric(
                        name=metric,
                        value=float(value),
                        timestamp=datetime.fromtimestamp(begin_time, tz=timezone.utc),
                        labels=ServiceLabels(service=service, namespace=""),
                        provider_source="newrelic",
                        ingestion_timestamp=datetime.now(timezone.utc),
                    )
                )
        return metrics


# ---------------------------------------------------------------------------
# Trace Adapter
# ---------------------------------------------------------------------------

class NewRelicTraceAdapter(TraceQuery):
    """Queries New Relic distributed traces via NerdGraph.

    Validates: AC-1.4.2
    """

    def __init__(self, client: NerdGraphClient) -> None:
        self._client = client

    async def get_trace(self, trace_id: str) -> CanonicalTrace | None:
        nrql = (
            f"SELECT * FROM Span "
            f"WHERE trace.id = '{trace_id}' SINCE 1 day ago LIMIT MAX"
        )
        results = await self._client.query(nrql)
        if not results:
            return None

        return self._parse_spans_to_trace(trace_id, results)

    async def query_traces(
        self,
        service: str,
        start_time: datetime,
        end_time: datetime,
        limit: int = 100,
        min_duration_ms: float | None = None,
        status_code: int | None = None,
    ) -> list[CanonicalTrace]:
        duration_secs = int((end_time - start_time).total_seconds())
        where_clauses = [f"service.name = '{service}'"]
        if min_duration_ms:
            where_clauses.append(f"duration.ms > {min_duration_ms}")
        if status_code:
            where_clauses.append(f"http.statusCode = {status_code}")

        where = " AND ".join(where_clauses)
        nrql = (
            f"SELECT uniques(trace.id) FROM Span "
            f"WHERE {where} SINCE {duration_secs} seconds ago LIMIT {limit}"
        )

        results = await self._client.query(nrql)
        trace_ids = results[0].get("uniques.trace.id", []) if results else []

        traces = []
        for tid in trace_ids[:limit]:
            trace = await self.get_trace(tid)
            if trace:
                traces.append(trace)
        return traces

    def _parse_spans_to_trace(
        self, trace_id: str, span_data: list[dict]
    ) -> CanonicalTrace:
        spans: list[TraceSpan] = []
        for sd in span_data:
            parent_id = sd.get("parent.id") or sd.get("parentId")
            spans.append(
                TraceSpan(
                    span_id=sd.get("id", sd.get("span.id", "")),
                    parent_span_id=parent_id if parent_id else None,
                    service=sd.get("service.name", sd.get("entity.name", "unknown")),
                    operation=sd.get("name", ""),
                    duration_ms=float(sd.get("duration.ms", sd.get("duration", 0))),
                    status_code=int(sd.get("http.statusCode", 200)),
                    error=sd.get("error.message"),
                    attributes={
                        k: v for k, v in sd.items()
                        if k not in {
                            "id", "span.id", "parent.id", "parentId",
                            "service.name", "entity.name", "name",
                            "duration.ms", "duration", "http.statusCode",
                            "error.message", "trace.id", "timestamp",
                        }
                    },
                )
            )

        # Assess completeness (AC-2.6.3)
        is_complete = True
        missing_services: list[str] = []
        span_ids = {s.span_id for s in spans}
        for s in spans:
            if s.parent_span_id and s.parent_span_id not in span_ids:
                is_complete = False
                missing_services.append(f"unknown (parent_span={s.parent_span_id})")
        root_spans = [s for s in spans if s.parent_span_id is None]
        if len(root_spans) == 0 and spans:
            is_complete = False

        if not is_complete:
            logger.info(
                "incomplete_trace_detected",
                trace_id=trace_id,
                total_spans=len(spans),
                missing_services=missing_services,
            )

        return CanonicalTrace(
            trace_id=trace_id,
            spans=spans,
            is_complete=is_complete,
            missing_services=missing_services,
            quality=DataQuality.HIGH if is_complete else DataQuality.INCOMPLETE,
            provider_source="newrelic",
            ingestion_timestamp=datetime.now(timezone.utc),
        )


# ---------------------------------------------------------------------------
# Log Adapter
# ---------------------------------------------------------------------------

class NewRelicLogAdapter(LogQuery):
    """Queries New Relic logs via NRQL.

    Validates: AC-1.4.3
    """

    def __init__(self, client: NerdGraphClient) -> None:
        self._client = client

    async def query_logs(
        self,
        service: str,
        start_time: datetime,
        end_time: datetime,
        severity: str | None = None,
        trace_id: str | None = None,
        search_text: str | None = None,
        limit: int = 1000,
    ) -> list[CanonicalLogEntry]:
        duration_secs = int((end_time - start_time).total_seconds())
        where_clauses = [f"service.name = '{service}'"]
        if severity:
            where_clauses.append(f"level = '{severity.lower()}'")
        if trace_id:
            where_clauses.append(f"trace.id = '{trace_id}'")
        if search_text:
            where_clauses.append(f"message LIKE '%{search_text}%'")

        where = " AND ".join(where_clauses)
        nrql = (
            f"SELECT timestamp, message, level, trace.id, span.id "
            f"FROM Log WHERE {where} "
            f"SINCE {duration_secs} seconds ago LIMIT {limit}"
        )

        results = await self._client.query(nrql)
        return self._parse_logs(results, service)

    async def query_by_trace_id(
        self,
        trace_id: str,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[CanonicalLogEntry]:
        nrql = (
            f"SELECT timestamp, message, level, service.name, span.id "
            f"FROM Log WHERE trace.id = '{trace_id}' SINCE 1 day ago LIMIT MAX"
        )
        results = await self._client.query(nrql)
        return self._parse_logs(results, "")

    def _parse_logs(
        self, results: list[dict], default_service: str
    ) -> list[CanonicalLogEntry]:
        entries: list[CanonicalLogEntry] = []
        for r in results:
            ts_val = r.get("timestamp")
            if ts_val:
                try:
                    ts = datetime.fromtimestamp(ts_val / 1000, tz=timezone.utc)
                except (ValueError, TypeError):
                    ts = datetime.now(timezone.utc)
            else:
                ts = datetime.now(timezone.utc)

            entries.append(
                CanonicalLogEntry(
                    timestamp=ts,
                    message=str(r.get("message", "")),
                    severity=(r.get("level") or "INFO").upper(),
                    labels=ServiceLabels(
                        service=r.get("service.name", default_service),
                        namespace="",
                    ),
                    trace_id=r.get("trace.id"),
                    span_id=r.get("span.id"),
                    provider_source="newrelic",
                    ingestion_timestamp=datetime.now(timezone.utc),
                )
            )
        return entries


# ---------------------------------------------------------------------------
# Dependency Graph Adapter
# ---------------------------------------------------------------------------

class NewRelicDependencyGraphAdapter(DependencyGraphQuery):
    """Builds dependency graph from New Relic Service Maps API.

    Validates: AC-1.4.4
    """

    def __init__(self, client: NerdGraphClient) -> None:
        self._client = client

    async def get_graph(self) -> ServiceGraph:
        query = """
        {
            actor {
                entitySearch(query: "type = 'APPLICATION'") {
                    results {
                        entities {
                            name
                            relationships {
                                target { entity { name } }
                                type
                            }
                        }
                    }
                }
            }
        }
        """
        data = await self._client.graphql(query)

        graph = ServiceGraph()
        try:
            entities = (
                data.get("data", {})
                .get("actor", {})
                .get("entitySearch", {})
                .get("results", {})
                .get("entities", [])
            )
        except (KeyError, AttributeError):
            return graph

        for entity in entities:
            name = entity.get("name", "")
            if name:
                graph.nodes[name] = ServiceNode(service=name, namespace="")
                for rel in entity.get("relationships", []):
                    target_name = (
                        rel.get("target", {}).get("entity", {}).get("name", "")
                    )
                    if target_name and rel.get("type") == "CALLS":
                        graph.edges.append(
                            ServiceEdge(source=name, target=target_name)
                        )
                        if target_name not in graph.nodes:
                            graph.nodes[target_name] = ServiceNode(
                                service=target_name, namespace=""
                            )

        graph.last_updated = datetime.now(timezone.utc)
        return graph

    async def get_service_dependencies(self, service, include_transitive=False):
        full_graph = await self.get_graph()
        if include_transitive:
            downstream = full_graph.get_transitive_downstream(service)
            upstream_set = set(full_graph.get_upstream(service))
            relevant = downstream | upstream_set | {service}
        else:
            downstream_set = set(full_graph.get_downstream(service))
            upstream_set = set(full_graph.get_upstream(service))
            relevant = downstream_set | upstream_set | {service}

        sub_graph = ServiceGraph(
            nodes={k: v for k, v in full_graph.nodes.items() if k in relevant},
            edges=[
                e for e in full_graph.edges
                if e.source in relevant and e.target in relevant
            ],
            last_updated=full_graph.last_updated,
        )
        return sub_graph

    async def get_service_health(self, service):
        nrql = (
            f"SELECT average(duration), percentage(count(*), WHERE error IS true) "
            f"FROM Transaction WHERE appName = '{service}' SINCE 5 minutes ago"
        )
        results = await self._client.query(nrql)
        if results:
            return {
                "is_healthy": True,
                "avg_latency_ms": results[0].get("average.duration", 0) * 1000,
                "error_rate": results[0].get("percentage", 0),
                "source": "newrelic",
            }
        return {"is_healthy": True, "source": "newrelic"}


# ---------------------------------------------------------------------------
# Composite Provider
# ---------------------------------------------------------------------------

class NewRelicProvider(TelemetryProvider):
    """Composite New Relic provider using NerdGraph for all queries.

    Validates: AC-1.4.1 through AC-1.4.4
    """

    def __init__(self, config: NewRelicConfig, api_key: str) -> None:
        self._client = NerdGraphClient(
            api_key=api_key,
            account_id=config.account_id,
            nerdgraph_url=config.nerdgraph_url,
        )
        self._metrics = NewRelicMetricsAdapter(self._client)
        self._traces = NewRelicTraceAdapter(self._client)
        self._logs = NewRelicLogAdapter(self._client)
        self._dep_graph = NewRelicDependencyGraphAdapter(self._client)

    @property
    def name(self) -> str:
        return "newrelic"

    @property
    def metrics(self) -> MetricsQuery:
        return self._metrics

    @property
    def traces(self) -> TraceQuery:
        return self._traces

    @property
    def logs(self) -> LogQuery:
        return self._logs

    @property
    def dependency_graph(self) -> DependencyGraphQuery:
        return self._dep_graph

    async def health_check(self) -> bool:
        return await self._client.health_check()

    async def close(self) -> None:
        await self._client.close()
        logger.info("newrelic_provider_closed")
