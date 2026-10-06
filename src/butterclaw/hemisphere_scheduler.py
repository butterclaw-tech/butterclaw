"""
hemisphere_scheduler.py — Butterclaw v0.9.0
Priority queue + circuit breaker for all 5 LLM hemispheres.

Role: Manage concurrent hemisphere invocations, enforce the MAX_CONCURRENT_LLM
    cap (Guardian Brain exempt), and provide circuit-breaker semantics for
    LLM failures.

Priority assignments (lower number = higher priority):
    guardian_brain   0  — always admitted, cap-exempt
    auditor          1  (scheduled and reactive)
    fleet_sentinel   2  scheduled | 1 reactive (live swarm events)
    loop_proposer    3
    dream_weaver     4

Circuit breaker:
    After CIRCUIT_BREAKER_THRESHOLD consecutive LLM errors, the circuit opens.
    Non-Guardian-Brain invocations are rejected until CIRCUIT_BREAKER_RESET_SECONDS
    elapses and a half-open retry succeeds.

Prometheus metrics (registered by server.py):
    butterclaw_hemisphere_queue_length          Gauge
    butterclaw_hemisphere_invocations_total     Counter  (label: hemisphere)
    butterclaw_hemisphere_latency_seconds       Histogram
    butterclaw_hemisphere_errors_total          Counter  (label: hemisphere)
    butterclaw_circuit_breaker_state            Gauge    (0=closed,1=half-open,2=open)
    butterclaw_hemisphere_queue_wait_seconds    Histogram

Per R-05.
"""

from __future__ import annotations

import heapq
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config defaults (overridden by server.py from env)
# ---------------------------------------------------------------------------
MAX_CONCURRENT_LLM: int = 2
CIRCUIT_BREAKER_THRESHOLD: int = 3
CIRCUIT_BREAKER_RESET_SECONDS: int = 60

# ---------------------------------------------------------------------------
# Circuit breaker states
# ---------------------------------------------------------------------------
_CB_CLOSED = 0
_CB_HALF_OPEN = 1
_CB_OPEN = 2

_CB_STATE_NAMES = {_CB_CLOSED: "closed", _CB_HALF_OPEN: "half-open", _CB_OPEN: "open"}

# ---------------------------------------------------------------------------
# Priority map — lower value = higher priority (R-05)
# ---------------------------------------------------------------------------
HEMISPHERE_PRIORITIES = {
    "guardian_brain": 0,
    "auditor": 1,
    "fleet_sentinel_reactive": 1,
    "fleet_sentinel": 2,
    "loop_proposer": 3,
    "dream_weaver": 4,
}
GUARDIAN_BRAIN = "guardian_brain"


@dataclass(order=True)
class _QueueItem:
    priority: int
    enqueued_at: float
    hemisphere: str = field(compare=False)
    fn: Callable = field(compare=False)
    args: tuple = field(compare=False)
    kwargs: dict = field(compare=False)
    result_holder: list = field(compare=False)   # [result] or [None, exception]
    done_event: threading.Event = field(compare=False)


class HemisphereScheduler:
    """
    Priority-queue-based scheduler for all five LLM hemispheres.

    Usage (in server.py):
        scheduler = HemisphereScheduler()
        scheduler.start()

        # Example: schedule a Fleet Sentinel reactive invocation
        verdict = scheduler.submit(
            hemisphere="fleet_sentinel_reactive",
            fn=fleet_sentinel.run_reactive,
            args=(triggering_event,),
        )
    """

    def __init__(
        self,
        max_concurrent: int = MAX_CONCURRENT_LLM,
        circuit_breaker_threshold: int = CIRCUIT_BREAKER_THRESHOLD,
        circuit_breaker_reset_seconds: int = CIRCUIT_BREAKER_RESET_SECONDS,
        metrics_registry=None,   # optional prometheus_client registry
    ) -> None:
        self._max_concurrent = max_concurrent
        self._cb_threshold = circuit_breaker_threshold
        self._cb_reset = circuit_breaker_reset_seconds
        self._metrics = metrics_registry

        self._queue: list[_QueueItem] = []
        self._queue_lock = threading.Lock()
        self._semaphore = threading.Semaphore(max_concurrent)
        self._worker_thread: Optional[threading.Thread] = None

        # Circuit breaker state
        self._cb_state = _CB_CLOSED
        self._cb_consecutive_errors = 0
        self._cb_opened_at: Optional[float] = None
        self._cb_lock = threading.Lock()

        # Prometheus-compatible counters (noop stubs — replaced by server.py)
        self._invocations: dict[str, int] = {}
        self._errors: dict[str, int] = {}
        self._queue_length: int = 0

        logger.info(
            "HemisphereScheduler initialised (max_concurrent=%d, cb_threshold=%d, cb_reset=%ds)",
            max_concurrent, circuit_breaker_threshold, circuit_breaker_reset_seconds,
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the background dispatch thread."""
        self._worker_thread = threading.Thread(
            target=self._dispatch_loop,
            daemon=True,
            name="hemisphere-scheduler",
        )
        self._worker_thread.start()
        logger.info("HemisphereScheduler: dispatch thread started")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def submit(
        self,
        hemisphere: str,
        fn: Callable,
        args: tuple = (),
        kwargs: Optional[dict] = None,
        block: bool = True,
        timeout: Optional[float] = None,
    ):
        """
        Submit a hemisphere invocation to the priority queue.

        Parameters
        ----------
        hemisphere : str
            Must be a key in HEMISPHERE_PRIORITIES.
        fn : callable
            The hemisphere's invocation function.
        args / kwargs :
            Arguments to pass to fn.
        block : bool
            If True (default), block until the invocation completes and return
            the result. If False, return immediately with None.
        timeout : float, optional
            Maximum seconds to wait when block=True. Returns None on timeout.

        Returns
        -------
        Result of fn(*args, **kwargs), or None if non-blocking / timed out.
        Raises the original exception if the hemisphere call raised.
        """
        priority = HEMISPHERE_PRIORITIES.get(hemisphere, 99)
        done_event = threading.Event()
        result_holder: list = []

        item = _QueueItem(
            priority=priority,
            enqueued_at=time.monotonic(),
            hemisphere=hemisphere,
            fn=fn,
            args=args,
            kwargs=kwargs or {},
            result_holder=result_holder,
            done_event=done_event,
        )

        with self._queue_lock:
            heapq.heappush(self._queue, item)
            self._queue_length += 1

        logger.debug(
            "HemisphereScheduler.submit: hemisphere=%s priority=%d queue_length=%d",
            hemisphere, priority, self._queue_length,
        )

        if not block:
            return None

        done_event.wait(timeout=timeout)
        if not done_event.is_set():
            return None  # timed out

        if len(result_holder) == 2 and result_holder[0] is None:
            raise result_holder[1]   # re-raise original exception
        return result_holder[0] if result_holder else None

    # ------------------------------------------------------------------
    # Internal dispatch loop
    # ------------------------------------------------------------------

    def _dispatch_loop(self) -> None:
        while True:
            item: Optional[_QueueItem] = None
            with self._queue_lock:
                if self._queue:
                    item = heapq.heappop(self._queue)
                    self._queue_length -= 1

            if item is None:
                time.sleep(0.05)
                continue

            is_guardian = item.hemisphere == GUARDIAN_BRAIN

            # Circuit breaker check (Guardian Brain bypasses)
            if not is_guardian and not self._cb_allow():
                logger.warning(
                    "HemisphereScheduler: circuit OPEN — rejecting hemisphere=%s",
                    item.hemisphere,
                )
                item.result_holder.extend([None, RuntimeError("Circuit breaker open")])
                item.done_event.set()
                continue

            # Acquire concurrency slot (Guardian Brain skips semaphore)
            if not is_guardian:
                acquired = self._semaphore.acquire(timeout=30)
                if not acquired:
                    logger.warning(
                        "HemisphereScheduler: semaphore timeout for hemisphere=%s",
                        item.hemisphere,
                    )
                    item.result_holder.extend([None, RuntimeError("Concurrency slot timeout")])
                    item.done_event.set()
                    continue

            wait_seconds = time.monotonic() - item.enqueued_at
            logger.debug(
                "HemisphereScheduler: dispatching hemisphere=%s wait=%.2fs",
                item.hemisphere, wait_seconds,
            )

            # Dispatch in a new thread to keep the dispatch loop free
            t = threading.Thread(
                target=self._run_item,
                args=(item, is_guardian),
                daemon=True,
                name=f"hemisphere-{item.hemisphere}",
            )
            t.start()

    def _run_item(self, item: _QueueItem, is_guardian: bool) -> None:
        start = time.monotonic()
        try:
            result = item.fn(*item.args, **item.kwargs)
            item.result_holder.append(result)
            self._cb_record_success(item.hemisphere)
        except Exception as exc:
            logger.exception(
                "HemisphereScheduler: hemisphere=%s raised %s", item.hemisphere, exc
            )
            item.result_holder.extend([None, exc])
            self._cb_record_error(item.hemisphere)
        finally:
            item.done_event.set()
            if not is_guardian:
                self._semaphore.release()
            elapsed = time.monotonic() - start
            logger.debug(
                "HemisphereScheduler: hemisphere=%s completed in %.3fs", item.hemisphere, elapsed
            )

    # ------------------------------------------------------------------
    # Circuit breaker
    # ------------------------------------------------------------------

    def _cb_allow(self) -> bool:
        """Return True if the circuit breaker allows the invocation."""
        with self._cb_lock:
            if self._cb_state == _CB_CLOSED:
                return True
            if self._cb_state == _CB_OPEN:
                elapsed = time.monotonic() - (self._cb_opened_at or 0)
                if elapsed >= self._cb_reset:
                    self._cb_state = _CB_HALF_OPEN
                    logger.info("HemisphereScheduler: circuit → half-open")
                    return True  # Allow one probe
                return False
            # HALF_OPEN — allow exactly one probe at a time
            return True

    def _cb_record_success(self, hemisphere: str) -> None:
        with self._cb_lock:
            prev_state = self._cb_state
            self._cb_consecutive_errors = 0
            self._cb_state = _CB_CLOSED
        if prev_state != _CB_CLOSED:
            logger.info(
                "HemisphereScheduler: circuit → closed (hemisphere=%s succeeded)", hemisphere
            )
        self._invocations[hemisphere] = self._invocations.get(hemisphere, 0) + 1

    def _cb_record_error(self, hemisphere: str) -> None:
        self._errors[hemisphere] = self._errors.get(hemisphere, 0) + 1
        if hemisphere == GUARDIAN_BRAIN:
            return  # Guardian Brain errors never trip the breaker
        with self._cb_lock:
            self._cb_consecutive_errors += 1
            if (
                self._cb_state != _CB_OPEN
                and self._cb_consecutive_errors >= self._cb_threshold
            ):
                self._cb_state = _CB_OPEN
                self._cb_opened_at = time.monotonic()
                logger.warning(
                    "HemisphereScheduler: circuit → OPEN after %d consecutive errors",
                    self._cb_consecutive_errors,
                )

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def get_status(self) -> dict:
        with self._cb_lock:
            cb_state = self._cb_state
            cb_errors = self._cb_consecutive_errors
        with self._queue_lock:
            q_len = self._queue_length
        return {
            "queue_length": q_len,
            "circuit_breaker_state": _CB_STATE_NAMES[cb_state],
            "circuit_breaker_state_code": cb_state,
            "consecutive_errors": cb_errors,
            "max_concurrent": self._max_concurrent,
            "invocations": dict(self._invocations),
            "errors": dict(self._errors),
        }
