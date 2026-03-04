# Phase 1.5 Migration Notes

## For Existing Kubernetes Configurations

Phase 1.5 introduces compute-agnostic data models. Existing Kubernetes-based
configurations will **continue to work without changes** because:

- `ServiceLabels.compute_mechanism` defaults to `ComputeMechanism.KUBERNETES`
- `ServiceLabels.namespace` remains functional (now optional, defaults to `""`)
- `ServiceLabels.pod` and `ServiceLabels.node` remain unchanged

### Explicit Migration (Optional, Recommended)

For clarity in multi-platform deployments, explicitly set `compute_mechanism`:

```python
# Before (still works)
labels = ServiceLabels(service="checkout", namespace="prod", pod="checkout-abc")

# After (explicit, recommended in mixed environments)
labels = ServiceLabels(
    service="checkout",
    namespace="prod",
    pod="checkout-abc",
    compute_mechanism=ComputeMechanism.KUBERNETES,
)
```

### New Fields for Non-K8s Targets

For serverless or VM targets, use the new fields:

```python
labels = ServiceLabels(
    service="payment-handler",
    compute_mechanism=ComputeMechanism.SERVERLESS,
    resource_id="arn:aws:lambda:us-east-1:123456789:function:payment-handler",
    platform_metadata={"runtime": "python3.12", "memory_mb": 512},
)
```

### Detection Behavior Changes

| Behavior | KUBERNETES | SERVERLESS |
|----------|-----------|-----------|
| eBPF telemetry | ✅ Available | ❌ Gracefully degraded |
| Memory pressure alerts | ✅ Active | ❌ Exempt (InvocationError surges monitored instead) |
| Cold-start latency suppression | N/A | ✅ 15-second suppression window |

### Cloud Operator Selection

Install optional dependencies for your cloud provider:

```bash
# AWS (ECS, EC2 ASG, Lambda)
pip install sre-agent[aws]

# Azure (App Service, Functions)
pip install sre-agent[azure]
```

The `CloudOperatorRegistry` automatically detects installed SDKs at bootstrap.
