-- Migration 009: metric_baselines continuous aggregate
--
-- Creates a TimescaleDB continuous aggregate for rolling metric baselines.
-- The migration is extension-aware and skips safely when TimescaleDB is not
-- installed in the current PostgreSQL environment.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_extension
        WHERE extname = 'timescaledb'
    ) THEN
        RAISE NOTICE 'TimescaleDB extension not installed; skipping metric_baselines';
        RETURN;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name = 'telemetry_metrics'
    ) THEN
        RAISE NOTICE 'telemetry_metrics table not found; skipping metric_baselines';
        RETURN;
    END IF;

    EXECUTE $sql$
        CREATE MATERIALIZED VIEW IF NOT EXISTS metric_baselines
        WITH (timescaledb.continuous) AS
        SELECT
            service,
            metric_name,
            time_bucket('5 minutes', ts) AS bucket,
            avg(value) AS avg_value,
            percentile_cont(0.95) WITHIN GROUP (ORDER BY value) AS p95_value
        FROM telemetry_metrics
        GROUP BY service, metric_name, bucket
        WITH NO DATA
    $sql$;

    EXECUTE '
        CREATE INDEX IF NOT EXISTS idx_metric_baselines_service_metric_bucket
        ON metric_baselines (service, metric_name, bucket DESC)
    ';

    BEGIN
        PERFORM add_continuous_aggregate_policy(
            'metric_baselines',
            start_offset => INTERVAL '1 day',
            end_offset => INTERVAL '5 minutes',
            schedule_interval => INTERVAL '5 minutes'
        );
    EXCEPTION
        WHEN OTHERS THEN
            IF position('already exists' IN SQLERRM) = 0 THEN
                RAISE NOTICE 'metric_baselines policy not added: %', SQLERRM;
            END IF;
    END;
END
$$;
