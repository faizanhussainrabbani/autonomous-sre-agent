-- Migration 004: Relay and Vector Fixes
-- 1. Extend event_outbox status enum to include 'processing' for atomic claim.
-- 2. Add UNIQUE constraint on vector_embeddings (source_type, source_id) for
--    stable upsert semantics regardless of doc_id format.
--
-- This migration is idempotent — safe to re-run on a DB that already has these
-- changes applied.

-- ==========================================================================
-- event_outbox — add 'processing' status for atomic row claiming by OutboxRelay
-- ==========================================================================

DO $$
BEGIN
    -- Drop and recreate the status check constraint to include 'processing'.
    -- IF EXISTS guards make this idempotent.
    IF EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE table_name = 'event_outbox'
          AND constraint_name = 'chk_outbox_status'
    ) THEN
        ALTER TABLE event_outbox DROP CONSTRAINT chk_outbox_status;
        RAISE NOTICE 'event_outbox: dropped old chk_outbox_status constraint';
    END IF;

    ALTER TABLE event_outbox
        ADD CONSTRAINT chk_outbox_status
        CHECK (status IN ('pending', 'processing', 'sent', 'failed'));

    RAISE NOTICE 'event_outbox: added new chk_outbox_status with processing status';
END
$$;

-- Partial index for efficient pending + processing visibility queries.
CREATE INDEX IF NOT EXISTS idx_outbox_claim_pending
    ON event_outbox (status, created_at ASC)
    WHERE status = 'pending';

-- ==========================================================================
-- vector_embeddings — UNIQUE (source_type, source_id) for upsert correctness
-- ==========================================================================

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE table_name = 'vector_embeddings'
          AND constraint_name = 'uq_vector_source'
    ) THEN
        ALTER TABLE vector_embeddings
            ADD CONSTRAINT uq_vector_source UNIQUE (source_type, source_id);
        RAISE NOTICE 'vector_embeddings: added uq_vector_source unique constraint';
    ELSE
        RAISE NOTICE 'vector_embeddings: uq_vector_source already exists, skipping';
    END IF;
END
$$;
