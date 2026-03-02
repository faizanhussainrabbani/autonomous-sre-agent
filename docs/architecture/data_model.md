# Canonical Data Model

The SRE Agent uses a set of standard, strictly typed data structures (implemented as Python `dataclasses` in `canonical.py`) for all internal inter-component messaging. This ensures complete provenance tracking and fulfills Constitution Principle V (Observable & Auditable).

Below are the core domain entities:

## 1. Incident

Represents a confirmed anomaly that requires agent investigation.

*   `id` (UUID): Unique identifier for the incident.
*   `source` (String): The observability system that generated the alert (e.g., "Prometheus", "eBPF/Cilium").
*   `type` (String): Must match one of the 5 supported [Incident Taxonomy](incident_taxonomy.md) types.
*   `severity` (Enum): `SEV_1`, `SEV_2`, `SEV_3`, `SEV_4`.
*   `state` (Enum): The current lifecycle phase of this incident (detailed sub-states in `state_incident_model.md`):
    *   `DETECTED`: Alert received, awaiting diagnosis.
    *   `DIAGNOSING`: Intelligence Layer is gathering context and reasoning.
    *   `DIAGNOSED`: Root cause established by Intelligence layer.
    *   `ACQUIRING_LOCK`: Waiting for distributed mutex from Governance layer.
    *   `BLOCKED`: Lock denied (preempted or cooling down).
    *   `REMEDIATING`: Action layer is currently applying a fix.
    *   `VERIFYING`: Action applied, waiting for metrics to normalize.
    *   `ROLLING_BACK`: Metrics degraded, reverting action.
    *   `RESOLVED`: Remediation verified successful.
    *   `ESCALATED`: Agent exceeded capability/confidence and alerted humans.
*   `detected_at` (Timestamp): When the anomaly was triggered.
*   `diagnosed_at` (Timestamp): When the diagnosis was finalized.
*   `resolved_at` (Timestamp): When the incident was successfully mitigated.
*   `escalated_at` (Timestamp): When the incident was escalated to a human.
*   `telemetry_context` (Dict): Snapshot of relevant metrics/traces at the time of detection.

## 2. Diagnosis

The output of the Intelligence Layer (RAG pipeline), attaching reasoning to an `Incident`.

*   `incident_id` (UUID): Foreign key mapping to the parent `Incident`.
*   `hypothesis` (String): Natural language explanation of the inferred root cause.
*   `confidence_score` (Float 0.0-1.0): The aggregate certainty of the diagnosis. Must exceed the Tier 1 Guardrail threshold to act.
*   `evidence_citations` (List[String]): Document IDs or URLs to historical post-mortems and runbooks from the KB that support the hypothesis.
*   `rag_similarity_scores` (List[Float]): The vector distance metrics showing how closely the current incident telemetry matches the cited evidence.

## 3. RemediationAction

A concrete, executable step proposed to resolve an `Incident`.

*   `id` (UUID): Unique identifier for the remediation action.
*   `action_type` (Enum): Must correspond to approved actions (e.g., `POD_RESTART`, `HPA_SCALE`, `GITOPS_REVERT`).
*   `status` (Enum): Lifecycle stage (e.g., `PROPOSED`, `APPROVED`, `EXECUTING`, `COMPLETED`, `ROLLED_BACK`).
*   `target_resource` (String): The Kubernetes/Cloud resource URI (e.g., `deployment/cart-service`, namespace `prod`).
*   `rollback_path` (String): Explicit definition of how to reverse this action if metrics degrade.
*   `blast_radius_estimate` (Dict):
    *   `affected_pods_percentage` (Float): e.g., 20.0 (20%)
    *   `dependent_services` (List[String]): Derived from the Dependency Graph.

## 4. AuditEntry

An immutable record of every state change or decision made by the agent, required for compliance.

*   `incident_id` (UUID): Foreign key mapping to the parent `Incident`.
*   `timestamp` (Timestamp): When the action occurred.
*   `agent_phase` (Enum): The authorized runtime Phase of the agent at the time (`OBSERVE`, `ASSIST`, `AUTONOMOUS`).
*   `action` (String): Description of the evaluation, lock acquisition, or API call.
*   `outcome` (String): Success, failure, or denial reason.
*   `provenance_chain` (List[UUID]): Links the Action -> Diagnosis -> Incident to prove exactly *why* a given API call was made.
