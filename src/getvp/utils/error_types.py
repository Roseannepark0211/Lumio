from __future__ import annotations

from enum import Enum


class ErrorCategory(str, Enum):
    COOKIE_EXPIRED = "cookie_expired"
    NETWORK = "network"
    RATE_LIMITED = "rate_limited"
    CONTENT_REMOVED = "content_removed"
    PARSE_FAILED = "parse_failed"
    UNKNOWN = "unknown"


_COOKIE_KEYWORDS = {"login", "cookie", "401", "unauthorized", "authentication", "session"}
_NETWORK_KEYWORDS = {"connection", "timeout", "network", "dns", "resolve", "socket", "ssl", "reset", "refused", "unreachable", "offline"}
_RATE_KEYWORDS = {"429", "rate limit", "too many requests", "throttle", "slow down"}
_CONTENT_KEYWORDS = {"404", "not found", "unavailable", "private", "removed", "deleted", "gone", "no longer", "video unavailable"}


def classify_error(error: Exception | str) -> ErrorCategory:
    """Classify an error into a user-friendly category."""
    text = str(error).lower()

    if any(kw in text for kw in _COOKIE_KEYWORDS):
        return ErrorCategory.COOKIE_EXPIRED
    if any(kw in text for kw in _RATE_KEYWORDS):
        return ErrorCategory.RATE_LIMITED
    if any(kw in text for kw in _CONTENT_KEYWORDS):
        return ErrorCategory.CONTENT_REMOVED
    if any(kw in text for kw in _NETWORK_KEYWORDS):
        return ErrorCategory.NETWORK

    # Check exception types
    error_type = type(error).__name__
    if error_type in ("ConnectionError", "TimeoutError", "OSError"):
        return ErrorCategory.NETWORK
    if error_type in ("ExtractorError",):
        return ErrorCategory.PARSE_FAILED

    return ErrorCategory.UNKNOWN
