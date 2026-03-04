"""
Unit tests for the SRE Agent CLI (Click) — AC-5.x, operator interface.

Tests validate the Click command group (cli), validate command,
status command, and run command using ``CliRunner``.
"""

from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from click.testing import CliRunner

from sre_agent.api.cli import cli


@pytest.fixture
def runner() -> CliRunner:
    """Click CliRunner for invoking CLI commands."""
    return CliRunner()


@pytest.fixture
def valid_config_path(tmp_path: Path) -> Path:
    """Write a minimal valid agent.yaml to a temp directory."""
    config_file = tmp_path / "agent.yaml"
    config_file.write_text(
        "telemetry_provider: otel\n"
        "cloud_provider: none\n"
        "log_level: INFO\n"
    )
    return config_file


@pytest.mark.unit
class TestCliGroup:
    """Test the top-level CLI group."""

    def test_cli_help_exits_zero(self, runner: CliRunner) -> None:
        """CLI --help exits with code 0."""
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "Autonomous SRE Agent" in result.output

    def test_cli_unknown_command_fails(self, runner: CliRunner) -> None:
        """Unknown subcommand prints error."""
        result = runner.invoke(cli, ["not-a-command"])
        assert result.exit_code != 0


@pytest.mark.unit
class TestStatusCommand:
    """Test the status subcommand."""

    def test_status_prints_version(self, runner: CliRunner) -> None:
        """Status command outputs version info."""
        result = runner.invoke(cli, ["status"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output

    def test_status_prints_phase(self, runner: CliRunner) -> None:
        """Status command outputs current phase."""
        result = runner.invoke(cli, ["status"])
        assert "Phase 1.5" in result.output


@pytest.mark.unit
class TestValidateCommand:
    """Test the validate subcommand."""

    def test_validate_requires_config_option(self, runner: CliRunner) -> None:
        """Validate fails without --config."""
        result = runner.invoke(cli, ["validate"])
        assert result.exit_code != 0

    @patch("sre_agent.api.cli.AgentConfig")
    def test_validate_valid_config_succeeds(
        self,
        mock_agent_config: MagicMock,
        runner: CliRunner,
        valid_config_path: Path,
    ) -> None:
        """Validate with valid config exits 0."""
        mock_instance = MagicMock()
        mock_instance.validate.return_value = []
        mock_instance.telemetry_provider = "otel"
        mock_instance.cloud_provider = "none"
        mock_instance.log_level = "INFO"
        mock_agent_config.from_yaml.return_value = mock_instance

        result = runner.invoke(cli, ["validate", "--config", str(valid_config_path)])
        assert result.exit_code == 0
        assert "✅" in result.output

    @patch("sre_agent.api.cli.AgentConfig")
    def test_validate_invalid_config_exits_one(
        self,
        mock_agent_config: MagicMock,
        runner: CliRunner,
        valid_config_path: Path,
    ) -> None:
        """Validate with invalid config exits 1."""
        mock_instance = MagicMock()
        mock_instance.validate.return_value = ["Missing telemetry_provider"]
        mock_agent_config.from_yaml.return_value = mock_instance

        result = runner.invoke(cli, ["validate", "--config", str(valid_config_path)])
        assert result.exit_code == 1
        assert "❌" in result.output


@pytest.mark.unit
class TestRunCommand:
    """Test the run subcommand."""

    def test_run_requires_config(self, runner: CliRunner) -> None:
        """Run fails without --config."""
        result = runner.invoke(cli, ["run"])
        assert result.exit_code != 0

    def test_run_without_dry_run_shows_not_implemented(
        self,
        runner: CliRunner,
        valid_config_path: Path,
    ) -> None:
        """Run without dry-run shows Phase 2 notice."""
        result = runner.invoke(cli, ["run", "--config", str(valid_config_path)])
        assert result.exit_code == 0
        assert "Phase 2" in result.output or "not yet implemented" in result.output
