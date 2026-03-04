## 1. Canonical Data Model Refactoring

- [x] 1.1 Add `ComputeMechanism` enum to `canonical.py` with values: `KUBERNETES`, `SERVERLESS`, `VIRTUAL_MACHINE`, `CONTAINER_INSTANCE`
- [x] 1.2 Add `compute_mechanism`, `resource_id`, and `platform_metadata` fields to `ServiceLabels`; make `namespace` and `pod` optional
- [x] 1.3 Update `ServiceNode` to add `compute_mechanism` and make `namespace` optional
- [x] 1.4 Update `AnomalyAlert` to use `resource_id` alongside `namespace` for backwards compatibility
- [x] 1.5 Update `CorrelatedSignals` to support `compute_mechanism` awareness
- [x] 1.6 Fix broken tests in `tests/unit/domain/test_canonical.py` for new `ServiceLabels` fields
- [x] 1.7 Fix broken tests in `tests/unit/domain/test_detection.py` affected by `ServiceLabels` changes
- [x] 1.8 Fix broken tests in `tests/unit/domain/test_integration.py`

## 2. eBPF Telemetry Graceful Degradation

- [x] 2.1 Add `is_supported(compute_mechanism: ComputeMechanism) -> bool` method to `eBPFQuery` port in `ports/telemetry.py`
- [x] 2.2 Update `SignalCorrelator._fetch_ebpf_events()` to call `is_supported()` and auto-set `has_degraded_observability = True` when unsupported
- [x] 2.3 Log degradation event with reason `"ebpf_unsupported_on_{compute_mechanism}"`
- [x] 2.4 Write unit test: `test_ebpf_degrades_on_serverless` — assert `is_supported(SERVERLESS) == False`
- [x] 2.5 Write unit test: `test_ebpf_degrades_on_container_instance` — assert `is_supported(CONTAINER_INSTANCE) == False`
- [x] 2.6 Write unit test: `test_ebpf_supported_on_kubernetes` — assert `is_supported(KUBERNETES) == True`
- [x] 2.7 Write unit test: `test_ebpf_supported_on_virtual_machine` — assert `is_supported(VIRTUAL_MACHINE) == True`

## 3. Serverless Anomaly Detection Logic

- [x] 3.1 Add `cold_start_suppression_window_seconds` config to `DetectionConfig` (default: 15s)
- [x] 3.2 Modify `AnomalyDetector._detect_latency_spike()` to suppress alerts within cold-start window for `SERVERLESS`
- [x] 3.3 Modify `AnomalyDetector._detect_memory_pressure()` to skip memory pressure rule for `SERVERLESS`
- [x] 3.4 Add `InvocationError` surge monitoring as OOM replacement for serverless
- [x] 3.5 Write unit test: `test_cold_start_suppression_lambda`
- [x] 3.6 Write unit test: `test_memory_pressure_exempted_for_serverless`
- [x] 3.7 Write unit test: `test_invocation_error_surge_detected_for_serverless`

## 4. Cloud Operator Abstraction (Port)

- [x] 4.1 Create `src/sre_agent/ports/cloud_operator.py` with `CloudOperatorPort` interface (`restart_compute_unit`, `scale_capacity`, `is_action_supported`)
- [x] 4.2 Include `health_check()` method in the interface for pre-flight validation

## 5. AWS Remediation Adapters

- [x] 5.1 Create `src/sre_agent/adapters/cloud/aws/ecs_operator.py` (ECS `StopTask`, `UpdateService`)
- [x] 5.2 Create `src/sre_agent/adapters/cloud/aws/ec2_asg_operator.py` (EC2 ASG `SetDesiredCapacity`)
- [x] 5.3 Create `src/sre_agent/adapters/cloud/aws/lambda_operator.py` (Lambda reserved concurrency adjustment)
- [x] 5.4 Add `boto3` as optional dependency in `pyproject.toml` under `aws` extras
- [x] 5.5 Write unit tests for all AWS adapters using mocked boto3 clients

## 6. Azure Remediation Adapters

- [x] 6.1 Create `src/sre_agent/adapters/cloud/azure/app_service_operator.py` (restart, instance count scaling)
- [x] 6.2 Create `src/sre_agent/adapters/cloud/azure/functions_operator.py` (restart, Premium plan scaling)
- [x] 6.3 Add `azure-mgmt-web` as optional dependency in `pyproject.toml` under `azure` extras
- [x] 6.4 Write unit tests for all Azure adapters using mocked Azure SDK clients

## 7. Provider Registry & Wiring

- [x] 7.1 Create `CloudOperatorRegistry` to select correct `CloudOperatorPort` based on `compute_mechanism` and cloud provider
- [x] 7.2 Update `adapters/bootstrap.py` to wire up cloud operators alongside telemetry providers
- [x] 7.3 Write integration test: given `CONTAINER_INSTANCE` on AWS, registry returns `ECSOperator`

## 8. Documentation & Migration

- [x] 8.1 Update `docs/architecture/Technology_Stack.md` to add `boto3` and `azure-mgmt-web`
- [x] 8.2 Update `docs/architecture/data_model.md` to reflect `ComputeMechanism`-aware `ServiceLabels`
- [x] 8.3 Update `docs/architecture/layers/action_layer_details.md` to document `CloudOperatorPort`
- [x] 8.4 Add migration notes for existing K8s configs to set `compute_mechanism = "KUBERNETES"`
