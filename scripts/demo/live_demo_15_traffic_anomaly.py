#!/usr/bin/env python3
"""Live Demo 15 — Traffic Anomaly detection walkthrough (simulation)."""

from __future__ import annotations

from datetime import datetime, timezone


def main() -> None:
    print("\nLive Demo 15 — Traffic Anomaly")
    print("=" * 46)
    payload = {
        "alert": {
            "service": "edge-gateway",
            "anomaly_type": "traffic_anomaly",
            "metric_name": "request_rate_rps",
            "current_value": 12840,
            "baseline_value": 3150,
            "deviation_sigma": 6.1,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "description": "Inbound request rate surged 4x from baseline.",
        }
    }
    print("Simulation payload:")
    print(payload)
    print("\n✅ Traffic anomaly demo payload generated")


if __name__ == "__main__":
    main()
