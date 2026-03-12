# Phase 1.5: Non-Kubernetes Platforms — Comprehensive Review

**Date:** March 3, 2026
**Reviewer:** AI Systems Architect
**Scope:** `openspec/changes/phase-1-5-non-k8s-platforms/`

---

## Part 1: Detailed Spec Review & Gaps

### 1.1 Proposal Review

The proposal is fundamentally sound. It correctly identifies the K8s coupling problem, lists all affected capabilities, and highlights the **BREAKING** data model change. However, there are several critical gaps:

> [!WARNING]
> **Missing from Proposal:**
> - **Lambda Operator**: The proposal mentions "AWS Operators" covering ECS, EC2 ASG, **and Lambda**, but the `tasks.md` has a task for `lambda_operator.py`, while `aws-remediation-adapters/spec.md` has **no Lambda requirement or scenario**. This is a spec-to-task mismatch.
> - **Azure Functions Operator**: The proposal mentions "Azure Adapters for App Services **and Functions**", but `azure-remediation-adapters/spec.md` only specifies App Service. Azure Functions restart/scale is **entirely absent** from the spec.
> - **No `restart_compute_unit` for EC2**: The EC2 ASG spec only covers `scale_capacity`. There is no scenario for restarting an individual EC2 instance.

### 1.2 Design Review

The design is architecturally sharp. The three key decisions (Unified Enum vs Polymorphism, Graceful Degradation vs Dual Pipelines, Cold Start Awareness) are well-reasoned. However:

> [!IMPORTANT]
> **Gap: `ServiceNode` Not Addressed.** The design only addresses `ServiceLabels` refactoring. The `ServiceNode` dataclass (line 234-240 of `canonical.py`) has a hardcoded `namespace: str` field with no `compute_mechanism`. This class is used by the `DependencyGraph`, meaning the dependency graph will also fail for non-K8s services.

### 1.3 Spec-by-Spec Review

#### `serverless-anomaly-detection/spec.md` — ✅ Solid
- Cold-start suppression is well-defined (15-second window).
- OOM exemption for serverless is correct.
- **Gap**: No scenario for **Azure Functions** cold starts. The spec only mentions Lambda implicitly. Azure Functions have a different cold-start profile (especially on Consumption plan vs Premium plan).

#### `aws-remediation-adapters/spec.md` — ⚠️ Incomplete
- ECS Task restart: ✅ Well-specified.
- ECS Service scaling: ✅ Well-specified.
- EC2 ASG scaling: ✅ Well-specified.
- **MISSING**: Lambda `restart_compute_unit` (not applicable to Lambda — spec should explicitly state Lambda does NOT support restart and instead supports `update_function_configuration` or reserved concurrency adjustments).
- **MISSING**: Lambda `scale_capacity` scenario (adjusting reserved concurrency).
- **MISSING**: Error scenarios (e.g., what happens when `StopTask` is called on a task within a FARGATE launch type vs EC2 launch type?).

#### `azure-remediation-adapters/spec.md` — ⚠️ Incomplete
- App Service restart: ✅ Well-specified.
- App Service Plan scaling: ✅ Well-specified.
- **MISSING**: Azure Functions restart scenario.
- **MISSING**: Azure Functions scale scenario (Consumption plan auto-scales; Premium plan supports manual instance count).

#### `telemetry-ingestion/spec.md` — ⚠️ Needs More Scenarios
- Graceful eBPF degradation: ✅ Core scenario is well-defined.
- **MISSING**: Scenario for `CONTAINER_INSTANCE` (e.g., AWS ECS on Fargate). Fargate also lacks eBPF, so this should also degrade gracefully.
- **MISSING**: Scenario for `VIRTUAL_MACHINE` (EC2/Azure VM). These **do** support eBPF. The spec should assert `is_supported() == True`.
- **MISSING**: Scenario for when eBPF *was* available but fails mid-operation (transition from HIGH to INCOMPLETE quality).

### 1.4 Tasks Review — `tasks.md`

The current task list has **15 tasks** across 4 groups. This is **critically incomplete**.

| Current Task | Verdict |
|---|---|
| 1.1 Extract `ServiceLabels` into `ComputeMechanism`-aware abstraction | ✅ Valid |
| 1.2 Update `AnomalyAlert` to handle optional namespace/pod | ✅ Valid |
| 1.3 Fix broken tests in `test_canonical.py` | ✅ Valid |
| 2.1 Update `eBPFQuery` with `is_supported` method | ✅ Valid |
| 2.2 Modify `SignalCorrelator` for `DataQuality.INCOMPLETE` | ⚠️ Partially done — correlator already accepts `is_degraded` param |
| 2.3 Implement mock test for eBPF bypass | ✅ Valid |
| 3.1 Implement cold-start suppression | ✅ Valid |
| 3.2 Conditional bypass of OOM rules for `SERVERLESS` | ✅ Valid |
| 3.3 Unit tests simulating Lambda invocations | ✅ Valid |
| 4.1 Define `CloudOperatorPort` interface | ✅ Valid |
| 4.2–4.5 Implement adapters | ✅ Valid (but 4.4 Lambda is unspec'd) |
| 4.6 Update `ProviderRegistry` to inject correct operator | ⚠️ Vague — needs more detail |

---

## Part 2: Complete Task Breakdown

Below is the **corrected and complete** task list required to fully achieve Phase 1.5.

### Group 1: Canonical Data Model Refactoring

- [ ] **1.1** Add `ComputeMechanism` enum to `canonical.py` with values: `KUBERNETES`, `SERVERLESS`, `VIRTUAL_MACHINE`, `CONTAINER_INSTANCE`.
- [ ] **1.2** Add `compute_mechanism: ComputeMechanism` field to `ServiceLabels`. Make `namespace` and `pod` optional (`str = ""`). Add `resource_id: str` and `platform_metadata: dict[str, Any]` fields.
- [ ] **1.3** Update `ServiceNode` to add `compute_mechanism: ComputeMechanism` and make `namespace` optional.
- [ ] **1.4** Update `AnomalyAlert` to use `resource_id` instead of `namespace` as the primary resource identifier, keeping `namespace` for backwards compatibility.
- [ ] **1.5** Update `CorrelatedSignals` to support `compute_mechanism` awareness.
- [ ] **1.6** Fix all broken unit tests in `tests/unit/domain/test_canonical.py` that pass literal K8s-specific values.
- [ ] **1.7** Fix all broken unit tests in `tests/unit/domain/test_detection.py` affected by `ServiceLabels` changes.
- [ ] **1.8** Fix all broken unit tests in `tests/unit/domain/test_integration.py`.

### Group 2: eBPF Telemetry Graceful Degradation

- [ ] **2.1** Add `is_supported(compute_mechanism: ComputeMechanism) -> bool` method to `eBPFQuery` port interface in `ports/telemetry.py`.
- [ ] **2.2** Update `SignalCorrelator._fetch_ebpf_events()` to call `is_supported()` and automatically set `has_degraded_observability = True` when eBPF is unsupported.
- [ ] **2.3** Log the degradation event with reason `"ebpf_unsupported_on_{compute_mechanism}"`.
- [ ] **2.4** Write unit test: `test_ebpf_degrades_on_serverless` — assert `is_supported(SERVERLESS) == False`.
- [ ] **2.5** Write unit test: `test_ebpf_degrades_on_container_instance` — assert `is_supported(CONTAINER_INSTANCE) == False` (Fargate).
- [ ] **2.6** Write unit test: `test_ebpf_supported_on_kubernetes` — assert `is_supported(KUBERNETES) == True`.
- [ ] **2.7** Write unit test: `test_ebpf_supported_on_virtual_machine` — assert `is_supported(VIRTUAL_MACHINE) == True`.

### Group 3: Serverless Anomaly Detection Logic

- [ ] **3.1** Add `cold_start_suppression_window_seconds` config to `DetectionConfig` (default: 15s).
- [ ] **3.2** Modify `AnomalyDetector._detect_latency_spike()` to check `compute_mechanism`. If `SERVERLESS` and metric timestamp is within the cold-start window, suppress the alert and log `reason=cold_start`.
- [ ] **3.3** Modify `AnomalyDetector._detect_memory_pressure()` to skip the memory pressure rule entirely if `compute_mechanism == SERVERLESS`.
- [ ] **3.4** Add monitoring for `InvocationError` surges when `compute_mechanism == SERVERLESS` as a replacement for OOM detection.
- [ ] **3.5** Write unit test: `test_cold_start_suppression_lambda` — assert latency spike within 15s of init is suppressed.
- [ ] **3.6** Write unit test: `test_memory_pressure_exempted_for_serverless` — assert memory pressure alert is NOT fired for `SERVERLESS`.
- [ ] **3.7** Write unit test: `test_invocation_error_surge_detected_for_serverless`.

### Group 4: Cloud Operator Abstraction (Port)

- [ ] **4.1** Create `src/sre_agent/ports/cloud_operator.py` defining the `CloudOperatorPort` abstract interface with methods: `restart_compute_unit(resource_id, metadata)`, `scale_capacity(resource_id, desired_count, metadata)`, `is_action_supported(action, compute_mechanism) -> bool`.
- [ ] **4.2** Ensure the interface includes a `health_check()` method for pre-flight validation.

### Group 5: AWS Remediation Adapters

- [ ] **5.1** Create `src/sre_agent/adapters/cloud/aws/ecs_operator.py` implementing `CloudOperatorPort` for ECS (`StopTask`, `UpdateService`).
- [ ] **5.2** Create `src/sre_agent/adapters/cloud/aws/ec2_asg_operator.py` implementing `CloudOperatorPort` for EC2 ASGs (`SetDesiredCapacity`).
- [ ] **5.3** Create `src/sre_agent/adapters/cloud/aws/lambda_operator.py` implementing `CloudOperatorPort` for Lambda (adjust reserved concurrency, NOT restart).
- [ ] **5.4** Add `boto3` as an optional dependency in `pyproject.toml` under `[project.optional-dependencies]` as `aws = ["boto3>=1.34"]`.
- [ ] **5.5** Write unit tests for each AWS adapter using mocked boto3 clients (`moto` or `unittest.mock`).

### Group 6: Azure Remediation Adapters

- [ ] **6.1** Create `src/sre_agent/adapters/cloud/azure/app_service_operator.py` implementing `CloudOperatorPort` for App Service (`webApps.restart`, instance count scaling).
- [ ] **6.2** Create `src/sre_agent/adapters/cloud/azure/functions_operator.py` implementing `CloudOperatorPort` for Azure Functions (restart, Premium plan scaling).
- [ ] **6.3** Add `azure-mgmt-web` as an optional dependency in `pyproject.toml` under `[project.optional-dependencies]` as `azure = ["azure-mgmt-web>=7.0"]`.
- [ ] **6.4** Write unit tests for each Azure adapter using mocked Azure SDK clients.

### Group 7: Provider Registry & Wiring

- [ ] **7.1** Update `ProviderRegistry` (or create a new `CloudOperatorRegistry`) to select the correct `CloudOperatorPort` implementation based on the target service's `compute_mechanism` and cloud provider metadata.
- [ ] **7.2** Update `adapters/bootstrap.py` to wire up cloud operators alongside telemetry providers.
- [ ] **7.3** Write integration test: given a service with `compute_mechanism=CONTAINER_INSTANCE` and cloud=`aws`, the registry returns the `ECSOperator`.

### Group 8: Documentation & Migration

- [ ] **8.1** Update `docs/architecture/Technology_Stack.md` to add `boto3` and `azure-mgmt-web` to the stack.
- [ ] **8.2** Update `docs/architecture/data_model.md` to reflect the new `ComputeMechanism`-aware `ServiceLabels`.
- [ ] **8.3** Update `docs/architecture/layers/action_layer_details.md` to document the `CloudOperatorPort` interface alongside the existing K8s API.
- [ ] **8.4** Add migration notes for existing K8s configs to set `compute_mechanism = "KUBERNETES"`.

---

## Part 3: Detailed Acceptance Criteria

### AC-1.5.1: Compute-Agnostic Data Model
| ID | Criterion | Verification |
|---|---|---|
| AC-1.5.1.1 | `ServiceLabels` SHALL include a `compute_mechanism` field of type `ComputeMechanism` enum. | Unit test asserts `ServiceLabels(service="svc", namespace="", compute_mechanism=ComputeMechanism.SERVERLESS)` is valid. |
| AC-1.5.1.2 | `ServiceLabels.namespace` SHALL default to `""` and NOT be required. | Unit test creates `ServiceLabels` without `namespace` and it succeeds. |
| AC-1.5.1.3 | `ServiceLabels` SHALL include a `resource_id: str` field that serves as the universal compute unit identifier (e.g., Pod UID, ECS Task ARN, Lambda Function ARN). | Unit test asserts `resource_id` is populated in all canonical models. |
| AC-1.5.1.4 | `ServiceLabels` SHALL include a `platform_metadata: dict` for provider-specific data. | Unit test validates arbitrary metadata is stored and retrievable. |
| AC-1.5.1.5 | All existing tests passing K8s-specific values to `ServiceLabels` SHALL continue to pass with `compute_mechanism` defaulting to `KUBERNETES`. | `pytest tests/unit/domain/` passes with 0 failures. |

### AC-1.5.2: Graceful eBPF Degradation
| ID | Criterion | Verification |
|---|---|---|
| AC-1.5.2.1 | `eBPFQuery` SHALL expose an `is_supported(compute_mechanism)` method. | Unit test asserts the interface has the method. |
| AC-1.5.2.2 | `is_supported()` SHALL return `False` for `SERVERLESS` and `CONTAINER_INSTANCE` (Fargate). | Unit test with mocked adapter. |
| AC-1.5.2.3 | `is_supported()` SHALL return `True` for `KUBERNETES` and `VIRTUAL_MACHINE`. | Unit test with mocked adapter. |
| AC-1.5.2.4 | When `is_supported()` returns `False`, `SignalCorrelator` SHALL tag `CorrelatedSignals` with `has_degraded_observability = True`. | Integration test correlating signals for a Lambda service. |
| AC-1.5.2.5 | The system SHALL NOT fail health checks when eBPF is unsupported. | Integration test asserting no errors in logs when correlating on serverless. |

### AC-1.5.3: Serverless Cold-Start Suppression
| ID | Criterion | Verification |
|---|---|---|
| AC-1.5.3.1 | Latency spikes occurring within `cold_start_suppression_window_seconds` of a serverless instance initialization SHALL be suppressed. | Unit test: inject a latency spike at T+5s for a `SERVERLESS` metric → assert `suppressed_count == 1`. |
| AC-1.5.3.2 | Suppressed alerts SHALL be logged with `reason=cold_start`. | Assert log output contains `"cold_start"`. |
| AC-1.5.3.3 | Latency spikes occurring AFTER the cold-start window SHALL fire normally. | Unit test: inject a latency spike at T+20s → assert alert is generated. |

### AC-1.5.4: Serverless OOM Exemption
| ID | Criterion | Verification |
|---|---|---|
| AC-1.5.4.1 | Memory pressure alerts SHALL NOT fire for `ComputeMechanism.SERVERLESS`. | Unit test: inject memory > 85% with `SERVERLESS` → assert zero memory pressure alerts. |
| AC-1.5.4.2 | The system SHALL monitor `InvocationError` surges as a replacement for OOM on serverless. | Unit test: inject surge of invocation errors → assert alert is generated. |

### AC-1.5.5: Cloud Operator Port
| ID | Criterion | Verification |
|---|---|---|
| AC-1.5.5.1 | A `CloudOperatorPort` abstract interface SHALL exist with `restart_compute_unit()` and `scale_capacity()` methods. | Interface file exists and defines the methods. |
| AC-1.5.5.2 | Each method SHALL accept a `resource_id` and `platform_metadata` dict. | Type signature check. |
| AC-1.5.5.3 | The interface SHALL include `is_action_supported(action, compute_mechanism)` to allow adapters to decline unsupported actions (e.g., Lambda cannot "restart"). | Unit test: `LambdaOperator.is_action_supported("restart", SERVERLESS) == False`. |

### AC-1.5.6: AWS Adapters
| ID | Criterion | Verification |
|---|---|---|
| AC-1.5.6.1 | `ECSOperator.restart_compute_unit()` SHALL call `ecs.stop_task()` via boto3. | Unit test with mocked boto3 `stop_task`. |
| AC-1.5.6.2 | `ECSOperator.scale_capacity()` SHALL call `ecs.update_service(desiredCount=N)`. | Unit test with mocked boto3 `update_service`. |
| AC-1.5.6.3 | `EC2ASGOperator.scale_capacity()` SHALL call `autoscaling.set_desired_capacity()`. | Unit test with mocked boto3. |
| AC-1.5.6.4 | `LambdaOperator.scale_capacity()` SHALL call `lambda.put_function_concurrency()`. | Unit test with mocked boto3. |

### AC-1.5.7: Azure Adapters
| ID | Criterion | Verification |
|---|---|---|
| AC-1.5.7.1 | `AppServiceOperator.restart_compute_unit()` SHALL issue a POST to `webApps.restart`. | Unit test with mocked Azure SDK. |
| AC-1.5.7.2 | `AppServiceOperator.scale_capacity()` SHALL modify the App Service Plan instance count. | Unit test with mocked Azure SDK. |
| AC-1.5.7.3 | `FunctionsOperator` SHALL exist for Azure Functions restart and Premium plan scaling. | Unit test with mocked Azure SDK. |

---

## Part 4: Expected Output Verification

This section defines the **exact expected outputs** that must be verifiable after Phase 1.5 is fully implemented. These serve as the end-to-end validation script.

### Test 1: Data Model Backward Compatibility
```python
# Command: pytest tests/unit/domain/test_canonical.py -v
# Expected: ALL TESTS PASS (0 failures, 0 errors)

# Existing K8s ServiceLabels MUST still work:
labels = ServiceLabels(service="checkout", namespace="prod", pod="checkout-abc-123")
assert labels.compute_mechanism == ComputeMechanism.KUBERNETES  # default
assert labels.resource_id == ""  # optional for K8s (pod is used)
```

### Test 2: Serverless ServiceLabels
```python
labels = ServiceLabels(
    service="payment-handler",
    namespace="",
    compute_mechanism=ComputeMechanism.SERVERLESS,
    resource_id="arn:aws:lambda:us-east-1:123456789:function:payment-handler",
    platform_metadata={"runtime": "python3.12", "memory_mb": 512},
)
assert labels.compute_mechanism == ComputeMechanism.SERVERLESS
assert labels.namespace == ""
assert labels.platform_metadata["runtime"] == "python3.12"
```

### Test 3: eBPF Graceful Degradation
```python
# Command: pytest tests/unit/domain/test_ebpf_degradation.py -v

# When correlating signals for a serverless service:
correlator = SignalCorrelator(metrics_q, trace_q, log_q, ebpf_q)
result = await correlator.correlate(
    service="payment-handler",
    namespace="",
    start_time=t0, end_time=t1,
)
assert result.has_degraded_observability == True
assert result.degradation_reason == "ebpf_unsupported_on_SERVERLESS"
# NO exceptions thrown, NO health check failures
```

### Test 4: Cold-Start Suppression
```python
# Command: pytest tests/unit/domain/test_serverless_detection.py -v

# Metric arriving 5 seconds after Lambda cold start:
metric = CanonicalMetric(
    name="http_request_duration_seconds",
    value=8.5,  # Very high (cold start)
    timestamp=init_time + timedelta(seconds=5),
    labels=ServiceLabels(
        service="payment-handler",
        namespace="",
        compute_mechanism=ComputeMechanism.SERVERLESS,
    ),
)
result = detector.detect("payment-handler", [metric])
assert result.suppressed_count == 1
assert len(result.alerts) == 0

# Metric arriving 20 seconds after (past cold start window):
metric_late = CanonicalMetric(
    name="http_request_duration_seconds",
    value=8.5,
    timestamp=init_time + timedelta(seconds=20),
    labels=ServiceLabels(
        service="payment-handler",
        namespace="",
        compute_mechanism=ComputeMechanism.SERVERLESS,
    ),
)
result_late = detector.detect("payment-handler", [metric_late])
assert len(result_late.alerts) == 1  # Alert fires normally
```

### Test 5: OOM Exemption for Serverless
```python
metric = CanonicalMetric(
    name="process_resident_memory_bytes",
    value=0.92,  # 92% — normally triggers alert
    timestamp=now,
    labels=ServiceLabels(
        service="payment-handler",
        namespace="",
        compute_mechanism=ComputeMechanism.SERVERLESS,
    ),
)
result = detector.detect("payment-handler", [metric])
assert len([a for a in result.alerts if a.anomaly_type == AnomalyType.MEMORY_PRESSURE]) == 0
```

### Test 6: ECS Operator
```python
# Command: pytest tests/unit/adapters/test_aws_operators.py -v

operator = ECSOperator(ecs_client=mock_ecs)
await operator.restart_compute_unit(
    resource_id="arn:aws:ecs:us-east-1:123456789:task/cluster/task-id",
    metadata={"cluster": "prod-cluster"},
)
mock_ecs.stop_task.assert_called_once_with(
    cluster="prod-cluster",
    task="arn:aws:ecs:us-east-1:123456789:task/cluster/task-id",
)
```

### Test 7: Full Pipeline Integration
```python
# Command: pytest tests/e2e/test_phase_1_5_integration.py -v

# End-to-end: Ingest serverless metric → Correlate (degraded) → Detect (cold-start suppressed)
# 1. Create serverless ServiceLabels
# 2. Create metrics simulating a Lambda cold start
# 3. Run SignalCorrelator → verify has_degraded_observability
# 4. Run AnomalyDetector → verify cold-start alert suppressed
# 5. Create metrics simulating steady-state latency spike
# 6. Run AnomalyDetector → verify alert fires normally
# Expected: All assertions pass, 0 exceptions
```

### Summary Test Matrix

| Test File | Command | Expected Result |
|---|---|---|
| `tests/unit/domain/test_canonical.py` | `pytest tests/unit/domain/test_canonical.py -v` | All pass (including new `ComputeMechanism` tests) |
| `tests/unit/domain/test_detection.py` | `pytest tests/unit/domain/test_detection.py -v` | All pass (including serverless suppression) |
| `tests/unit/domain/test_ebpf_degradation.py` | `pytest tests/unit/domain/test_ebpf_degradation.py -v` | All pass (new file) |
| `tests/unit/domain/test_serverless_detection.py` | `pytest tests/unit/domain/test_serverless_detection.py -v` | All pass (new file) |
| `tests/unit/adapters/test_aws_operators.py` | `pytest tests/unit/adapters/test_aws_operators.py -v` | All pass (new file) |
| `tests/unit/adapters/test_azure_operators.py` | `pytest tests/unit/adapters/test_azure_operators.py -v` | All pass (new file) |
| `tests/e2e/test_phase_1_5_integration.py` | `pytest tests/e2e/test_phase_1_5_integration.py -v` | All pass (new file) |
| **Full suite** | `pytest tests/ -v` | **0 failures, 0 errors** |
