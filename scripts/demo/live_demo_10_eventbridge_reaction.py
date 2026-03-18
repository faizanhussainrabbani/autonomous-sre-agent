#!/usr/bin/env python3
"""Compatibility alias for Demo 10 using standardized numbering."""

from __future__ import annotations

from pathlib import Path
from runpy import run_path


if __name__ == "__main__":
    run_path(str(Path(__file__).with_name("live_demo_eventbridge_reaction.py")), run_name="__main__")
