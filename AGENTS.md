# Multi-Agent Ecosystem (AGENTS.md)

This document defines the overarching AI Agent ecosystem within this repository. While the primary focus is the **Autonomous SRE Agent**, this system is designed to operate in a shared, multi-agent environment where different specialized AI agents orchestrate distinct domains of the infrastructure.

To prevent agents from creating conflicting states (e.g., an SRE agent resolving a latency issue by scaling up, while a FinOps agent simultaneously resolves a cost alert by scaling down), all agents adhere to strict coordination protocols defined in the Orchestration Layer.

---

## 1. The Autonomous SRE Agent (Primary)

The core agent built and maintained within this repository. 

*   **Role:** Site Reliability / Infrastructure Health
*   **Mission:** Detect, diagnose, and remediate infrastructure incidents (OOM kills, high latency, errors, disk exhaustion) to minimize Mean Time to Recovery (MTTR).
*   **Operating Scope:** 
    *   Kubernetes Pods, Deployments, StatefulSets
    *   GitOps Repositories (ArgoCD / Flux)
    *   Certificate Managers
*   **Required Permissions:** 
    *   `kubectl` `restart`, `scale`, `patch` on specific namespaces.
    *   Write access to Infrastructure Git Repositories (to generate Revert PRs).
*   **Conflict Priority Level:** **Medium (Level 2)** 
    *   SRE actions supersede Cost/FinOps actions.
    *   SRE actions yield to Security/SecOps actions.

---

## 2. The Autonomous SecOps Agent (Hypothetical / External)

A specialized agent focused entirely on cluster and application security.

*   **Role:** Security Operations / Threat Response
*   **Mission:** Detect anomalous access patterns, unauthorized privilege escalations, and known CVE exploitations; execute immediate quarantines.
*   **Operating Scope:**
    *   Node cordoning / taint application
    *   Network Policy enforcement (isolation)
    *   IAM Role / ServiceAccount revokation
*   **Conflict Priority Level:** **High (Level 1 - Override)**
    *   If the SecOps Agent requires a lock on a Node to quarantine it, it will preempt or deny any lock request from the SRE Agent attempting to schedule pods on that node.

---

## 3. The Autonomous FinOps Agent (Hypothetical / External)

A specialized agent optimizing infrastructure for cost-efficiency.

*   **Role:** Cloud Cost Optimization
*   **Mission:** Identify over-provisioned resources and safe down-scaling opportunities during off-peak hours to minimize cloud spend.
*   **Operating Scope:**
    *   Horizontal Pod Autoscaler (HPA) min/max tuning
    *   Cluster Autoscaler node pool scaling
    *   Volume detachment/resizing
*   **Conflict Priority Level:** **Low (Level 3)**
    *   If a service is currently under active load/incident investigation by the SRE Agent, the FinOps Agent is denied locks to scale down resources. Reliability always trumps Cost during an active incident.

---

## Agent Coordination Guidelines

All agents within this ecosystem MUST adhere to the **Multi-Agent Lock Protocol** (backed by Redis/etcd).

1.  **Mutual Exclusion (Mutex):** Before an agent executes any write action on a Kubernetes Resource or Git Repository, it must acquire an exclusive lock via the Coordinator.
2.  **State Observation:** Before acquiring a lock, an agent must verify that the resource is not currently in a "cooling off" period from another agent's recent action (preventing oscillation loops).
3.  **Human Supremacy:** Any human operator possessing elevated credentials can override agent locks, forcibly release them, or trigger the global agent **Kill Switch**. When human intervention is detected on a resource, all autonomous agents immediately back off and yield control.
