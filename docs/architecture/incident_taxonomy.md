# Incident Taxonomy

**Status:** DRAFT
**Version:** 1.0.0

The Autonomous SRE Agent is constrained to 5 well-understood incident types (Constitution Principle IV). This document serves as the single source of truth for these incidents, defining their detection signals, diagnostics, remediation actions, and safety boundaries.

| Incident Type | Detection Signals | Diagnostic Evidence Pattern | Approved Remediation | Blast Radius Limits | Rollback Strategy |
|---------------|-------------------|-----------------------------|-----------------------|---------------------|-------------------|
| **OOM Kills** | Memory usage >95%, eBPF OOM events, `cgroup` limits hit | High memory utilization without corresponding traffic increase, historical leak patterns | Pod restart | Max 20% of deployment replicas restarted at once | N/A (Restart is usually safe; alert if fast failure loop) |
| **Traffic Spikes** | Request rates >3\u03c3 baseline, Latency spikes, Thread exhaustion | Sudden ingress volume increase, CPU/Mem scaling proportionally | Horizontal Pod Autoscaling (HPA) limit increase, manual scale-up | Max 2x current replicas, capped by namespace quota | Scale down after cooling period (e.g. 1 hour) |
| **Deploy Regressions** | Elevated error rates (5xx), Trace latency degradation | Correlation between error onset and recent ArgoCD sync/Git commit | GitOps Revert via ArgoCD / `kubectl.kubernetes.io/restartedAt` | Single deployment only | If revert fails, escalate immediately |
| **Cert Expiry** | Cert metadata (validity <7 days), TLS handshake failures | Expired/expiring certificate listed in `cert-manager` or Ingress logs | Certificate rotation (cert-manager webhook trigger) | Single namespace/Ingress controller | Re-apply previous Secret if new cert is invalid |
| **Disk Exhaustion** | Disk usage >85%, positive growth derivative | Constant space increase in specific volume mounts, specific log file growth | Log rotation/truncation, PVC size expansion | Max +50% PVC size, single statefulset | Cannot shrink PVC; alert humans if growth persists |
