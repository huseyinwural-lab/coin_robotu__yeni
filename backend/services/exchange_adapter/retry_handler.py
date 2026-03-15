import time
from typing import Callable


def with_retry(callable_fn: Callable, *, max_attempts: int = 3, backoff_seconds: float = 0.2):
    last_error = None
    for attempt in range(1, max_attempts + 1):
        try:
            return callable_fn()
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt >= max_attempts:
                break
            time.sleep(backoff_seconds * attempt)
    raise RuntimeError(f"retry_exhausted: {last_error}") from last_error
