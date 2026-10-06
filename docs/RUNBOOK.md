# Butterclaw v0.9.0 — Operations Runbook

> **Scope:** Fleet layer operational procedures added in v0.9.0.
> For pre-fleet procedures see the v0.8 Runbook in the `dev` branch history.

---

## 1. Quarantine vs. Block Decision Flowchart

```
Suspicious fleet behavior detected?
        │
        ▼
Is the agent actively running processes
that must be stopped RIGHT NOW?
        │
    YES │                         NO
        │                          │
        ▼                          ▼
Use /api/spatial/block       Is the agent part of a
(kinetic — terminates        confirmed colluding group?
 active processes)                 │
        │                      YES │              NO
        │                          │               │
        │                          ▼               ▼
        │                   Quarantine            Monitor via
        │                   the agent             Fleet Sentinel log
        │                   (see §1.1)            and correlation events
        │                          │
        └──────────────────────────┘
                    │
                    ▼
        After quarantine: do active
        sessions still need killing?
                    │
                YES │
                    ▼
        Follow up with /api/spatial/block
        for each active session_id
```

### Key Distinction

| Action | API | Effect | Kills Active Processes? |
|--------|-----|--------|------------------------|
| **Block** | `POST /api/spatial/block` | Kinetic — terminates active processes via Paranoia Dial | ✅ Yes |
| **Quarantine** | `POST /api/fleet/agents/<id>/quarantine` then `/confirm` | Fleet layer — sets reputation to 0.0, blocks new sessions, fires taint propagation | ❌ No |

> **Rule:** Quarantine first when you want to prevent new sessions and propagate taint through the trust graph without immediately killing running processes. Block when you need immediate termination.

---

## 1.1 Quarantine Workflow (Two-Step, R-06)

### Step 1 — Flag

```http
POST /api/fleet/agents/<agent_id>/quarantine
Authorization: Bearer <admin-token>
```

**Response 200:**
```json
{
  "confirmation_token": "qtok_<uuid>",
  "expires_in_seconds": 60,
  "agent_id": "<agent_id>",
  "current_reputation": 0.42,
  "active_sessions": ["sess_abc", "sess_def"],
  "warning": "Quarantine will set reputation to 0.0 and block new sessions but will NOT terminate active processes. Use /api/spatial/block to terminate active processes."
}
```

> ⚠️ Token expires in **60 seconds**. If it expires, re-issue Step 1.

**UI requirement:** Display the warning string in a modal with **"Quarantine Agent"** / **"Cancel"** buttons. The confirm button must use destructive visual styling. Active sessions list must be shown. Auto-submission on page load is prohibited.

### Step 2 — Confirm

```http
POST /api/fleet/agents/<agent_id>/quarantine/confirm
Authorization: Bearer <admin-token>
Content-Type: application/json

{ "confirmation_token": "qtok_<uuid>" }
```

**Response 200:**
```json
{
  "status": "quarantined",
  "reputation_score": 0.0,
  "role": "quarantined",
  "audit_log_id": 4821
}
```

**Side effects on confirm:**
1. `reputation_score` → 0.0, `role` → `quarantined`
2. Synthetic TAINT event submitted for all known `session_id`s → Topology Manager → Cold Memory crystallisation
3. `trust_graph.propagate_taint()` fires (one-hop, per I-05-fleet)
4. Immediate reactive Fleet Sentinel cycle queued at priority 1

### Releasing Quarantine

```http
DELETE /api/fleet/agents/<agent_id>/quarantine
Authorization: Bearer <admin-token>
```

- Sets `role` → `unknown`, begins **asymmetric** reputation recovery from 0.0
- Memory Engine taint records are **NOT removed** — taint is permanent evidence
- Audit log entry `action=released` is written

---

## 2. Fleet Sentinel Dry-Run Rollout

### Recommended Deployment Sequence (R-RISK-04)

| Phase | Action | When to Move On |
|-------|--------|-----------------|
| 1 | Deploy with `FLEET_SENTINEL_DRY_RUN=true` (default) | Immediately |
| 2 | Monitor `fleet_sentinel_log` for 1–2 weeks; submit operator feedback on all CORRELATED and COLLUDING verdicts | When you have ≥20 labeled verdicts |
| 3 | Check: `confirmed_false_positive / total_labeled < 5%` over a rolling 7-day window | When FP rate < 5% |
| 4 | Set `FLEET_SENTINEL_DRY_RUN=false` | When Step 3 passes |
| 5 | Continuously monitor — re-enable dry-run if FP rate exceeds 10% in any 24-hour window | Ongoing |

### Submitting Operator Feedback

```http
POST /api/fleet/sentinel-log/<log_id>/feedback
Authorization: Bearer <operator-token>
Content-Type: application/json

{
  "feedback": "confirmed_false_positive",
  "notes": "Three background workers running identical scheduled tasks — not an attack."
}
```

Valid `feedback` values: `confirmed_true_positive` | `confirmed_false_positive`

Feedback is picked up by the Loop Proposer's next improvement cycle (D-28).

---

## 3. Fleet Database Operations

### fleet.db Location

Controlled by `BUTTERCLAW_FLEET_DB_PATH` (default: `./fleet.db`).

fleet.db is included in the Docker volume backup **alongside** butterclaw.db (I-01-fleet).

### Backup Verification

`scripts/verify_backup.sh` runs `PRAGMA integrity_check` on both `butterclaw.db` and `fleet.db`.

```bash
./scripts/verify_backup.sh
# Expected output:
#   butterclaw.db: ok
#   fleet.db: ok
```

If `fleet.db` is corrupted:
1. **Individual-agent detection is unaffected** during the restoration window (fleet data is enrichment only)
2. Restore from the most recent Docker volume backup
3. Server will **not start** without a valid `fleet.db` (I-01-fleet enforced by `fleet_db_init.py`)

### DB Isolation Rule (I-07-fleet)

No code path may hold an open transaction on `butterclaw.db` while acquiring a connection to `fleet.db`, and vice versa. Enforced by `tests/fleet/conftest.py::assert_distinct_db_connections`.

---

## 4. Alert Response Procedures

### P1 Alerts

| Alert | Cause | Response |
|-------|-------|----------|
| `butterclaw_hemisphere_errors_total` rate > 3/60s | LLM provider errors | Check LLM provider status page; circuit breaker will open after `CIRCUIT_BREAKER_THRESHOLD` (default 3) errors |
| `butterclaw_circuit_breaker_state == 2` (open) | Repeated LLM failures | Guardian Brain is unaffected; wait for `CIRCUIT_BREAKER_RESET_SECONDS` (default 60s) half-open retry; check LLM provider |

### P2 Alerts

| Alert | Cause | Response |
|-------|-------|----------|
| `butterclaw_hemisphere_queue_length` > 5 for > 2 min | Hemisphere backlog | Check `MAX_CONCURRENT_LLM` config; check for runaway Fleet Sentinel reactive cycles |
| LLM provider token usage > 80% of daily budget by noon | Token exhaustion risk | Increase `FLEET_SENTINEL_MIN_INTERVAL_SECONDS`; consider reducing proactive `SENTINEL_INTERVAL_HOURS` |
| `fleet.db` write latency p99 > 50ms | Volume I/O contention | Tune `PRAGMA wal_autocheckpoint`; consider separate volume mount for `fleet.db` |
| `butterclaw.db` write latency p99 > 20ms | Shared volume saturation | Investigate volume I/O; consider separate volume mounts |

---

## 5. Fleet Sentinel Manual Trigger

To run one Fleet Sentinel cycle immediately (operator role):

```http
POST /api/fleet/sentinel/trigger
Authorization: Bearer <operator-token>
```

Response includes the `FleetVerdict` with `verdict`, `confidence`, `implicated_agent_ids`, and `dry_run` status.

> Note: Trigger is subject to `FLEET_SENTINEL_DRY_RUN`. If `dry_run=true`, no payload will be submitted to the Guardian Brain even on a `COLLUDING` verdict.

---

## 6. Demoting a Fleet-Promoted Semantic Entity

If a fleet-scope entity promotion was incorrect (false positive), the two-step rollback is:

**Step 1 — Demote the entity:**
```http
DELETE /api/fleet/correlations/<entity_id>/promote
Authorization: Bearer <admin-token>
```
Sets `scope = 'session'` on the `memory_semantic` row.

**Step 2 — Remove the Cold Memory fast-path signature (if created):**
```http
DELETE /api/memory/signatures/<sig_id>
Authorization: Bearer <admin-token>
```

> ⚠️ Two steps are required because promotion creates two artifacts (entity scope + optional Cold Memory signature). Rollback requires an explicit decision on each. This is intentional (D-25).

---

## 7. Configuration Quick Reference

| Env Var | Default | Description |
|---------|---------|-------------|
| `BUTTERCLAW_FLEET_DB_PATH` | `./fleet.db` | Fleet SQLite database path |
| `BUTTERCLAW_FLEET_SENTINEL_DRY_RUN` | `true` | Suppress Guardian Brain escalation |
| `BUTTERCLAW_SENTINEL_INTERVAL_HOURS` | `4` | Proactive Fleet Sentinel cycle interval |
| `BUTTERCLAW_SENTINEL_MIN_AGENTS` | `2` | Min agents before Fleet Sentinel runs |
| `BUTTERCLAW_COLLUSION_WINDOW_SECONDS` | `180` | Sliding window for collusion role assignment |
| `BUTTERCLAW_CORRELATION_FLEET_THRESHOLD` | `3` | Distinct agents for a CorrelationEvent |
| `BUTTERCLAW_TRUST_PROPAGATION_DEPTH` | `1` | Taint propagation hops (1 or 2) |
| `BUTTERCLAW_REPUTATION_DECAY_RATIO` | `3.0` | Taint penalty multiplier vs. clean recovery |
| `BUTTERCLAW_CIRCUIT_BREAKER_THRESHOLD` | `3` | LLM errors before circuit opens |
| `BUTTERCLAW_FLEET_SENTINEL_MIN_INTERVAL_SECONDS` | `30` | Rate limit between Fleet Sentinel LLM calls |
| `BUTTERCLAW_MAX_CONCURRENT_LLM` | `2` | Max simultaneous LLM hemisphere calls |

---

*Butterclaw Engineering — v0.9.0 Runbook — 2026-09-15*

---

## Related Documentation

* [`API.md`](API.md) — Full endpoint reference (77 routes, 4-tier RBAC)
* [`ARCHITECTURE.md`](ARCHITECTURE.md) — System design, trust boundaries, invariants, design decisions
* [`DEPLOYMENT.md`](DEPLOYMENT.md) — Docker, systemd, nginx, backup configuration
* [`SECURITY.md`](SECURITY.md) — Threat model, attack surfaces, responsible disclosure
* [`THREAT_MODEL.md`](THREAT_MODEL.md) — Updated threat model
