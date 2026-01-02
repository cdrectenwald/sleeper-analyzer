"""
Resilience patterns for external service calls.

This module provides:
- Retry with exponential backoff
- Circuit breaker pattern
- Timeout handling

Usage:
    from src.common.resilience import with_retry, circuit_breaker

    @with_retry(max_attempts=3, backoff_base=1.0)
    def call_external_api():
        return requests.get(url)

    @circuit_breaker("openai", failure_threshold=5)
    def call_openai():
        return client.chat.completions.create(...)
"""

from __future__ import annotations

import functools
import logging
import random
import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Callable, TypeVar, ParamSpec

log = logging.getLogger(__name__)

P = ParamSpec("P")
T = TypeVar("T")


class RetryError(Exception):
    """Raised when all retry attempts are exhausted."""
    
    def __init__(self, attempts: int, last_error: Exception) -> None:
        self.attempts = attempts
        self.last_error = last_error
        super().__init__(f"Failed after {attempts} attempts: {last_error}")


def with_retry(
    max_attempts: int = 3,
    backoff_base: float = 1.0,
    backoff_max: float = 30.0,
    jitter: bool = True,
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,),
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """
    Decorator that retries a function with exponential backoff.
    
    Args:
        max_attempts: Maximum number of attempts (including first try).
        backoff_base: Base delay in seconds (doubles each retry).
        backoff_max: Maximum delay between retries.
        jitter: Add random jitter to prevent thundering herd.
        retryable_exceptions: Tuple of exception types to retry on.
    
    Example:
        @with_retry(max_attempts=3, backoff_base=1.0)
        def flaky_api_call():
            return requests.get(url)
    """
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            last_error: Exception | None = None
            
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except retryable_exceptions as e:
                    last_error = e
                    
                    if attempt == max_attempts:
                        log.warning(
                            "Retry exhausted for %s after %d attempts: %s",
                            func.__name__, attempt, e
                        )
                        raise RetryError(attempt, e) from e
                    
                    # Calculate backoff delay
                    delay = min(backoff_base * (2 ** (attempt - 1)), backoff_max)
                    if jitter:
                        delay *= (0.5 + random.random())
                    
                    log.info(
                        "Retry %d/%d for %s after %.2fs: %s",
                        attempt, max_attempts, func.__name__, delay, e
                    )
                    time.sleep(delay)
            
            # Should never reach here, but satisfy type checker
            raise RetryError(max_attempts, last_error or Exception("Unknown error"))
        
        return wrapper
    return decorator


@dataclass
class CircuitState:
    """State for a single circuit breaker."""
    
    name: str
    failure_threshold: int = 5
    recovery_timeout: float = 30.0
    half_open_max_calls: int = 3
    
    # State tracking
    failures: int = 0
    successes: int = 0
    last_failure_time: float = 0.0
    state: str = "closed"  # closed, open, half_open
    half_open_calls: int = 0
    _lock: Lock = field(default_factory=Lock, repr=False)
    
    def record_success(self) -> None:
        """Record a successful call."""
        with self._lock:
            self.failures = 0
            if self.state == "half_open":
                self.successes += 1
                if self.successes >= self.half_open_max_calls:
                    log.info("Circuit %s: half_open -> closed (recovered)", self.name)
                    self.state = "closed"
                    self.half_open_calls = 0
                    self.successes = 0
    
    def record_failure(self) -> None:
        """Record a failed call."""
        with self._lock:
            self.failures += 1
            self.last_failure_time = time.time()
            
            if self.state == "half_open":
                log.warning("Circuit %s: half_open -> open (failed during probe)", self.name)
                self.state = "open"
                self.half_open_calls = 0
            elif self.state == "closed" and self.failures >= self.failure_threshold:
                log.warning(
                    "Circuit %s: closed -> open (threshold %d reached)",
                    self.name, self.failure_threshold
                )
                self.state = "open"
    
    def allow_request(self) -> bool:
        """Check if a request should be allowed through."""
        with self._lock:
            if self.state == "closed":
                return True
            
            if self.state == "open":
                # Check if we should transition to half_open
                if time.time() - self.last_failure_time >= self.recovery_timeout:
                    log.info("Circuit %s: open -> half_open (recovery timeout)", self.name)
                    self.state = "half_open"
                    self.half_open_calls = 0
                    self.successes = 0
                    return True
                return False
            
            # half_open: allow limited calls
            if self.half_open_calls < self.half_open_max_calls:
                self.half_open_calls += 1
                return True
            return False


# Global circuit breaker registry
_circuits: dict[str, CircuitState] = {}
_circuits_lock = Lock()


def get_circuit(
    name: str,
    failure_threshold: int = 5,
    recovery_timeout: float = 30.0,
) -> CircuitState:
    """Get or create a circuit breaker by name."""
    with _circuits_lock:
        if name not in _circuits:
            _circuits[name] = CircuitState(
                name=name,
                failure_threshold=failure_threshold,
                recovery_timeout=recovery_timeout,
            )
        return _circuits[name]


class CircuitOpenError(Exception):
    """Raised when circuit breaker is open and request is blocked."""
    
    def __init__(self, circuit_name: str) -> None:
        self.circuit_name = circuit_name
        super().__init__(f"Circuit '{circuit_name}' is open")


def circuit_breaker(
    name: str,
    failure_threshold: int = 5,
    recovery_timeout: float = 30.0,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """
    Decorator that applies circuit breaker pattern.
    
    Args:
        name: Unique name for this circuit breaker.
        failure_threshold: Number of failures before opening circuit.
        recovery_timeout: Seconds to wait before attempting recovery.
    
    Example:
        @circuit_breaker("openai", failure_threshold=5, recovery_timeout=60)
        def call_openai():
            return client.completions.create(...)
    """
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            circuit = get_circuit(name, failure_threshold, recovery_timeout)
            
            if not circuit.allow_request():
                raise CircuitOpenError(name)
            
            try:
                result = func(*args, **kwargs)
                circuit.record_success()
                return result
            except Exception as e:
                circuit.record_failure()
                raise
        
        return wrapper
    return decorator


def get_all_circuit_states() -> dict[str, dict[str, Any]]:
    """Get state of all circuit breakers for monitoring."""
    with _circuits_lock:
        return {
            name: {
                "state": c.state,
                "failures": c.failures,
                "last_failure_time": c.last_failure_time,
            }
            for name, c in _circuits.items()
        }
