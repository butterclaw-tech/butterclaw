"""
collusion_detector.py — Butterclaw v0.9.0
Complementary semantic role detection across agents within a sliding window.

Role: Detect distributed kill chains where distinct agents fill distinct semantic
    roles (encoder + exfiltrator + persister) within COLLUSION_WINDOW_SECONDS.
NOT Responsible For: Determining whether collusion is intentional or coincidental.
    It surfaces the pattern for the Fleet Sentinel to evaluate.
Failure Mode: Role assignment uses default_signatures.json patterns extended with
    collusion_role tags per R-04. If the Arsenal fails to load, collusion detection
    is disabled and logs CRITICAL — it does NOT silently degrade.

Distinct from CorrelationEngine:
    Correlation detects SAME patterns across agents (copycat/broadcast attack).
    Collusion detects COMPLEMENTARY patterns (divided labor attack).

Invariants: I-06-fleet (Arsenal patterns are the single signature system).
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config defaults (overridden by server.py from env)
# ---------------------------------------------------------------------------
COLLUSION_WINDOW_SECONDS: int = 180
COLLUSION_MIN_ROLES: int = 3      # distinct roles required to fire a CollusionEvent

# ---------------------------------------------------------------------------
# Semantic role vocabulary (I-06-fleet: tags live in default_signatures.json)
# ---------------------------------------------------------------------------
KNOWN_COLLUSION_ROLES = frozenset({
    "encoder",       # base64, gzip, or other encoding of payloads
    "exfiltrator",   # outbound transfer: curl, wget, socket writes
    "persister",     # persistence mechanisms: authorized_keys, crontab, systemd
    "scout",         # reconnaissance: metadata service probes, env reads, network scans
    "injector",      # prompt injection patterns targeting LLM inputs
})


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class CollusionEvent:
    event_id: str
    roles_filled: dict[str, str]          # {collusion_role: agent_id}
    implicated_agent_ids: list[str]
    confidence: float
    fired_at_unix: int = field(default_factory=lambda: int(time.time()))
    active: bool = True

    def as_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "roles_filled": self.roles_filled,
            "implicated_agent_ids": self.implicated_agent_ids,
            "confidence": self.confidence,
            "fired_at_unix": self.fired_at_unix,
            "active": self.active,
        }


# ---------------------------------------------------------------------------
# Detector
# ---------------------------------------------------------------------------

class CollusionDetector:
    """
    Detects divided-labor attacks by tracking semantic role assignment
    across distinct agents within a sliding COLLUSION_WINDOW_SECONDS window.
    """

    def __init__(
        self,
        arsenal_signatures: Optional[list[dict]] = None,
        window_seconds: int = COLLUSION_WINDOW_SECONDS,
        min_roles: int = COLLUSION_MIN_ROLES,
        on_collusion_event=None,
    ) -> None:
        """
        Parameters
        ----------
        arsenal_signatures : list[dict]
            Parsed entries from default_signatures.json. Each entry may carry
            a 'collusion_role' key (optional per R-04). Entries without the key
            participate only in individual-agent detection, not collusion.
        window_seconds : int
            Sliding window for role assignment accumulation.
        min_roles : int
            Number of distinct roles that must be filled to fire a CollusionEvent.
        on_collusion_event : callable, optional
            Callback invoked with (CollusionEvent,) when a CollusionEvent fires.
        """
        self._window = window_seconds
        self._min_roles = min_roles
        self._on_event = on_collusion_event
        self._lock = threading.Lock()

        # {collusion_role: [(agent_id, timestamp), ...]}
        self._role_window: dict[str, list[tuple[str, int]]] = {
            role: [] for role in KNOWN_COLLUSION_ROLES
        }
        self._active_events: dict[str, CollusionEvent] = {}

        # Load role mapping from Arsenal (I-06-fleet)
        self._role_map: dict[str, str] = {}  # pattern_id → collusion_role
        self._disabled = False
        self._load_arsenal(arsenal_signatures or [])

    # ------------------------------------------------------------------
    # Arsenal loading (I-06-fleet, R-04)
    # ------------------------------------------------------------------

    def _load_arsenal(self, signatures: list[dict]) -> None:
        """
        Build pattern_id → collusion_role mapping from Arsenal entries that
        carry a collusion_role tag. Entries without the tag are silently skipped.
        """
        loaded = 0
        for sig in signatures:
            role = sig.get("collusion_role")
            if role and role in KNOWN_COLLUSION_ROLES:
                self._role_map[sig["id"]] = role
                loaded += 1

        if not signatures:
            logger.critical(
                "CollusionDetector: Arsenal is empty — collusion detection DISABLED. "
                "Ensure default_signatures.json is loaded before startup."
            )
            self._disabled = True
        else:
            logger.info(
                "CollusionDetector: loaded %d collusion-role mappings from %d Arsenal entries",
                loaded, len(signatures),
            )

    def reload_arsenal(self, signatures: list[dict]) -> None:
        """Hot-reload Arsenal signatures (e.g., after a Loop Proposer update)."""
        with self._lock:
            self._role_map.clear()
            self._disabled = False
            self._load_arsenal(signatures)

    # ------------------------------------------------------------------
    # Ingest — public API
    # ------------------------------------------------------------------

    def ingest_pattern_match(
        self,
        agent_id: str,
        pattern_id: str,
        session_id: str,
        timestamp: Optional[int] = None,
    ) -> Optional[CollusionEvent]:
        """
        Called whenever the Arsenal matches a signature against an agent's tool call.
        If the matched signature carries a collusion_role, it is recorded in the
        sliding window and the window is evaluated for a CollusionEvent.

        Returns a CollusionEvent if the threshold is crossed, else None.
        """
        if self._disabled:
            return None

        collusion_role = self._role_map.get(pattern_id)
        if not collusion_role:
            return None  # Pattern does not participate in collusion detection

        ts = timestamp or int(time.time())

        with self._lock:
            return self._record_role_and_evaluate(agent_id, collusion_role, ts)

    def ingest_role_directly(
        self,
        agent_id: str,
        collusion_role: str,
        timestamp: Optional[int] = None,
    ) -> Optional[CollusionEvent]:
        """
        Assign a semantic role directly (used by test harness and future
        classifiers). collusion_role must be in KNOWN_COLLUSION_ROLES.
        """
        if collusion_role not in KNOWN_COLLUSION_ROLES:
            raise ValueError(f"Unknown collusion role: {collusion_role}")
        ts = timestamp or int(time.time())
        with self._lock:
            return self._record_role_and_evaluate(agent_id, collusion_role, ts)

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get_active_collusion_events(self) -> list[dict]:
        with self._lock:
            return [e.as_dict() for e in self._active_events.values() if e.active]

    def get_all_collusion_events(self) -> list[dict]:
        with self._lock:
            return [e.as_dict() for e in self._active_events.values()]

    def get_current_window_roles(self) -> dict[str, list[str]]:
        """
        Return the current live role window: {role: [agent_ids]} after pruning.
        Useful for Fleet Sentinel context injection.
        """
        now = int(time.time())
        cutoff = now - self._window
        with self._lock:
            result = {}
            for role, entries in self._role_window.items():
                agents = list({aid for aid, ts in entries if ts >= cutoff})
                if agents:
                    result[role] = agents
            return result

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _record_role_and_evaluate(
        self, agent_id: str, collusion_role: str, ts: int
    ) -> Optional[CollusionEvent]:
        """Must be called with self._lock held."""
        cutoff = ts - self._window

        # Append and prune this role's window
        self._role_window[collusion_role].append((agent_id, ts))
        self._role_window[collusion_role] = [
            (aid, t) for aid, t in self._role_window[collusion_role] if t >= cutoff
        ]

        # Build current role → representative agent mapping (one per role, latest)
        active_roles: dict[str, str] = {}
        for role, entries in self._role_window.items():
            live = [(aid, t) for aid, t in entries if t >= cutoff]
            if live:
                # Take the most recently active agent for this role
                active_roles[role] = max(live, key=lambda x: x[1])[0]

        # Ensure each role is held by a DISTINCT agent
        role_to_agent = self._deduplicate_roles(active_roles, cutoff)

        if len(role_to_agent) >= self._min_roles:
            return self._fire_collusion_event(role_to_agent)

        return None

    def _deduplicate_roles(
        self, candidate: dict[str, str], cutoff: int
    ) -> dict[str, str]:
        """
        Enforce that each role is assigned to a distinct agent_id.
        If an agent appears in multiple roles, assign each role to its
        earliest-appearing distinct agent within the window.
        """
        used_agents: set[str] = set()
        result: dict[str, str] = {}

        # Build role → [agent candidates sorted by first appearance]
        role_candidates: dict[str, list[tuple[int, str]]] = {}
        for role, entries in self._role_window.items():
            live = sorted(
                [(t, aid) for aid, t in entries if t >= cutoff],
                key=lambda x: x[0],
            )
            if live:
                role_candidates[role] = live

        for role, candidates in sorted(role_candidates.items()):
            for _, aid in candidates:
                if aid not in used_agents:
                    result[role] = aid
                    used_agents.add(aid)
                    break

        return result

    def _fire_collusion_event(self, role_to_agent: dict[str, str]) -> CollusionEvent:
        implicated = list(set(role_to_agent.values()))
        fingerprint = ":".join(
            f"{r}={a}" for r, a in sorted(role_to_agent.items())
        )
        event_id = hashlib.sha256(fingerprint.encode()).hexdigest()[:24]

        if event_id in self._active_events:
            return self._active_events[event_id]

        confidence = min(1.0, len(role_to_agent) / max(len(KNOWN_COLLUSION_ROLES), 1) * 1.5)
        event = CollusionEvent(
            event_id=event_id,
            roles_filled=role_to_agent,
            implicated_agent_ids=implicated,
            confidence=round(confidence, 3),
        )
        self._active_events[event_id] = event

        logger.warning(
            "CollusionEvent fired: event_id=%s roles=%s agents=%s confidence=%.3f",
            event_id, list(role_to_agent.keys()), implicated, confidence,
        )

        if self._on_event:
            try:
                self._on_event(event)
            except Exception:
                logger.exception("Error dispatching CollusionEvent to callback")

        return event
