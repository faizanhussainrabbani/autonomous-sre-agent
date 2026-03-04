# Agent Configuration Reference

**Status:** DRAFT  
**Version:** 1.0.0

This document describes the schema and usage of the SRE Agent's primary configuration file: `config/agent.yaml`.

For the full list of configuration keys and their Python defaults, see [`src/sre_agent/config/settings.py`](../src/sre_agent/config/settings.py).

---

## Top-Level Keys

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `telemetry_provider` | `string` | `"otel"` | The active telemetry backend. One of `"otel"` or `"newrelic"`. |
| `cloud_provider` | `string` | `"none"` | The active cloud provider for remediation. One of `"aws"`, `"azure"`, or `"none"`. |
| `log_level` | `string` | `"INFO"` | Python logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`). |
| `environment` | `string` | `"development"` | Deployment environment identifier (`development`, `staging`, `production`). |

---

## `otel` — OpenTelemetry Backend Configuration

Used when `telemetry_provider: otel`.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `prometheus_url` | `string` | `http://prometheus:9090` | Prometheus HTTP API base URL. |
| `jaeger_url` | `string` | `http://jaeger:16686` | Jaeger Query API base URL. |
| `loki_url` | `string` | `http://loki:3100` | Loki Log Query API base URL. |
| `otel_collector_url` | `string` | `http://otel-collector:4317` | OTel Collector gRPC endpoint. |

## `newrelic` — New Relic Backend Configuration

Used when `telemetry_provider: newrelic`.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `account_id` | `string` | — | Your New Relic account ID. |
| `api_key_secret_name` | `string` | — | Name of the secret containing the NerdGraph API key. |
| `region` | `string` | `"US"` | New Relic data center region (`US` or `EU`). |

## `aws` — AWS Cloud Configuration

Used when `cloud_provider: aws`.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `region` | `string` | `"us-east-1"` | AWS region for API calls. |
| `eks_cluster_name` | `string` | — | EKS cluster name for Kubernetes operations. |
| `s3_bucket` | `string` | — | S3 bucket for audit log storage. |
| `secrets_manager_prefix` | `string` | `"/sre-agent/"` | AWS Secrets Manager key prefix. |

## `azure` — Azure Cloud Configuration

Used when `cloud_provider: azure`.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `subscription_id` | `string` | — | Azure subscription ID. |
| `resource_group` | `string` | — | Resource group containing managed services. |
| `aks_cluster_name` | `string` | — | AKS cluster name for Kubernetes operations. |
| `blob_container` | `string` | — | Blob container for audit log storage. |
| `keyvault_name` | `string` | — | Azure Key Vault name for secret management. |

---

## `detection` — Anomaly Detection Thresholds

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `latency_sigma_threshold` | `float` | `3.0` | Standard deviations above baseline to trigger latency alert. |
| `latency_duration_minutes` | `int` | `2` | Minimum sustained duration before latency alert fires. |
| `error_rate_surge_percent` | `float` | `200.0` | Percentage increase over baseline to trigger error rate alert. |
| `memory_pressure_percent` | `float` | `85.0` | Memory usage threshold for pressure alerts. |
| `memory_pressure_duration_minutes` | `int` | `5` | Sustained duration for memory pressure alerts. |
| `disk_exhaustion_percent` | `float` | `80.0` | Disk usage threshold for exhaustion alerts. |
| `disk_projection_hours` | `int` | `24` | Projected time-to-full window for proactive alerts. |
| `cert_expiry_warning_days` | `int` | `14` | Days before cert expiry for WARNING alert. |
| `cert_expiry_critical_days` | `int` | `3` | Days before cert expiry for CRITICAL alert. |
| `deployment_correlation_window_minutes` | `int` | `60` | Time window to correlate anomalies with recent deployments. |
| `suppression_window_seconds` | `int` | `30` | Duration of alert suppression during active deployment windows. |

---

## `performance` — SLO Timing Constraints

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `alert_latency_seconds` | `int` | `60` | Max time from threshold crossing to alert emission (latency). |
| `error_alert_latency_seconds` | `int` | `30` | Max time from error burst to alert emission. |
| `proactive_alert_latency_seconds` | `int` | `120` | Max time for proactive resource exhaustion alerts. |
| `rag_query_timeout_seconds` | `int` | `30` | Timeout for RAG diagnostic queries. |
| `max_concurrent_rag_queries` | `int` | `10` | Concurrency limit for RAG queries. |
| `max_concurrent_remediations` | `int` | `3` | Concurrency limit for active remediation actions. |

---

## `features` — Feature Flags

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `ebpf_enabled` | `bool` | `true` | Enable kernel-level eBPF signal collection. |
| `multi_dimensional_correlation` | `bool` | `true` | Enable multi-signal incident correlation. |
| `deployment_aware_detection` | `bool` | `true` | Flag anomalies near recent deployments. |
| `proactive_scaling` | `bool` | `false` | **[PLANNED]** Predictive auto-scaling before resource exhaustion. |
| `architectural_recommendations` | `bool` | `false` | **[PLANNED]** AI-generated architecture improvement suggestions. |
| `new_relic_adapter` | `bool` | `false` | Enable the New Relic NerdGraph adapter. |
| `otel_adapter` | `bool` | `true` | Enable the OpenTelemetry stack adapter. |

---

## Environment Variable Overrides

All configuration keys can be overridden via environment variables using the `SRE_AGENT_` prefix and double-underscore nesting:

```bash
# Override telemetry provider
export SRE_AGENT_TELEMETRY_PROVIDER=newrelic

# Override detection threshold
export SRE_AGENT_DETECTION__LATENCY_SIGMA_THRESHOLD=2.5

# Override feature flag
export SRE_AGENT_FEATURES__EBPF_ENABLED=false
```

Environment variables take precedence over `agent.yaml` values.
