# Live Demos Analysis Report
**Document Owner:** Engineering
**Status:** DRAFT

## 1. Introduction
This report provides a comprehensive review of the interactive terminal demonstration scripts (`live_demo_*.py`) available in the `scripts/` directory. These demos act as functional integration tests, stakeholder showcases, and interactive educational sequences demonstrating the capabilities of the **Autonomous SRE Agent**. 

This document will first catalog the intention and purpose of every demo script, and then critically evaluate them against the documented architectural features (Phase 1 through Phase 2.3) of the project.

---

## 2. Demo Inventory & Documented Purpose

| Demo Identifier | File Name | Primary Purpose / Narrative | Focus Area |
| :--- | :--- | :--- | :--- |
| **Demo 2** | `live_demo_cascade_failure.py` | Simulates a realistic Black Friday flash-sale incident cascade (OOM -> 503 Surge -> API Latency). | Tests correlation and blast-radius tracing; multi-service dependency impact. |
| **Demo 3** | `live_demo_deployment_regression.py` | Simulates a bad Canary Deployment generating infrastructure fragility, including secondary failures and "LLM Disagreement" (Second-opinion validator). | Tests the Second-Opinion RAG validator constraint and exposed Circuit Breaker logic tripping due to operator failures. |
| **Demo 4** | `live_demo_localstack_aws.py` | Orchestrates mocked AWS infrastructure endpoints using LocalStack to showcase the Phase 1.5 cloud operator layer (ECS, Lambda, EC2 ASG). | Showcases deterministic execution of real AWS SDK API calls to modify cluster capacities autonomously. |
| **Demo 5** | `live_demo_http_server.py` | Boots up the background FastAPI application server and drives mock incident scenarios against it. | True End-to-End validation of the HTTP pipeline, Router layers, and Dependency Injection in a self-contained runtime. |
| **Demo 6** | `live_demo_http_optimizations.py` | Extended HTTP Demo testing the Phase 2.2 Token Optimizations in a live HTTP server loop. | Mathematically proves the utility of cross-encoder reranking, evidence compression (TLDRify), and semantic caching loops. |
| **Demo 7** | `live_demo_localstack_incident.py` | LocalStack End-to-End Incident Response handling. Provisions a vulnerable Lambda, sets off a CloudWatch Alarm, routes it through SNS -> Bridge -> SRE Agent webhook. | Validates true real-world network routing using Cloud Provider abstractions with an explicit LLM-powered root cause audit trail. |
| **Demo 8** | `live_demo_ecs_multi_service.py` | ECS alternative to Lambda (different Multi-Service cascade). Proves severity override APIs and dynamic signal ingestion. | Validates stateful containerized task metrics, `correlated_signals` population, and the operator-level HITL Severity downgrade API. |
| **Demo 9** | `live_demo_cloudwatch_enrichment.py` | Simulates Alert Enrichment via Phase 2.3. Pushes generic AWS Metric & Log anomalies to LocalStack and displays the `AlertEnricher` extracting and transforming them. | Proves pre-diagnosis dynamic context fetching preventing token waste and guaranteeing incident freshness. |
| **Demo 10** | `live_demo_eventbridge_reaction.py` | Simulates stateless EventBridge Webhooks transmitting system infrastructure state changes directly into canonical incident timelines. | Validates HTTP-level native integration with AWS EventBridge rules, bridging structural Cloud Provider state models to generic Domain types. |

---

## 3. Critical Review: Alignment with Application Functionality

To gauge the efficacy of these demos, we must measure how accurately they cover the known completed domains of the architecture.

### 3.1 What the Demos Showcase Successfully (Strengths)✅
1. **Full-Spectrum Hexagonal Verification:** The demos successfully interact with almost the entire Hexagonal architecture, crossing the API/REST border (FastAPI HTTP Server) down through adapter/localstack bridging.
2. **Robust RAG Validation:** Demos 2, 3, 6, and 7 heavily drill the RAG mechanism (Intelligence Phase 2). Specifically, Demo 6 mathematically illustrates token optimizations, proving the specific value of Phase 2.2 engineering components.
3. **External Infrastructure Agnosticism:** With LocalStack deeply embedded into Demos 4, 7, 8, 9, the tool is strictly verified to survive independent execution against unmocked HTTP servers simulating production AWS regions—this closes the gap traditionally filled by weak unit-test stubs.
4. **Cloud Portability Validation:** Demos 4, 7, and 8 ensure that the Cloud Operators defined in Phase 1.5 actively run commands like `scale_capacity()` over standard synchronous networking bounds natively mapped to Async environments.

### 3.2 Feature Gaps & Demonstrability Issues (Weaknesses) ❌
1. **Missing Provider Coverage (Azure/K8s):** Every LocalStack infrastructure demo exclusively exercises the **AWS Cloud Operator adapters** (ECS, Lambda, EC2 ASG). Features like **Azure App Service** and **Azure Functions** constructed in Phase 1.5 are entirely missing from live demonstrability.
2. **"Demo 1" is Missing:** The numbering skips Demo 1. Given the focus of Demo 2 on "Flash Sale Cascade", it's implied that Demo 1 would likely be a simple Phase 1 basic Telemetry fetch/baseline test that isn't currently listed.
3. **Phase 3 Gap (Remediation & Safety):** As identified by the architectural review, Phase 3 (Remediation Actions, Saga Rollbacks, Multi-agent locking) is not implemented. Although the demos correctly *don't* mock something that doesn't exist, earlier Demos (Demo 4) title themselves "Remediation Operators", which actually just execute raw cloud scales rather than autonomous, plan-guided Domain Remediation loops.
4. **Agent Extensibility (Event Pub/Sub):** The `events/` internal Domain layer only utilizes the basic in-memory pub-sub. Currently, none of the demos hook an alternate event-bus (like Kafka) or highlight internal messaging apart from immediate HTTP/REST boundary resolution, hiding the power of the event-driven decoupling built into the domain layer.

### 4. Conclusion
The suite of `live_demo_*.py` applications is highly mature, effectively spanning across HTTP ingestion, AWS Telemetry, Token extraction, and multi-service Root Cause diagnostics. The focus is overwhelmingly AWS-centric—this is pragmatic given LocalStack’s utility, but leaves multi-cloud adapter integration largely untested outside the unit testing environment. Expanding demonstrations into Phase 3 domains or Azure deployments will guarantee full feature visualization.
