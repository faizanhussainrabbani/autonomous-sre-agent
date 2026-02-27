## 1. Data Model Refactoring

- [ ] 1.1 Extract `ServiceLabels` into a flexible `ComputeMechanism`-aware abstraction
- [ ] 1.2 Update `AnomalyAlert` to handle optional namespace and pod fields
- [ ] 1.3 Fix broken tests in `tests/unit/domain/test_canonical.py`

## 2. Telemetry Downgrade Support

- [ ] 2.1 Update `eBPFQuery` port interface with `is_supported` method
- [ ] 2.2 Modify `SignalCorrelator` to handle `DataQuality.INCOMPLETE` gracefully
- [ ] 2.3 Implement mock test for eBPF bypass

## 3. Serverless Detection Logic

- [ ] 3.1 Implement cold-start suppression window in `AnomalyDetector`
- [ ] 3.2 Add conditional bypassing of OOM rules for `SERVERLESS` targets
- [ ] 3.3 Add unit tests simulating Lambda invocations

## 4. Cloud Operator Abstraction

- [ ] 4.1 Define `CloudOperatorPort` interface in `src/sre_agent/ports/cloud_operator.py`
- [ ] 4.2 Implement `ecs_operator.py` adapter
- [ ] 4.3 Implement `ec2_auto_scaling_operator.py` adapter
- [ ] 4.4 Implement `lambda_operator.py` adapter
- [ ] 4.5 Implement `app_service_operator.py` adapter
- [ ] 4.6 Update `ProviderRegistry` to inject correct operator based on target
