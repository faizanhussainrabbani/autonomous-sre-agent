"""
Application Bootstrap — wire adapters to domain via plugin registry.

This is the ONLY place where adapter implementations are imported and
connected to the domain layer. It lives in the adapters layer, not
in domain or config, per hexagonal architecture (§1.1).

This module is called at application startup (e.g., from main.py).
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import structlog

from sre_agent.adapters.coordination.in_memory_lock_manager import InMemoryDistributedLockManager
from sre_agent.config.plugin import ProviderPlugin
from sre_agent.config.settings import AgentConfig, LockBackendType
from sre_agent.domain.detection.provider_registry import ProviderRegistry
from sre_agent.ports.lock_manager import DistributedLockManagerPort
from sre_agent.ports.telemetry import LogQuery, TelemetryProvider

if TYPE_CHECKING:
    from sre_agent.domain.detection.cloud_operator_registry import CloudOperatorRegistry
    from sre_agent.ports.events import EventBus, EventStore
    from sre_agent.ports.persistence import (
        CoordinationAuditPort,
        DiagnosisStorePort,
        IncidentStorePort,
        OutboxPort,
        ReasoningTracePort,
        RemediationStorePort,
    )
    from sre_agent.ports.telemetry import eBPFQuery
    from sre_agent.ports.vector_store import VectorStorePort

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Built-in provider factories (adapter layer — OK to import adapters here)
# ---------------------------------------------------------------------------


def _otel_factory(config: AgentConfig) -> TelemetryProvider:
    """Factory for the OTel provider (Prometheus + Jaeger + Loki)."""
    from sre_agent.adapters.telemetry.otel.provider import OTelProvider

    logs_adapter = _build_otel_log_adapter(config)
    return OTelProvider(config.otel, logs_adapter=logs_adapter)


def _build_otel_log_adapter(config: AgentConfig) -> LogQuery:
    """Build OTel log adapter chain with optional Kubernetes fallback.

    The primary path stays Loki. When the Kubernetes client and kube config
    are available, compose Loki with Kubernetes API fallback through the
    FallbackLogAdapter decorator.
    """
    from sre_agent.adapters.telemetry.otel.loki_adapter import LokiLogAdapter

    primary = LokiLogAdapter(config.otel.loki_url)
    fallback = _maybe_build_kubernetes_log_adapter()

    if fallback is None:
        return primary

    from sre_agent.adapters.telemetry.fallback_log_adapter import FallbackLogAdapter

    logger.info("otel_logs_fallback_enabled", primary="loki", fallback="kubernetes_api")
    return FallbackLogAdapter(
        primary=primary,
        fallback=fallback,
        primary_name="loki",
        fallback_name="kubernetes_api",
    )


def _maybe_build_kubernetes_log_adapter() -> LogQuery | None:
    """Create Kubernetes log adapter when client + config are available."""
    try:
        from kubernetes import client as k8s_client
        from kubernetes import config as k8s_config
    except ImportError:
        logger.debug(
            "kubernetes_log_fallback_unavailable",
            reason="kubernetes client not installed",
        )
        return None

    try:
        k8s_config.load_incluster_config()
    except Exception:  # noqa: BLE001
        try:
            k8s_config.load_kube_config()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "kubernetes_log_fallback_unavailable",
                reason="kube configuration unavailable",
                error=str(exc),
            )
            return None

    from sre_agent.adapters.telemetry.kubernetes.pod_log_adapter import KubernetesLogAdapter

    namespace = os.getenv("KUBERNETES_NAMESPACE", "default")
    return KubernetesLogAdapter(core_v1_api=k8s_client.CoreV1Api(), namespace=namespace)


def _newrelic_factory(config: AgentConfig) -> TelemetryProvider:
    """Factory for the New Relic provider.

    Note: API key must be resolved from secrets manager before calling this.
    For now, uses a placeholder — real secrets integration in cloud-portability.
    """
    from sre_agent.adapters.telemetry.newrelic.provider import NewRelicProvider

    # In production, api_key comes from secrets manager (AWS SM, Azure KV, Vault)
    api_key = ""  # Placeholder — resolved at runtime
    return NewRelicProvider(config.newrelic, api_key=api_key)


def _cloudwatch_factory(config: AgentConfig) -> TelemetryProvider:
    """Factory for the CloudWatch provider (Metrics + Logs + X-Ray).

    Uses lazy imports: ``boto3`` is imported only when this factory
    is called, so non-AWS environments can import bootstrap.py
    without triggering an ImportError.
    """
    import boto3

    from sre_agent.adapters.telemetry.cloudwatch.provider import CloudWatchProvider

    cw = config.cloudwatch
    kwargs: dict[str, str] = {}
    if cw.endpoint_url:
        kwargs["endpoint_url"] = cw.endpoint_url
    return CloudWatchProvider(
        cloudwatch_client=boto3.client("cloudwatch", region_name=cw.region, **kwargs),
        logs_client=boto3.client("logs", region_name=cw.region, **kwargs),
        xray_client=boto3.client("xray", region_name=cw.region, **kwargs),
        region=cw.region,
    )


def _create_pixie_adapter(config: AgentConfig) -> eBPFQuery:
    """Factory for the Pixie eBPF adapter (optional — kernel telemetry).

    Returns an eBPFQuery implementation. This is separate from the
    TelemetryProvider since eBPF is supplementary to the primary
    metrics/traces/logs provider.
    """
    from sre_agent.adapters.telemetry.ebpf.pixie_adapter import PixieAdapter

    return PixieAdapter(
        api_url=getattr(config, "pixie_api_url", "https://work.withpixie.ai"),
        cluster_id=getattr(config, "pixie_cluster_id", ""),
        api_key=getattr(config, "pixie_api_key", ""),
    )


def register_builtin_providers() -> None:
    """Register the built-in OTel, New Relic, and CloudWatch provider factories."""
    ProviderPlugin.register("otel", _otel_factory)
    ProviderPlugin.register("newrelic", _newrelic_factory)
    ProviderPlugin.register("cloudwatch", _cloudwatch_factory)


async def bootstrap_provider(
    config: AgentConfig,
    registry: ProviderRegistry,
) -> TelemetryProvider:
    """Bootstrap the telemetry provider from configuration.

    1. Register built-in providers
    2. Create the configured provider via plugin system
    3. Register and activate it in the provider registry

    Returns:
        The activated TelemetryProvider instance.
    """
    register_builtin_providers()

    provider_name = config.telemetry_provider.value
    logger.info("bootstrapping_provider", provider=provider_name)

    try:
        provider = ProviderPlugin.create_provider(provider_name, config)
        registry.register(provider)
        await registry.activate(provider_name)
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "provider_bootstrap_failed",
            provider=provider_name,
            available=ProviderPlugin.available_providers(),
            error=str(exc),
        )
        raise

    logger.info(
        "provider_bootstrapped",
        provider=provider_name,
        available=ProviderPlugin.available_providers(),
    )
    return provider


# ---------------------------------------------------------------------------
# Phase 1.5 — Cloud operator bootstrap
# ---------------------------------------------------------------------------


def bootstrap_cloud_operators(config: AgentConfig) -> CloudOperatorRegistry:
    """Bootstrap cloud remediation operators based on available SDKs.

    Returns a CloudOperatorRegistry with registered operators for any
    cloud SDKs that are importable.
    """
    from sre_agent.domain.detection.cloud_operator_registry import CloudOperatorRegistry

    registry = CloudOperatorRegistry()

    # Kubernetes operator (requires kubernetes client)
    try:
        from kubernetes import client as _k8s_client  # noqa: F401

        from sre_agent.adapters.cloud.kubernetes.operator import KubernetesOperator

        registry.register(KubernetesOperator())
        logger.info("kubernetes_operator_bootstrapped")
    except ImportError:
        logger.debug("kubernetes_operator_skipped", reason="kubernetes client not installed")

    # AWS operators (requires boto3)
    try:
        import boto3  # noqa: F401

        from sre_agent.adapters.cloud.aws.ec2_asg_operator import EC2ASGOperator
        from sre_agent.adapters.cloud.aws.ecs_operator import ECSOperator
        from sre_agent.adapters.cloud.aws.lambda_operator import LambdaOperator

        region = getattr(config, "aws_region", "us-east-1")
        registry.register(ECSOperator(boto3.client("ecs", region_name=region)))
        registry.register(EC2ASGOperator(boto3.client("autoscaling", region_name=region)))
        registry.register(LambdaOperator(boto3.client("lambda", region_name=region)))
        logger.info("aws_operators_bootstrapped", region=region)
    except ImportError:
        logger.debug("aws_operators_skipped", reason="boto3 not installed")

    # Azure operators (requires azure-mgmt-web)
    try:
        from azure.identity import DefaultAzureCredential  # noqa: F401
        from azure.mgmt.web import WebSiteManagementClient  # noqa: F401

        from sre_agent.adapters.cloud.azure.app_service_operator import AppServiceOperator
        from sre_agent.adapters.cloud.azure.functions_operator import FunctionsOperator

        sub_id = getattr(config, "azure_subscription_id", "")
        credential = DefaultAzureCredential()
        web_client = WebSiteManagementClient(credential, sub_id)
        registry.register(AppServiceOperator(web_client))
        registry.register(FunctionsOperator(web_client))
        logger.info("azure_operators_bootstrapped", subscription=sub_id)
    except ImportError:
        logger.debug("azure_operators_skipped", reason="azure-mgmt-web not installed")

    return registry


async def bootstrap_coordination_audit(
    pool: object | None,
) -> CoordinationAuditPort | None:
    """Bootstrap the coordination audit store using the shared connection pool.

    Returns None when pool is None (persistence disabled / local dev mode).

    Args:
        pool: Shared asyncpg pool from bootstrap_asyncpg_pool().
    """
    if pool is None:
        logger.info("coordination_audit_disabled", reason="no database pool")
        return None

    try:
        from sre_agent.adapters.persistence.coordination_store import (
            PostgresCoordinationAuditStore,
        )

        logger.info("coordination_audit_bootstrapped")
        return PostgresCoordinationAuditStore(pool=pool)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "coordination_audit_bootstrap_failed",
            error=str(exc),
            fallback="disabled",
        )
        return None


def bootstrap_lock_manager(
    config: AgentConfig,
    audit: CoordinationAuditPort | None = None,
) -> DistributedLockManagerPort:
    """Bootstrap lock manager backend based on configuration."""
    backend = config.lock.backend

    if backend == LockBackendType.REDIS:
        try:
            from sre_agent.adapters.coordination.redis_lock_manager import (
                RedisDistributedLockManager,
                RedisLockConfig,
            )

            logger.info(
                "lock_manager_bootstrapped",
                backend="redis",
                audit_enabled=audit is not None,
            )
            return RedisDistributedLockManager(
                config=RedisLockConfig(
                    url=config.lock.redis_url,
                    key_prefix=config.lock.key_prefix,
                ),
                audit=audit,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "lock_manager_backend_failed",
                backend="redis",
                error=str(exc),
                fallback="in_memory",
            )

    if backend == LockBackendType.ETCD:
        try:
            from sre_agent.adapters.coordination.etcd_lock_manager import (
                EtcdDistributedLockManager,
                EtcdLockConfig,
            )

            logger.info(
                "lock_manager_bootstrapped",
                backend="etcd",
                audit_enabled=audit is not None,
            )
            return EtcdDistributedLockManager(
                config=EtcdLockConfig(
                    host=config.lock.etcd_host,
                    port=config.lock.etcd_port,
                    key_prefix=config.lock.key_prefix,
                ),
                audit=audit,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "lock_manager_backend_failed",
                backend="etcd",
                error=str(exc),
                fallback="in_memory",
            )

    logger.info("lock_manager_bootstrapped", backend="in_memory", audit_enabled=audit is not None)
    return InMemoryDistributedLockManager(audit=audit)


# ---------------------------------------------------------------------------
# Phase 4.0 — Persistence adapter bootstrap
# ---------------------------------------------------------------------------


async def bootstrap_asyncpg_pool(config: AgentConfig) -> object | None:
    """Create and return a shared asyncpg connection pool.

    Returns None when persistence is disabled or asyncpg is unavailable.
    The pool is shared across IncidentStore, OutboxStore, and VectorStore adapters.
    """
    if not config.persistence.enabled or not config.persistence.postgres_dsn:
        logger.info("asyncpg_pool_skipped", reason="persistence not configured")
        return None

    try:
        import asyncpg  # type: ignore[import]

        pool = await asyncpg.create_pool(
            dsn=config.persistence.postgres_dsn,
            min_size=config.persistence.pool_min_size,
            max_size=config.persistence.pool_max_size,
        )
        logger.info(
            "asyncpg_pool_created",
            pool_min=config.persistence.pool_min_size,
            pool_max=config.persistence.pool_max_size,
        )
        return pool
    except Exception as exc:  # noqa: BLE001
        logger.warning("asyncpg_pool_failed", error=str(exc), fallback="disabled")
        return None


def bootstrap_incident_store(pool: object | None) -> IncidentStorePort | None:
    """Bootstrap the PostgreSQL incident event store.

    Args:
        pool: Shared asyncpg pool from bootstrap_asyncpg_pool().

    Returns:
        PostgresIncidentStore when a pool is available, None otherwise.
    """
    if pool is None:
        logger.info("incident_store_disabled", reason="no database pool")
        return None

    from sre_agent.adapters.persistence.incident_store import PostgresIncidentStore

    logger.info("incident_store_bootstrapped")
    return PostgresIncidentStore(pool=pool)


def bootstrap_outbox_store(pool: object | None) -> OutboxPort | None:
    """Bootstrap the PostgreSQL outbox store.

    Args:
        pool: Shared asyncpg pool from bootstrap_asyncpg_pool().

    Returns:
        PostgresOutboxStore when a pool is available, None otherwise.
    """
    if pool is None:
        logger.info("outbox_store_disabled", reason="no database pool")
        return None

    from sre_agent.adapters.persistence.postgres_outbox import PostgresOutboxStore

    logger.info("outbox_store_bootstrapped")
    return PostgresOutboxStore(pool=pool)


def bootstrap_diagnosis_store(pool: object | None) -> DiagnosisStorePort | None:
    """Bootstrap the PostgreSQL diagnosis result store.

    Args:
        pool: Shared asyncpg pool from bootstrap_asyncpg_pool().

    Returns:
        PostgresDiagnosisStore when a pool is available, None otherwise.
    """
    if pool is None:
        logger.info("diagnosis_store_disabled", reason="no database pool")
        return None

    from sre_agent.adapters.persistence.diagnosis_store import PostgresDiagnosisStore

    logger.info("diagnosis_store_bootstrapped")
    return PostgresDiagnosisStore(pool=pool)


def bootstrap_reasoning_trace_store(pool: object | None) -> ReasoningTracePort | None:
    """Bootstrap the PostgreSQL reasoning trace store.

    Gated behind environment flag ``SRE_AGENT_REASONING_TRACE_ENABLED`` so
    writes can be enabled gradually after back-pressure validation.
    """
    if pool is None:
        logger.info("reasoning_trace_store_disabled", reason="no database pool")
        return None

    enabled = os.getenv("SRE_AGENT_REASONING_TRACE_ENABLED", "false").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if not enabled:
        logger.info("reasoning_trace_store_disabled", reason="feature flag off")
        return None

    from sre_agent.adapters.persistence.reasoning_trace_store import (
        PostgresReasoningTraceStore,
    )

    logger.info("reasoning_trace_store_bootstrapped")
    return PostgresReasoningTraceStore(pool=pool)


def bootstrap_remediation_store(pool: object | None) -> RemediationStorePort | None:
    """Bootstrap the PostgreSQL remediation action store.

    Args:
        pool: Shared asyncpg pool from bootstrap_asyncpg_pool().

    Returns:
        PostgresRemediationStore when a pool is available, None otherwise.
    """
    if pool is None:
        logger.info("remediation_store_disabled", reason="no database pool")
        return None

    from sre_agent.adapters.persistence.remediation_store import PostgresRemediationStore

    logger.info("remediation_store_bootstrapped")
    return PostgresRemediationStore(pool=pool)


def bootstrap_retention_executor(
    pool: object | None,
    config: AgentConfig,
) -> object | None:
    """Bootstrap retention executor when enabled in configuration."""
    if pool is None:
        logger.info("retention_executor_disabled", reason="no database pool")
        return None

    if not config.retention.enabled:
        logger.info("retention_executor_disabled", reason="config disabled")
        return None

    from sre_agent.adapters.persistence.retention_executor import RetentionExecutor

    executor = RetentionExecutor(
        pool=pool,
        poll_interval_s=config.retention.poll_interval_s,
        processed_events_retention_days=config.retention.processed_events_retention_days,
        baseline_snapshots_retention_days=config.retention.baseline_snapshots_retention_days,
    )
    logger.info(
        "retention_executor_bootstrapped",
        poll_interval_s=config.retention.poll_interval_s,
        processed_events_days=config.retention.processed_events_retention_days,
        baseline_snapshots_days=config.retention.baseline_snapshots_retention_days,
    )
    return executor


def bootstrap_event_bus(config: AgentConfig) -> EventBus:
    """Bootstrap the event bus backend.

    Returns RedisStreamsEventBus when configured and redis available;
    falls back to InMemoryEventBus gracefully.
    """
    from sre_agent.config.settings import EventBusBackendType
    from sre_agent.events.in_memory import InMemoryEventBus

    if config.event_bus.backend == EventBusBackendType.REDIS_STREAMS:
        try:
            import redis.asyncio as aioredis  # type: ignore[import]

            from sre_agent.adapters.events.redis_streams_event_bus import (
                RedisStreamsEventBus,
            )

            client = aioredis.from_url(config.event_bus.redis_url)
            bus = RedisStreamsEventBus(
                redis_client=client,
                stream_prefix=config.event_bus.stream_prefix,
                consumer_group=config.event_bus.consumer_group,
                consumer_name=config.event_bus.consumer_name,
                block_ms=config.event_bus.block_ms,
                batch_size=config.event_bus.batch_size,
            )
            logger.info("event_bus_bootstrapped", backend="redis_streams")
            return bus
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "event_bus_backend_failed",
                backend="redis_streams",
                error=str(exc),
                fallback="in_memory",
            )

    logger.info("event_bus_bootstrapped", backend="in_memory")
    return InMemoryEventBus()


def bootstrap_vector_store(
    config: AgentConfig,
    pool: object | None = None,
) -> VectorStorePort:
    """Bootstrap the vector store adapter.

    Returns PgVectorStoreAdapter when persistence is enabled and a pool is
    provided; falls back to ChromaVectorStoreAdapter for dev/test.
    """
    from sre_agent.ports.vector_store import VectorStorePort  # noqa: F401

    if config.persistence.enabled and pool is not None:
        try:
            from sre_agent.adapters.vectordb.pgvector.adapter import PgVectorStoreAdapter

            adapter = PgVectorStoreAdapter(
                pool=pool,
                embedding_dim=config.persistence.vector_embedding_dim,
                collection=config.persistence.vector_collection,
            )
            logger.info(
                "vector_store_bootstrapped",
                backend="pgvector",
                dim=config.persistence.vector_embedding_dim,
                collection=config.persistence.vector_collection,
            )
            return adapter
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "vector_store_pgvector_failed",
                error=str(exc),
                fallback="chromadb",
            )

    # Dev/test fallback
    try:
        from sre_agent.adapters.vectordb.chroma.adapter import ChromaVectorStoreAdapter

        adapter_chroma = ChromaVectorStoreAdapter(
            collection_name=config.persistence.vector_collection,
        )
        logger.info("vector_store_bootstrapped", backend="chromadb")
        return adapter_chroma
    except Exception as exc:  # noqa: BLE001
        logger.error("vector_store_bootstrap_failed", error=str(exc))
        raise


def bootstrap_event_store(pool: object | None) -> EventStore | None:
    """Bootstrap the PostgreSQL domain event store.

    Args:
        pool: Shared asyncpg pool from bootstrap_asyncpg_pool().

    Returns:
        PostgresEventStore when a pool is available, None otherwise.
    """
    if pool is None:
        logger.info("event_store_disabled", reason="no database pool")
        return None

    from sre_agent.adapters.persistence.event_store import PostgresEventStore

    logger.info("event_store_bootstrapped")
    return PostgresEventStore(pool=pool)
