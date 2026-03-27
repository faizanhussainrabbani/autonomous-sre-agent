## Why

Many enterprises already use Datadog for observability but lack autonomous remediation capabilities. Our competitive analysis found that Datadog's own AIOps (Bits AI, Workflow Automation) is tightly coupled to their proprietary telemetry stack — creating an opportunity for our agent to operate *on top of* Datadog's data with superior safety controls.

Providing a Datadog telemetry adapter means enterprises can adopt our agent without changing their existing observability stack. This is a competitive subversion strategy: use Datadog's own data to power our safety-first remediation, directly challenging their AIOps offering.

The existing `provider-abstraction` spec defines the extensible telemetry provider interface and canonical data model. This change delivers the first proprietary backend adapter.

## What Changes

- **New Datadog metrics adapter** (`adapters/telemetry/datadog/metrics.py`): Implements `MetricsQuery` ABC using Datadog Metrics API v2
- **New Datadog traces adapter** (`adapters/telemetry/datadog/traces.py`): Implements `TraceQuery` ABC using Datadog APM API
- **New Datadog logs adapter** (`adapters/telemetry/datadog/logs.py`): Implements `LogQuery` ABC using Datadog Logs API
- **New Datadog service map adapter** (`adapters/telemetry/datadog/service_map.py`): Implements `DependencyGraphQuery` using Datadog Service Map API
- **Updated configuration**: `TelemetrySettings` extended with Datadog API key, application key, and site configuration
- **Updated provider registry**: Datadog registered as selectable provider (`telemetry_provider: "datadog"`)

## Capabilities

### New Capabilities
- `datadog-telemetry`: Full metric, trace, and log ingestion from Datadog using Datadog APIs, canonicalized to internal data model

### Modified Capabilities
- `provider-abstraction`: First proprietary backend adapter validates the plugin architecture

## Impact

- **Dependencies**: `datadog-api-client` Python SDK
- **Configuration**: `SRE_AGENT_DATADOG_API_KEY`, `SRE_AGENT_DATADOG_APP_KEY`, `SRE_AGENT_DATADOG_SITE`
- **Security**: API/App keys must be stored in secrets manager
