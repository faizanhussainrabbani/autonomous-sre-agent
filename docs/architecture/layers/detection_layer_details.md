# Detection Layer: Detailed Breakdown

The **Detection Layer** bridges the gap between raw telemetry (Observability) and the agent's reasoning engine (Intelligence). Its primary responsibility is to ingest continuous metric streams and assert when the system state has deviated beyond normal operating parameters, producing a canonical `Incident`.

## 1. Core Responsibilities

*   **Metric Windowing & Aggregation:** Pulling raw time-series data into manageable, rolling windows for analysis (e.g., 5-minute rolling averages, 95th percentiles).
*   **Baselining (Statistical & ML):**
    *   *Statistical:* Simple moving averages (SMA), standard deviation bands, and exponential smoothing for predictable metrics like CPU.
    *   *ML-Based:* Unsupervised anomaly detection (e.g., Isolation Forests, Autoencoders) for complex, highly dimensional data like request latency distributions where simple thresholds fail.
*   **Multi-Dimensional Correlation:** Single metric spikes are noisy. The layer correlates CPU spikes with latency increases, error rates, and concurrent deployment events to suppress false positives.
*   **Threshold-Free Detection:** Moving away from static, human-defined alerting rules (e.g., "CPU > 80%") toward dynamic, self-tuning sensitivity based on historical seasonality.
*   **Incident Type Assignment:** Upon correlating a confirmed anomaly, the Detection Layer maps the anomalous signature to one of the `AnomalyType` categories defined in `canonical.py` (e.g., `LATENCY_SPIKE`, `ERROR_RATE_SURGE`, `MEMORY_PRESSURE`, `DEPLOYMENT_INDUCED`, `INVOCATION_ERROR_SURGE`, etc.) before passing it to Intelligence.

## 2. Integration Boundaries

*   **Input (From Observability):** Consumes normalized telemetry data (Prometheus metrics, Loki logs, eBPF events) usually routed through an OpenTelemetry Collector.
*   **Output (To Intelligence):** When an anomaly correlation crosses the confidence threshold, it generates a canonical `Incident` (defined in `data_model.md`) and passes it to the Intelligence Layer for diagnosis.

## 3. Advanced Detection Mechanisms

### 3.1 Alert Deduplication & Grouping
To prevent alert storms, the layer enforces strict deduplication logic. If an anomaly signature matching an existing active incident's `resource` and `type` fires again, it is suppressed from creating a new `Incident` object. Instead, the telemetry is appended to the `telemetry_context` of the existing open incident, up to a maximum rate limit defined for that namespace.

### 3.2 ML Warm-up Period
ML baselines require sufficient historical data to tune parameters properly.
*   **Cold Start:** During the first 7 days of deployment, the ML baseline falls back to conservative, statistical standard-deviation thresholds (Statistical Baselining).
*   **Convergence:** After 7 days, Isolation Forests and Autoencoders fully converge and phase out the statistical fallback, assuming control over anomaly sensitivity.

## 3. Technology Stack

*   **Feature Store:** A low-latency store (e.g., Redis) maintaining the rolling metric windows and historical baselines used for real-time comparison.
*   **Anomaly Engine:** Python-based ML services utilizing libraries like `scikit-learn` or `Prophet` for seasonality detection.
*   **Correlation Processor:** Stream processing (e.g., generic Python async queues or Kafka for higher scale) to group anomalous signals occurring within the same time boundary.
