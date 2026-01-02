import logging
import time
from contextlib import contextmanager
from typing import Generator


def setup_logging(level: str = "INFO") -> None:
    """Configure structured logging for the application."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


@contextmanager
def log_timing(logger: logging.Logger, operation: str) -> Generator[None, None, None]:
    """Context manager to log the duration of an operation."""
    start = time.perf_counter()
    logger.info("Starting: %s", operation)
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        logger.info("Completed: %s (%.2fs)", operation, elapsed)
