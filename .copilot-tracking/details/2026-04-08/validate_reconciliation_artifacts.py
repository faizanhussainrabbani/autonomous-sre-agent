#!/usr/bin/env python3
"""Structured validator for persistence architecture reconciliation artifacts.

This validator enforces semantic checks that are stronger than header-presence
grep checks. It verifies:

* C-01 through C-06 gate completeness (decision + rationale fields)
* Quantitative split-gate completeness
* Contract enum alignment for provider and compute_mechanism
* Conditional Kubernetes/non-Kubernetes coordination key formats
* Cross-artifact reference integrity for core planning files
* Reproducibility metadata fields in the Plan Validator trace artifact
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


REQUIRED_COMPUTE_MECHANISMS = {
    "KUBERNETES",
    "SERVERLESS",
    "VIRTUAL_MACHINE",
    "CONTAINER_INSTANCE",
}

REQUIRED_PROVIDERS = {"kubernetes", "aws", "azure"}


def _read(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Missing required artifact: {path}")
    return path.read_text(encoding="utf-8")


def _extract_dash_enum_block(text: str, key: str) -> set[str]:
    pattern = re.compile(
        rf"{re.escape(key)}:\n\s+type:\s+string\n\s+enum:\n((?:\s+-\s+[^\n]+\n)+)"
    )
    match = pattern.search(text)
    if not match:
        return set()
    values = set()
    for raw in match.group(1).splitlines():
        line = raw.strip()
        if line.startswith("-"):
            values.add(line.lstrip("-").strip())
    return values


def _extract_inline_enum_blocks(text: str, key: str) -> list[set[str]]:
    pattern = re.compile(
        rf"{re.escape(key)}:\n\s+type:\s+string\n\s+enum:\s*\[([^\]]+)\]"
    )
    blocks = []
    for raw in pattern.findall(text):
        blocks.append({v.strip() for v in raw.split(",") if v.strip()})
    return blocks


def _validate_gate_sections(research_text: str, errors: list[str]) -> None:
    gate_matches = list(re.finditer(r"^###\s+(C-\d{2}):", research_text, re.MULTILINE))
    if len(gate_matches) != 6:
        errors.append(
            f"Expected 6 clarification gates (C-01..C-06), found {len(gate_matches)}"
        )
        return

    expected = [f"C-{idx:02d}" for idx in range(1, 7)]
    found = [m.group(1) for m in gate_matches]
    if found != expected:
        errors.append(
            f"Clarification gate ordering mismatch. Expected {expected}, found {found}"
        )

    for idx, match in enumerate(gate_matches):
        start = match.start()
        end = gate_matches[idx + 1].start() if idx + 1 < len(gate_matches) else len(research_text)
        section = research_text[start:end]
        gate = match.group(1)
        if "* Decision:" not in section:
            errors.append(f"{gate} is missing a Decision entry")
        if "* Rationale:" not in section:
            errors.append(f"{gate} is missing a Rationale entry")


def _validate_split_gates(research_text: str, errors: list[str]) -> None:
    match = re.search(r"^####\s+Selected split gates\n\n((?:\*\s+.+\n)+)", research_text, re.MULTILINE)
    if not match:
        errors.append("Selected split gates section missing or malformed")
        return

    lines = [line.strip() for line in match.group(1).splitlines() if line.strip().startswith("*")]
    if len(lines) < 6:
        errors.append(f"Expected at least 6 split-gate entries, found {len(lines)}")

    for line in lines:
        if re.search(r"\d", line) is None:
            errors.append(f"Split gate missing numeric threshold: {line}")


def _validate_contracts(outbox_text: str, coordination_text: str, errors: list[str]) -> None:
    provider_enum = _extract_dash_enum_block(outbox_text, "provider")
    if provider_enum != REQUIRED_PROVIDERS:
        errors.append(
            "Outbox contract provider enum mismatch. "
            f"Expected {sorted(REQUIRED_PROVIDERS)}, found {sorted(provider_enum)}"
        )

    outbox_compute = _extract_dash_enum_block(outbox_text, "compute_mechanism")
    if outbox_compute != REQUIRED_COMPUTE_MECHANISMS:
        errors.append(
            "Outbox contract compute_mechanism enum mismatch. "
            f"Expected {sorted(REQUIRED_COMPUTE_MECHANISMS)}, found {sorted(outbox_compute)}"
        )

    inline_compute_blocks = _extract_inline_enum_blocks(coordination_text, "compute_mechanism")
    if not inline_compute_blocks:
        errors.append("Coordination contract compute_mechanism enum blocks missing")
    else:
        for index, block in enumerate(inline_compute_blocks, start=1):
            if block != REQUIRED_COMPUTE_MECHANISMS:
                errors.append(
                    "Coordination contract compute_mechanism enum mismatch in block "
                    f"{index}. Expected {sorted(REQUIRED_COMPUTE_MECHANISMS)}, found {sorted(block)}"
                )

    required_key_tokens = [
        "lock_key_format:",
        "  kubernetes: lock:{namespace}:{resource_type}:{resource_name}",
        "  non_kubernetes: lock:{provider}:{compute_mechanism}:{resource_id}",
        "cooldown_key_format:",
        "  kubernetes: cooldown:{namespace}:{resource_type}:{resource_name}",
        "  non_kubernetes: cooldown:{provider}:{compute_mechanism}:{resource_id}",
    ]
    for token in required_key_tokens:
        if token not in coordination_text:
            errors.append(f"Coordination key format token missing: {token}")


def _validate_reference_integrity(
    root: Path,
    details_text: str,
    quickstart_text: str,
    planning_log_text: str,
    errors: list[str],
) -> None:
    reference_pattern = re.compile(r"\.copilot-tracking/[A-Za-z0-9._/\-]+")
    combined_text = "\n".join([details_text, quickstart_text, planning_log_text])
    references = sorted(set(reference_pattern.findall(combined_text)))

    for reference in references:
        normalized_reference = reference.rstrip(".,);:")
        ref_path = root / normalized_reference
        if not ref_path.exists():
            errors.append(f"Broken artifact reference: {normalized_reference}")


def _validate_trace_fields(trace_text: str, errors: list[str]) -> None:
    required_fields = [
        "## Replay Command",
        "## Determinism Notes",
        "## Artifact Checksums",
    ]
    for field in required_fields:
        if field not in trace_text:
            errors.append(f"Plan Validator trace missing reproducibility field: {field}")


def main() -> int:
    script_path = Path(__file__).resolve()
    repo_root = script_path.parents[3]

    research_path = repo_root / ".copilot-tracking/research/2026-04-08/persistence-architecture-reconciliation-research.md"
    details_path = repo_root / ".copilot-tracking/details/2026-04-08/persistence-architecture-reconciliation-details.md"
    quickstart_path = repo_root / ".copilot-tracking/details/2026-04-08/persistence-architecture-reconciliation-quickstart.md"
    planning_log_path = repo_root / ".copilot-tracking/plans/logs/2026-04-08/persistence-architecture-reconciliation-log.md"
    trace_path = repo_root / ".copilot-tracking/plans/logs/2026-04-08/persistence-architecture-reconciliation-plan-validator-trace.md"
    outbox_path = repo_root / ".copilot-tracking/details/2026-04-08/contracts/incident-outbox-contract.yaml"
    coordination_path = repo_root / ".copilot-tracking/details/2026-04-08/contracts/coordination-state-contract.yaml"

    errors: list[str] = []

    try:
        research_text = _read(research_path)
        details_text = _read(details_path)
        quickstart_text = _read(quickstart_path)
        planning_log_text = _read(planning_log_path)
        trace_text = _read(trace_path)
        outbox_text = _read(outbox_path)
        coordination_text = _read(coordination_path)
    except FileNotFoundError as exc:
        print(json.dumps({"status": "failed", "errors": [str(exc)]}, indent=2))
        return 1

    _validate_gate_sections(research_text, errors)
    _validate_split_gates(research_text, errors)
    _validate_contracts(outbox_text, coordination_text, errors)
    _validate_reference_integrity(
        repo_root,
        details_text,
        quickstart_text,
        planning_log_text,
        errors,
    )
    _validate_trace_fields(trace_text, errors)

    if errors:
        print(json.dumps({"status": "failed", "error_count": len(errors), "errors": errors}, indent=2))
        return 1

    result = {
        "status": "passed",
        "checks": {
            "clarification_gates": "passed",
            "split_gates": "passed",
            "contract_enums": "passed",
            "coordination_key_formats": "passed",
            "reference_integrity": "passed",
            "trace_reproducibility_fields": "passed",
        },
    }
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
