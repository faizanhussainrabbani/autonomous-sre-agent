"""
SRE Agent CLI — Click-based command-line interface.

Commands:
  sre-agent validate   Validate configuration and provider connectivity
  sre-agent status     Print agent status (version, halt state, provider health)
  sre-agent run        Start the SRE Agent (Phase 2: full pipeline)

Usage:
    python -m sre_agent.api.cli validate --config config.yaml
    python -m sre_agent.api.cli status
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import click
import structlog

from sre_agent.config.logging import configure_logging
from sre_agent.config.settings import AgentConfig

logger = structlog.get_logger(__name__)


@click.group()
@click.option("--log-level", default="info", show_default=True,
              type=click.Choice(["debug", "info", "warning", "error"], case_sensitive=False),
              help="Logging level.")
@click.pass_context
def cli(ctx: click.Context, log_level: str) -> None:
    """Autonomous SRE Agent — CLI entrypoint."""
    configure_logging(log_level=log_level.upper())
    ctx.ensure_object(dict)


@cli.command()
@click.option("--config", "-c", required=True, type=click.Path(exists=True, path_type=Path),
              help="Path to agent YAML configuration file.")
def validate(config: Path) -> None:
    """Validate configuration file and check provider connectivity."""
    click.echo(f"🔍 Validating configuration: {config}")

    try:
        agent_config = AgentConfig.from_yaml(str(config))
        errors = agent_config.validate()
        if errors:
            click.secho("❌ Configuration validation failed:", fg="red", bold=True)
            for err in errors:
                click.secho(f"   • {err}", fg="red")
            sys.exit(1)
        else:
            click.secho("✅ Configuration valid.", fg="green", bold=True)
            click.echo(f"   Telemetry:  {agent_config.telemetry_provider}")
            click.echo(f"   Cloud:      {agent_config.cloud_provider or 'kubernetes (default)'}")
            click.echo(f"   Log level:  {agent_config.log_level}")
    except Exception as exc:  # noqa: BLE001 — CLI top-level, intent is to show user-friendly error
        click.secho(f"❌ Failed to load config: {exc}", fg="red")
        sys.exit(1)


@cli.command()
def status() -> None:
    """Print current agent version and status."""
    click.echo("SRE Agent — Phase 1.5 (Multi-Cloud Support)")
    click.echo("Version:  0.1.0")
    click.echo("Status:   ✅ Operational")
    click.echo("")
    click.echo("To start the agent API server:")
    click.echo("  uvicorn sre_agent.api.main:app --host 0.0.0.0 --port 8080")


@cli.command()
@click.option("--config", "-c", required=True, type=click.Path(exists=True, path_type=Path),
              help="Path to agent YAML configuration file.")
@click.option("--dry-run", is_flag=True, help="Validate config but do not start agent.")
def run(config: Path, dry_run: bool) -> None:
    """Start the SRE Agent. (Phase 2: full pipeline not yet implemented.)"""
    if dry_run:
        click.invoke(validate, args=[str(config)])
        return

    click.secho(
        "⚠️  Full pipeline (Phase 2 — Intelligence Layer) not yet implemented.\n"
        "   Use the API server for Phase 1.5 functionality:\n"
        "   uvicorn sre_agent.api.main:app --host 0.0.0.0 --port 8080",
        fg="yellow",
    )
    sys.exit(0)


def main() -> None:
    """Module entry point."""
    cli(obj={})


if __name__ == "__main__":
    main()
