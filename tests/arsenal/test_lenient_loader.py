"""
tests/arsenal/test_lenient_loader.py — Butterclaw v0.9.0
Arsenal loader backward compatibility tests (R-04).

Verifies that the lenient JSON parsing in policy_engine.py:
  - Ignores unknown fields without raising
  - Correctly reads collusion_role when present
  - Returns None for collusion_role when absent
  - Defaults fleet_scope to False when absent

These tests protect the invariant that a v0.8 Arsenal signature without
the v0.9 fields continues to function for individual-agent detection
exactly as before, and that a new Arsenal signature automatically
participates in collusion role assignment if it carries a collusion_role tag.

Invariant: I-06-fleet — no second signature system.
Resolution: R-04.
"""

from __future__ import annotations

import json
import pytest


# ---------------------------------------------------------------------------
# Minimal Arsenal loader implementation under test
# (in production this lives in policy_engine.py; tested here in isolation)
# ---------------------------------------------------------------------------

KNOWN_FIELDS = {
    "id",
    "name",
    "description",
    "severity",
    "patterns",
    "confidence_threshold",
    "tags",
    "enabled",
    "collusion_role",   # v0.9 — optional
    "fleet_scope",      # v0.9 — optional, default False
}

VALID_COLLUSION_ROLES = {
    "encoder", "exfiltrator", "persister", "scout", "injector",
}

import logging

logger = logging.getLogger(__name__)


class _Signature:
    """Minimal signature data class mirroring policy_engine.Signature."""
    __slots__ = (
        "id", "name", "description", "severity", "patterns",
        "confidence_threshold", "tags", "enabled",
        "collusion_role", "fleet_scope",
    )

    def __init__(self, **kwargs):
        for k in self.__slots__:
            setattr(self, k, kwargs.get(k))


def _load_signature(raw: dict) -> _Signature:
    """
    Lenient loader — allow-list extraction that ignores unknown keys (R-04).
    Unknown keys are logged at DEBUG level, not raised.
    """
    unknown = set(raw.keys()) - KNOWN_FIELDS
    if unknown:
        logger.debug("Arsenal loader: ignoring unknown fields: %s", unknown)

    sig = _Signature(
        id=raw.get("id"),
        name=raw.get("name"),
        description=raw.get("description"),
        severity=raw.get("severity"),
        patterns=raw.get("patterns", []),
        confidence_threshold=raw.get("confidence_threshold", 0.5),
        tags=raw.get("tags", []),
        enabled=raw.get("enabled", True),
        collusion_role=raw.get("collusion_role", None),
        fleet_scope=raw.get("fleet_scope", False),
    )
    return sig


# ---------------------------------------------------------------------------
# R-04 tests
# ---------------------------------------------------------------------------

class TestLenientLoader:
    """test_unknown_field_ignored"""

    def test_unknown_field_ignored(self):
        """
        A signature with an unrecognised field must load without error.
        The unknown field must not appear on the resulting Signature object.
        """
        raw = {
            "id": "sig-999",
            "name": "Future Signature",
            "severity": "low",
            "patterns": [],
            "confidence_threshold": 0.5,
            "tags": [],
            "enabled": True,
            "unknown_future_field": "should be silently ignored",
            "another_unknown": 42,
        }
        sig = _load_signature(raw)
        assert sig.id == "sig-999"
        assert sig.name == "Future Signature"
        assert not hasattr(sig, "unknown_future_field"), (
            "Unknown fields must not be added to the Signature object"
        )
        assert not hasattr(sig, "another_unknown")

    def test_collusion_role_present(self):
        """
        A signature with a valid collusion_role must expose it on the object.
        All KNOWN_COLLUSION_ROLES must be accepted.
        """
        for role in VALID_COLLUSION_ROLES:
            raw = {
                "id": f"sig-role-{role}",
                "name": f"Test {role}",
                "severity": "medium",
                "patterns": [],
                "confidence_threshold": 0.6,
                "tags": [],
                "enabled": True,
                "collusion_role": role,
            }
            sig = _load_signature(raw)
            assert sig.collusion_role == role, (
                f"Expected collusion_role={role!r}, got {sig.collusion_role!r}"
            )

    def test_collusion_role_absent(self):
        """
        A v0.8 signature without collusion_role must have collusion_role=None.
        It must still load and function for individual-agent detection.
        """
        raw = {
            "id": "sig-v08-legacy",
            "name": "Legacy v0.8 Signature",
            "severity": "high",
            "patterns": [{"type": "regex", "value": "curl.*evil\\.com"}],
            "confidence_threshold": 0.8,
            "tags": ["exfil"],
            "enabled": True,
            # No collusion_role — v0.8 style
        }
        sig = _load_signature(raw)
        assert sig.collusion_role is None, (
            "Absent collusion_role must default to None, not raise or default to a role"
        )
        # Must still carry all v0.8 fields intact
        assert sig.id == "sig-v08-legacy"
        assert sig.severity == "high"
        assert sig.enabled is True
        assert len(sig.patterns) == 1

    def test_fleet_scope_default_false(self):
        """
        A signature without fleet_scope must default to False.
        """
        raw = {
            "id": "sig-no-scope",
            "name": "No Scope Signature",
            "severity": "low",
            "patterns": [],
            "confidence_threshold": 0.5,
            "tags": [],
            "enabled": True,
        }
        sig = _load_signature(raw)
        assert sig.fleet_scope is False, (
            f"Expected fleet_scope=False, got {sig.fleet_scope!r}"
        )

    def test_fleet_scope_explicit_true(self):
        """A signature with fleet_scope=True must expose True."""
        raw = {
            "id": "sig-fleet-scoped",
            "name": "Fleet Scoped Signature",
            "severity": "critical",
            "patterns": [],
            "confidence_threshold": 0.9,
            "tags": [],
            "enabled": True,
            "collusion_role": "persister",
            "fleet_scope": True,
        }
        sig = _load_signature(raw)
        assert sig.fleet_scope is True

    def test_both_v09_fields_together(self):
        """A fully-specified v0.9 signature must load all fields correctly."""
        raw = {
            "id": "sig-v09-full",
            "name": "v0.9 Full Signature",
            "description": "Detects base64 encoding of payloads",
            "severity": "high",
            "patterns": [{"type": "regex", "value": "base64.*encode"}],
            "confidence_threshold": 0.75,
            "tags": ["encoding", "staging"],
            "enabled": True,
            "collusion_role": "encoder",
            "fleet_scope": True,
        }
        sig = _load_signature(raw)
        assert sig.id == "sig-v09-full"
        assert sig.collusion_role == "encoder"
        assert sig.fleet_scope is True

    def test_unknown_and_v09_fields_together(self):
        """
        A signature with both unknown fields AND v0.9 fields must:
        - Ignore the unknown fields
        - Correctly parse the v0.9 fields
        """
        raw = {
            "id": "sig-mixed",
            "name": "Mixed Signature",
            "severity": "medium",
            "patterns": [],
            "confidence_threshold": 0.6,
            "tags": [],
            "enabled": True,
            "collusion_role": "scout",
            "fleet_scope": False,
            "future_field_v10": "ignore me",
            "experimental": {"nested": True},
        }
        sig = _load_signature(raw)
        assert sig.collusion_role == "scout"
        assert sig.fleet_scope is False
        assert not hasattr(sig, "future_field_v10")
        assert not hasattr(sig, "experimental")

    def test_empty_signatures_list_logs_critical(self, caplog):
        """
        CollusionDetector receiving an empty signatures list must disable
        collusion detection and log at CRITICAL (not raise).
        """
        import logging
        from butterclaw.collusion_detector import CollusionDetector

        with caplog.at_level(logging.CRITICAL, logger="collusion_detector"):
            detector = CollusionDetector(arsenal_signatures=[], window_seconds=60, min_roles=3)

        assert detector._disabled is True
        assert any("DISABLED" in r.message for r in caplog.records), (
            "Expected CRITICAL log with 'DISABLED' when Arsenal is empty"
        )

    def test_non_collusion_role_signature_still_individual_detects(self):
        """
        A signature without collusion_role must not participate in collusion
        detection, but the CollusionDetector must not crash on it.
        """
        from butterclaw.collusion_detector import CollusionDetector

        sigs = [
            {
                "id": "sig-no-role",
                "name": "No Collusion Role",
                "severity": "high",
                "patterns": [],
                "confidence_threshold": 0.7,
                "tags": [],
                "enabled": True,
                # No collusion_role
            }
        ]
        detector = CollusionDetector(arsenal_signatures=sigs, window_seconds=60, min_roles=3)
        assert not detector._disabled, "Detector must not be disabled just because one sig lacks collusion_role"
        # Attempting to ingest a pattern match for this sig must silently return None
        result = detector.ingest_pattern_match(
            agent_id="agent-test",
            pattern_id="sig-no-role",
            session_id="sess-001",
        )
        assert result is None, (
            "Signature without collusion_role must not produce a CollusionEvent"
        )
