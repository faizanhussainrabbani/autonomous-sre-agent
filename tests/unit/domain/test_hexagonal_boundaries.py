"""Hexagonal architecture boundary checks for domain and ports layers."""

from __future__ import annotations

import ast
from pathlib import Path


def _collect_adapter_import_violations(layer_glob: str) -> list[str]:
    repo_root = Path(__file__).resolve().parents[3]
    violations: list[str] = []

    for file_path in repo_root.glob(layer_glob):
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(file_path))

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("sre_agent.adapters"):
                        rel = file_path.relative_to(repo_root)
                        violations.append(f"{rel}:{node.lineno} import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module.startswith("sre_agent.adapters"):
                    rel = file_path.relative_to(repo_root)
                    violations.append(f"{rel}:{node.lineno} from {module}")

    return violations


def test_domain_and_ports_do_not_import_adapters() -> None:
    """Domain and ports layers must not import adapter modules directly."""
    domain_violations = _collect_adapter_import_violations("src/sre_agent/domain/**/*.py")
    ports_violations = _collect_adapter_import_violations("src/sre_agent/ports/**/*.py")
    violations = domain_violations + ports_violations

    assert not violations, "\n".join(violations)
