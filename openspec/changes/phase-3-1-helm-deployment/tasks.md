## HELM-001 — Chart Structure (Critical Path)

- [ ] 1.1 Create `charts/sre-agent/Chart.yaml` with metadata, version, dependencies
- [ ] 1.2 Create `charts/sre-agent/values.yaml` with all configurable settings
- [ ] 1.3 Create `charts/sre-agent/values.schema.json` for validation
- [ ] 1.4 Create `charts/sre-agent/templates/deployment.yaml`
- [ ] 1.5 Create `charts/sre-agent/templates/service.yaml`
- [ ] 1.6 Create `charts/sre-agent/templates/configmap.yaml` for agent configuration
- [ ] 1.7 Create `charts/sre-agent/templates/serviceaccount.yaml` and `rbac.yaml`
- [ ] 1.8 Create `charts/sre-agent/templates/hpa.yaml` (optional horizontal pod autoscaler)

## HELM-002 — RBAC Templates (High)

- [ ] 2.1 Create phase-specific RBAC: Observe (read-only cluster role)
- [ ] 2.2 Create phase-specific RBAC: Assist (read + limited write for approved actions)
- [ ] 2.3 Create phase-specific RBAC: Autonomous (read + write for all remediation types)
- [ ] 2.4 RBAC selection via `values.yaml` `phase` setting

## HELM-003 — Configuration Injection (Medium)

- [ ] 3.1 Map values.yaml to environment variables and ConfigMap entries
- [ ] 3.2 Secret references (external-secrets-operator pattern or direct K8s Secret)
- [ ] 3.3 Provider-specific configuration blocks (telemetryProvider, cloudProvider)

## HELM-004 — Testing (High)

- [ ] 4.1 `helm lint` passes
- [ ] 4.2 `helm template` renders valid YAML for all provider combinations
- [ ] 4.3 `ct install` (Chart Testing) on kind/k3d cluster
- [ ] 4.4 Verify agent health check passes after `helm install`
