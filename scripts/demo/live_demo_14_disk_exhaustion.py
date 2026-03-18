#!/usr/bin/env python3
"""Live Demo 14 — Disk Exhaustion anomaly walkthrough (simulation)."""

from __future__ import annotations

from datetime import datetime, timezone


def main() -> None:
    print("\nLive Demo 14 — Disk Exhaustion Anomaly")
    print("=" * 52)
    payload = {
        "alert": {
            "service": "checkout-service",
            "anomaly_type": "disk_exhaustion",
            "metric_name": "node_filesystem_avail_bytes",
            "current_value": 2.1,
            "baseline_value": 34.8,
            "deviation_sigma": 5.4,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "description": "Persistent volume free space dropped below critical floor.",
        }
    }
    print("Simulation payload:")
    print(payload)
    print("\n✅ Disk exhaustion demo payload generated")


if __name__ == "__main__":
    main()
