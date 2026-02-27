# Contributing to the Autonomous SRE Agent

First off, thank you for considering contributing to the Autonomous SRE Agent!

Site Reliability Engineering is built on a culture of shared responsibility and rigorous safety. As an AI agent capable of executing production infrastructure actions autonomously, our contribution standards are exceptionally strict, prioritizing safety, determinism, and auditability above all else.

## 1. Safety First (The Golden Rule)

Before writing any code, you must read the **[Agent Constitution](.specify/memory/constitution.md)**. 

### Non-Negotiable Requirements for PRs:
*   **No new remediation action** can be added without an accompanying unit test proving its hard-coded blast radius limit works (e.g., "cannot restart > 20% of pods").
*   **No direct API calls** to standard infrastructure unless it interacts exclusively with an idempotent `Port` interface. 
*   **No raw LLM logic** driving actions without RAG grounding and secondary evidence validation.

## 2. Development Workflow

We practice Spec-Driven Development. Our `openspec` directory serves as the ultimate source of truth for all agent behaviors.

1.  **Read the Specs:** Check `openspec/changes/autonomous-sre-agent/specs/` to find the scenario you are implementing or modifying.
2.  **Pass the Tests:** Write your test *first* to match the `WHEN`/`THEN` scenario defined in the markdown spec.
3.  **Local Execution:** Run the full test suite locally using `pytest` inside your virtual environment before pushing code.

## 3. Creating a Pull Request (PR)

When submitting a PR, ensure the following checklist is complete:
- [ ] **Specs Updated:** If modifying behavior, the relevant `.md` spec in `openspec` must be updated *before* the code is merged.
- [ ] **Documentation Updated:** If you added a new component or altered the architecture, update the corresponding file in the `docs/` folder.
- [ ] **Tests Passing:** Unit tests and local integration tests must cleanly pass.
- [ ] **Linting:** Your code complies with `flake8` and `black` (for Python) or `eslint` (for TS/JS).

### PR Title & Description
Please use [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/).
*   *Feat: Add new Redis lock coordinator*
*   *Fix: Prevent infinite loops in anomaly detector*
*   *Docs: Update intelligence layer diagrams*

## 4. Documentation Standards ("Docs as Code")

We maintain our documentation with the same rigor as our application code.

*   **Architecture changes** must be reflected in `docs/architecture/` using Meridian (Mermaid.js) diagrams. No external proprietary diagram formats (e.g., Visio, Lucidchart) are allowed for core system documentation.
*   **Keep it Evergreen:** If a document is out of date and redundant, open a PR to delete it. We prefer "Minimum Viable Documentation" over stale noise.

---

*Thank you for helping us make autonomous operations safer and more reliable!*
