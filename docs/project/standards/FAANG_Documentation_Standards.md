# FAANG Documentation Standards vs. Our Repository Structure

**Status:** APPROVED
**Version:** 1.1.0

This document synthesizes research on how top-tier technology companies (like Google, Uber, and others in the FAANG sphere) structure their engineering documentation, and compares those standards directly against the structure we have built for the Autonomous SRE Agent.

> [!NOTE]
> This document is a **companion** to [`engineering_standards.md`](../project/standards/engineering_standards.md), which defines the detailed coding, testing, and architectural standards. This document focuses on the *organizational structure* of our documentation and how it aligns with industry best practices.

## 1. How FAANG Does Documentation (Industry Standards)

Top-tier tech companies separate documentation into distinct categories based on the **lifecycle** of the software and the **audience** reading it. 

### A. The "Design Doc" or "RFC" (The "Why" and "What")
Before code is written, companies like Google and Uber rely heavily on **Design Docs** or **RFCs (Request for Comments)**.
*   **Purpose:** To outline technical proposals, justify decisions, discuss trade-offs, and solicit feedback.
*   **Standard Structure (Google/Uber):**
    1.  **Context/Motivation:** Why are we doing this? (Quantified if possible).
    2.  **Goals & Non-Goals:** What is explicitly out of scope?
    3.  **Proposed Design/Architecture:** The core solution.
    4.  **Alternatives Considered:** Why were other options rejected?
    5.  **Engineering Impact:** Security, performance, dependencies.
*   **Lifecycle:** These are "living documents" during the planning phase, but eventually become historical records of *why* a system was built a certain way.

### B. Repository & Evergreen Documentation (The "How")
Once a system is built, the documentation shifts from "proposals" to "evergreen references" stored directly alongside the code in Git repositories. 
*   **Purpose:** To provide a reliable, easily structured guide for onboarding, operations, and continued development.
*   **Standard Categorization:**
    *   **Architecture Docs:** Overall system design, component diagrams (often using "Diagrams as Code" like Mermaid).
    *   **Operations / Runbooks:** Deployment guides, incident response, SLO definitions.
    *   **Security:** Threat models, access control paradigms.
    *   **API / Integration Docs:** Contracts for how other teams interact with the service.

### C. Core Principles Emphasized by FAANG
1.  **Documentation as Code:** Keeping docs in version control (Git) using Markdown ensures they evolve alongside the codebase and are subject to PR reviews.
2.  **Minimum Viable Documentation:** Delete dead documentation. A small amount of accurate documentation is better than volumes of outdated "noise."
3.  **Logical Hierarchy:** Breaking monolithic documentation into categorized folders (Security, Operations, Architecture) rather than massive single files.

---

## 2. Comparing Our Structure to FAANG Standards

We have structured the Autonomous SRE Agent repository utilizing two primary folders: `openspec/` and `docs/`. Here is how this aligns with the industry standard.

### The `openspec/` Folder = The FAANG Design Doc / RFC
Our `openspec/` directory perfectly mirrors the FAANG Design Doc pattern. 
*   **`openspec/.../design.md` & `proposal.md`:** These files match the Google/Uber templates exactly. They contain the Context, Goals/Non-Goals, Decisions (with alternatives considered), and Risks.
*   **`openspec/.../specs/`:** This breaks down the high-level design into highly granular, testable scenarios (Behavior-Driven Development). 
*   **FAANG Alignment:** **Excellent.** We have successfully separated the *intent and strict requirements* into a dedicated, formalized specification folder.

### The `docs/` Folder = The FAANG Evergreen Repository Docs
Our recent restructuring of the `docs/` folder aligns directly with how mature engineering teams organize long-term repository knowledge. We broke a flat, cluttered structure into logical domains:
*   **`docs/architecture/` (and `layers/`)**: Contains the high-level stack down to deep-dive Mermaid diagrams. FAANG strongly encourages storing architecture as Markdown/Mermaid in Git.
*   **`docs/operations/`**: Houses Runbooks, SLOs, and Error Budgets. This mirrors Google's SRE book practices for operational readiness.
*   **`docs/security/`**: Centralizes Threat Models and Safety Guardrails.
*   **`docs/api/`**: Consolidates API contracts for external interaction.
*   **`docs/project/`**: Contains onboarding and roadmapping.

### "Minimum Viable Documentation" (The Cleanup)
By deleting the massive 49KB `Critical_Analysis...md` file and the redundant `Technical_Analysis.md` file earlier, we adhered to the FAANG principle of deleting outdated or redundant documentation to prevent "drift." The specifications live in `openspec`, and the evergreen reference lives in `docs`.

## Conclusion

Our current organizational setup is **highly compliant** with top-tier industry standards. 

1.  We have robust, structured **Proposals/RFCs** (`openspec`).
2.  We have living, well-categorized **Architecture and Operational references** (`docs`).
3.  We are treating **Documentation as Code** (Markdown + Mermaid in Git).
4.  We have eliminated redundant bloat.
5.  We maintain **Architectural Decision Records** in `docs/project/ADRs/` for decision traceability.
6.  We have a comprehensive **Changelog** at `docs/project/CHANGELOG.md`.

The separation of concerns between *what we are proposing to build* (specs) and *how the system currently works/is operated* (docs) is the exact hallmark of a mature engineering organization.

## Related Documents

- [Engineering Standards & Code Organization](../project/standards/engineering_standards.md) — Coding, testing, and architectural standards
- [CONTRIBUTING.md](../../CONTRIBUTING.md) — Contributor guidelines
- [ADR Records](../project/ADRs/) — Architectural decisions
- [Testing Strategy](../testing/testing_strategy.md) — Comprehensive test plan
