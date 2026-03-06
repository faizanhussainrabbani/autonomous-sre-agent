"""
Unit tests for Azure Error Mapper.
"""
import pytest

# Mock Azure HttpResponseError to avoid hard dependency in tests if not installed
class MockHttpResponseError(Exception):
    def __init__(self, status_code: int):
        self.status_code = status_code
        super().__init__(f"Azure Error {status_code}")

from sre_agent.adapters.cloud.azure.error_mapper import map_azure_error
from sre_agent.adapters.cloud.resilience import (
    AuthenticationError,
    CloudOperatorError,
    RateLimitError,
    ResourceNotFoundError,
    TransientError,
)

def test_map_authentication_error():
    exc = MockHttpResponseError(401)
    mapped = map_azure_error(exc)
    assert isinstance(mapped, AuthenticationError)
    
    exc2 = MockHttpResponseError(403)
    mapped2 = map_azure_error(exc2)
    assert isinstance(mapped2, AuthenticationError)

def test_map_resource_not_found():
    exc = MockHttpResponseError(404)
    mapped = map_azure_error(exc)
    assert isinstance(mapped, ResourceNotFoundError)

def test_map_rate_limit():
    exc = MockHttpResponseError(429)
    mapped = map_azure_error(exc)
    assert isinstance(mapped, RateLimitError)

def test_map_transient_error():
    exc = MockHttpResponseError(500)
    mapped = map_azure_error(exc)
    assert isinstance(mapped, TransientError)
    
    exc2 = MockHttpResponseError(503)
    mapped2 = map_azure_error(exc2)
    assert isinstance(mapped2, TransientError)

def test_map_generic_client_error():
    exc = MockHttpResponseError(400)
    # Set class name to match expected Azure error
    exc.__class__.__name__ = "HttpResponseError"
    mapped = map_azure_error(exc)
    assert type(mapped) is CloudOperatorError  # Base class, non-retryable

def test_pass_through_python_errors():
    exc = TimeoutError("Network timeout")
    mapped = map_azure_error(exc)
    assert isinstance(mapped, TransientError)
