"""Per-request wall-clock budget shared by synchronous and async stages."""
from contextlib import contextmanager
from contextvars import ContextVar
import time

_deadline: ContextVar[float | None] = ContextVar("verification_deadline", default=None)


def remaining_seconds(stage_limit: float) -> float:
    deadline = _deadline.get()
    return float(stage_limit) if deadline is None else max(0.0, min(float(stage_limit), deadline - time.monotonic()))


@contextmanager
def request_budget(seconds: float = 225.0):
    previous = _deadline.get()
    deadline = time.monotonic() + seconds
    token = _deadline.set(min(previous, deadline) if previous is not None else deadline)
    try:
        yield
    finally:
        _deadline.reset(token)
