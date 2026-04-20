"""Unit tests for PostgresReasoningTraceStore."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sre_agent.adapters.persistence.reasoning_trace_store import PostgresReasoningTraceStore
from sre_agent.ports.persistence import ReasoningTracePort
from tests.unit.adapters.persistence.conftest import FakePool


def test_store_implements_reasoning_trace_port(fake_pool: FakePool) -> None:
    """PostgresReasoningTraceStore must satisfy ReasoningTracePort."""
    store = PostgresReasoningTraceStore(pool=fake_pool)
    assert isinstance(store, ReasoningTracePort)


async def test_start_run_inserts_agent_runs_row(fake_pool: FakePool) -> None:
    """start_run should insert one agent_runs row with expected keys."""
    store = PostgresReasoningTraceStore(pool=fake_pool)
    incident_id = uuid4()

    run_id = await store.start_run(
        incident_id=incident_id,
        agent_id="rag-diagnostic-pipeline",
        metadata={"service": "checkout-service"},
    )

    assert run_id is not None
    assert fake_pool.conn.executed, "Expected INSERT execution"
    sql, args = fake_pool.conn.executed[0]
    assert "INSERT INTO agent_runs" in sql
    assert args[0] == run_id
    assert args[1] == incident_id
    assert args[2] == "rag-diagnostic-pipeline"


async def test_end_run_updates_outcome_and_end_time(fake_pool: FakePool) -> None:
    """end_run should update outcome and ended_at for existing run."""
    store = PostgresReasoningTraceStore(pool=fake_pool)
    run_id = uuid4()

    await store.end_run(run_id, "success", metadata={"confidence": 0.91})

    assert fake_pool.conn.executed, "Expected UPDATE execution"
    sql, args = fake_pool.conn.executed[0]
    assert "UPDATE agent_runs" in sql
    assert args[0] == run_id
    assert args[2] == "success"


async def test_log_tool_call_persists_payloads(fake_pool: FakePool) -> None:
    """log_tool_call should persist input/output payload JSON."""
    store = PostgresReasoningTraceStore(pool=fake_pool)
    run_id = uuid4()

    call_id = await store.log_tool_call(
        run_id,
        tool_name="llm.generate_hypothesis",
        status="success",
        input_payload={"evidence_count": 3},
        output_payload={"confidence": 0.88},
        latency_ms=120,
    )

    assert call_id is not None
    sql, args = fake_pool.conn.executed[0]
    assert "INSERT INTO tool_calls" in sql
    assert args[1] == run_id
    assert args[2] == "llm.generate_hypothesis"
    assert args[6] == "success"


async def test_log_retrieved_context_clamps_similarity(fake_pool: FakePool) -> None:
    """Similarity values should be clamped into [0.0, 1.0] range."""
    store = PostgresReasoningTraceStore(pool=fake_pool)
    run_id = uuid4()

    await store.log_retrieved_context(
        run_id,
        doc_id="runbook/oom.md",
        similarity_score=3.5,
        source="runbook/oom.md",
        content_snippet="OOM troubleshooting section",
    )

    sql, args = fake_pool.conn.executed[0]
    assert "INSERT INTO retrieved_contexts" in sql
    assert args[1] == run_id
    assert args[2] == "runbook/oom.md"
    assert args[3] == 1.0


async def test_get_run_returns_record_when_present(fake_pool: FakePool) -> None:
    """get_run should map one agent_runs row into a ReasoningRunRecord."""
    store = PostgresReasoningTraceStore(pool=fake_pool)
    run_id = uuid4()
    incident_id = uuid4()
    now = datetime.now(tz=UTC)
    fake_pool.conn.queue_fetchrow(
        {
            "run_id": run_id,
            "incident_id": incident_id,
            "agent_id": "rag-diagnostic-pipeline",
            "started_at": now,
            "ended_at": None,
            "outcome": None,
            "metadata": {"service": "checkout-service"},
        }
    )

    record = await store.get_run(run_id)

    assert record is not None
    assert record.run_id == run_id
    assert record.incident_id == incident_id
    assert record.metadata_json == {"service": "checkout-service"}


async def test_get_run_returns_none_when_missing(fake_pool: FakePool) -> None:
    """get_run should return None when no run row exists."""
    store = PostgresReasoningTraceStore(pool=fake_pool)

    record = await store.get_run(uuid4())

    assert record is None


async def test_list_runs_by_incident_returns_ordered_rows(fake_pool: FakePool) -> None:
    """list_runs_by_incident should return mapped records and pass the limit."""
    store = PostgresReasoningTraceStore(pool=fake_pool)
    incident_id = uuid4()
    now = datetime.now(tz=UTC)
    fake_pool.conn.queue_fetch(
        [
            {
                "run_id": uuid4(),
                "incident_id": incident_id,
                "agent_id": "rag-diagnostic-pipeline",
                "started_at": now,
                "ended_at": None,
                "outcome": "success",
                "metadata": {"attempt": 1},
            },
            {
                "run_id": uuid4(),
                "incident_id": incident_id,
                "agent_id": "rag-diagnostic-pipeline",
                "started_at": now,
                "ended_at": now,
                "outcome": "failed",
                "metadata": {"attempt": 2},
            },
        ]
    )

    records = await store.list_runs_by_incident(incident_id, limit=25)

    assert len(records) == 2
    assert records[0].metadata_json == {"attempt": 1}
    sql, args = fake_pool.conn.executed[0]
    assert "FROM agent_runs" in sql
    assert args[0] == incident_id
    assert args[1] == 25


async def test_list_tool_calls_maps_json_payloads(fake_pool: FakePool) -> None:
    """list_tool_calls should decode tool call input/output payloads."""
    store = PostgresReasoningTraceStore(pool=fake_pool)
    run_id = uuid4()
    now = datetime.now(tz=UTC)
    fake_pool.conn.queue_fetch(
        [
            {
                "call_id": uuid4(),
                "run_id": run_id,
                "tool_name": "llm.generate_hypothesis",
                "input": {"evidence_count": 3},
                "output": {"confidence": 0.88},
                "latency_ms": 120,
                "status": "success",
                "called_at": now,
            }
        ]
    )

    records = await store.list_tool_calls(run_id)

    assert len(records) == 1
    assert records[0].input_json == {"evidence_count": 3}
    assert records[0].output_json == {"confidence": 0.88}


async def test_list_retrieved_contexts_maps_rows(fake_pool: FakePool) -> None:
    """list_retrieved_contexts should map rows into RetrievedContextRecord values."""
    store = PostgresReasoningTraceStore(pool=fake_pool)
    run_id = uuid4()
    now = datetime.now(tz=UTC)
    fake_pool.conn.queue_fetch(
        [
            {
                "context_id": uuid4(),
                "run_id": run_id,
                "doc_id": "runbook/oom.md",
                "similarity_score": 0.95,
                "content_snippet": "OOM troubleshooting",
                "source": "runbook/oom.md",
                "retrieved_at": now,
            }
        ]
    )

    records = await store.list_retrieved_contexts(run_id)

    assert len(records) == 1
    assert records[0].doc_id == "runbook/oom.md"
    assert records[0].similarity_score == 0.95
