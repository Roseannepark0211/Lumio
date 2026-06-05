"""Tests for utils/error_types.py"""
import pytest
from getvp.utils.error_types import ErrorCategory, classify_error


class TestClassifyCookieErrors:
    def test_login_keyword(self):
        assert classify_error("login required") == ErrorCategory.COOKIE_EXPIRED

    def test_cookie_keyword(self):
        assert classify_error("Cookie expired") == ErrorCategory.COOKIE_EXPIRED

    def test_401_keyword(self):
        assert classify_error("HTTP 401 Unauthorized") == ErrorCategory.COOKIE_EXPIRED

    def test_session_keyword(self):
        assert classify_error("session invalid") == ErrorCategory.COOKIE_EXPIRED

    def test_authentication_keyword(self):
        assert classify_error("authentication failed") == ErrorCategory.COOKIE_EXPIRED


class TestClassifyNetworkErrors:
    def test_connection_error_type(self):
        assert classify_error(ConnectionError("refused")) == ErrorCategory.NETWORK

    def test_timeout_error_type(self):
        assert classify_error(TimeoutError("timed out")) == ErrorCategory.NETWORK

    def test_os_error_type(self):
        assert classify_error(OSError("network unreachable")) == ErrorCategory.NETWORK

    def test_connection_keyword(self):
        assert classify_error("connection reset by peer") == ErrorCategory.NETWORK

    def test_dns_keyword(self):
        assert classify_error("DNS resolve failed") == ErrorCategory.NETWORK


class TestClassifyRateLimitErrors:
    def test_429_keyword(self):
        assert classify_error("HTTP 429 Too Many Requests") == ErrorCategory.RATE_LIMITED

    def test_rate_limit_keyword(self):
        assert classify_error("rate limit exceeded") == ErrorCategory.RATE_LIMITED

    def test_slow_down_keyword(self):
        assert classify_error("slow down, too many requests") == ErrorCategory.RATE_LIMITED


class TestClassifyContentErrors:
    def test_404_keyword(self):
        assert classify_error("404 not found") == ErrorCategory.CONTENT_REMOVED

    def test_unavailable_keyword(self):
        assert classify_error("video unavailable") == ErrorCategory.CONTENT_REMOVED

    def test_private_keyword(self):
        assert classify_error("this account is private") == ErrorCategory.CONTENT_REMOVED

    def test_deleted_keyword(self):
        assert classify_error("content has been deleted") == ErrorCategory.CONTENT_REMOVED


class TestClassifyUnknown:
    def test_random_string(self):
        assert classify_error("something completely random") == ErrorCategory.UNKNOWN

    def test_generic_exception(self):
        assert classify_error(ValueError("bad value")) == ErrorCategory.UNKNOWN


class TestPriority:
    def test_cookie_over_network(self):
        assert classify_error("login failed due to connection") == ErrorCategory.COOKIE_EXPIRED

    def test_rate_over_content(self):
        assert classify_error("429 rate limit not found") == ErrorCategory.RATE_LIMITED
