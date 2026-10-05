"""
tests/fleet/conftest.py — Butterclaw v0.9.0
Pytest fixtures for fleet layer tests.

Key fixture: assert_distinct_db_connections
    Enforces I-07-fleet — fleet.db and butterclaw.db are NEVER co-transacted.
    Asserts both connection objects are distinct at the module level.
"""

from __future__ import annotations

import sqlite3
from sqlite3 import Connection
from typing import Iterator
import tempfile
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# In-memory / temp-file DB fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="function")
def fleet_db_path(tmp_path: Path) -> str:
    """Return a fresh temporary fleet.db path for each test."""
    return str(tmp_path / "fleet.db")


@pytest.fixture(scope="function")
def butterclaw_db_path(tmp_path: Path) -> str:
    """Return a fresh temporary butterclaw.db path for each test."""
    return str(tmp_path / "butterclaw.db")


# Old: def fleet_db(fleet_db_path: str) -> Connection:
@pytest.fixture(scope="function")
def fleet_db(fleet_db_path: str) -> Iterator[Connection]:
    """
    Bootstrapped fleet.db connection for testing.
    Overrides the module-level fleet_db_init._connection.
    """
    # Old: import fleet_db_init
    import butterclaw.fleet_db_init as fleet_db_init

    conn = fleet_db_init.init_fleet_db(path=fleet_db_path)
    yield conn

    # Teardown
    conn.close()
    fleet_db_init._connection = None


# Old: def butterclaw_db(butterclaw_db_path: str) -> Connection:
@pytest.fixture(scope="function")
def butterclaw_db(butterclaw_db_path: str) -> Iterator[Connection]:
    """A minimal butterclaw.db connection for isolation testing."""
    conn = sqlite3.connect(butterclaw_db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY)")
    conn.commit()
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# I-07-fleet: DB isolation assertion fixture
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def assert_distinct_db_connections(fleet_db, butterclaw_db):
    """
    Invariant I-07-fleet — fleet.db and butterclaw.db must NEVER be the same
    connection object and must point to different file paths.

    This fixture runs automatically for every test in the fleet test suite.
    """
    assert fleet_db is not butterclaw_db, (
        "I-07-fleet VIOLATION: fleet_db and butterclaw_db are the same connection object. "
        "No code path may hold an open transaction on butterclaw.db while acquiring "
        "a connection to fleet.db, and vice versa."
    )
    assert fleet_db.execute("PRAGMA database_list").fetchall() != \
           butterclaw_db.execute("PRAGMA database_list").fetchall(), (
        "I-07-fleet VIOLATION: fleet.db and butterclaw.db appear to use the same backing file."
    )


# ---------------------------------------------------------------------------
# Component fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="function")
def fleet_registry(fleet_db):
    # Old: from fleet_registry import FleetRegistry
    from butterclaw.fleet_registry import FleetRegistry
    return FleetRegistry()


@pytest.fixture(scope="function")
def trust_graph(fleet_db):
    # Old: from trust_graph import TrustGraph
    from butterclaw.trust_graph import TrustGraph
    return TrustGraph()


@pytest.fixture(scope="function")
def correlation_engine(fleet_db):
    from butterclaw.correlation_engine import CorrelationEngine
    return CorrelationEngine(window_minutes=1, fleet_threshold=3, temporal_window_seconds=30)


@pytest.fixture(scope="function")
def collusion_detector(fleet_db):
    from butterclaw.collusion_detector import CollusionDetector
    # Minimal Arsenal with collusion_role tags for testing
    signatures = [
        {"id": "sig-001", "name": "Base64 Encoding", "severity": "medium",
         "patterns": [], "confidence_threshold": 0.6, "tags": [], "enabled": True,
         "collusion_role": "encoder"},
        {"id": "sig-002", "name": "Outbound Transfer", "severity": "high",
         "patterns": [], "confidence_threshold": 0.7, "tags": [], "enabled": True,
         "collusion_role": "exfiltrator"},
        {"id": "sig-003", "name": "Persistence Write", "severity": "critical",
         "patterns": [], "confidence_threshold": 0.8, "tags": [], "enabled": True,
         "collusion_role": "persister"},
        {"id": "sig-004", "name": "Recon Probe", "severity": "low",
         "patterns": [], "confidence_threshold": 0.5, "tags": [], "enabled": True,
         "collusion_role": "scout"},
    ]
    return CollusionDetector(arsenal_signatures=signatures, window_seconds=180, min_roles=3)


@pytest.fixture(scope="function")
def fleet_memory(fleet_db):
    from butterclaw.fleet_memory import FleetMemory
    return FleetMemory(promotion_threshold=3)


@pytest.fixture(scope="function")
def mock_llm():
    """Returns a mock LLM callable that always returns a CORRELATED verdict."""
    def _llm(messages, temperature=0.5):
        return (
            '{"verdict": "CORRELATED", "confidence": 0.72, '
            '"implicated_agent_ids": ["agent-a", "agent-b", "agent-c"], '
            '"reasoning": "Three agents exhibit identical trajectory hashes."}'
        )
    return _llm


@pytest.fixture(scope="function")
def mock_analyze_submitter():
    """Records payloads submitted to /api/analyze for assertion."""
    submitted = []

    def _submit(payload):
        submitted.append(payload)

    _submit.submitted = submitted
    return _submit


@pytest.fixture(scope="function")
def fleet_sentinel(
    fleet_db, fleet_registry, correlation_engine, collusion_detector,
    trust_graph, fleet_memory, mock_llm, mock_analyze_submitter
):
    # Old: from fleet_sentinel import FleetSentinel
    from butterclaw.fleet_sentinel import FleetSentinel
    return FleetSentinel(
        fleet_registry=fleet_registry,
        correlation_engine=correlation_engine,
        collusion_detector=collusion_detector,
        trust_graph=trust_graph,
        fleet_memory=fleet_memory,
        llm_client=mock_llm,
        analyze_endpoint_submitter=mock_analyze_submitter,
        dry_run=True,
        min_agents=2,
        min_interval_seconds=0,   # disable rate-limiting in tests
    )


@pytest.fixture(scope="function")
def hemisphere_scheduler():
    # Old: from hemisphere_scheduler import HemisphereScheduler
    from butterclaw.hemisphere_scheduler import HemisphereScheduler
    scheduler = HemisphereScheduler(max_concurrent=2, circuit_breaker_threshold=3)
    scheduler.start()
    return scheduler
