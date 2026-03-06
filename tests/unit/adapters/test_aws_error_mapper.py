"""
Unit tests for AWS Error Mapper.
"""
import pytest
from botocore.exceptions import ClientError

from sre_agent.adapters.cloud.aws.error_mapper import map_boto_error
from sre_agent.adapters.cloud.resilience import (
    AuthenticationError,
    CloudOperatorError,
    RateLimitError,
    ResourceNotFoundError,
    TransientError,
)

def create_client_error(status_code: int, error_code: str, message: str = "Error") -> ClientError:
    return ClientError(
        error_response={"Error": {"Code": error_code, "Message": message}, "ResponseMetadata": {"HTTPStatusCode": status_code}},
        operation_name="TestOp",
    )

def test_map_authentication_error_by_status():
    exc = create_client_error(403, "SomeRandomCode")
    mapped = map_boto_error(exc)
    assert isinstance(mapped, AuthenticationError)

def test_map_authentication_error_by_code():
    exc = create_client_error(400, "AccessDenied")
    mapped = map_boto_error(exc)
    assert isinstance(mapped, AuthenticationError)

def test_map_resource_not_found():
    exc = create_client_error(404, "SomeRandomCode")
    mapped = map_boto_error(exc)
    assert isinstance(mapped, ResourceNotFoundError)
    
    exc2 = create_client_error(400, "ResourceNotFoundException")
    mapped2 = map_boto_error(exc2)
    assert isinstance(mapped2, ResourceNotFoundError)

def test_map_rate_limit():
    exc = create_client_error(429, "TooManyRequests")
    mapped = map_boto_error(exc)
    assert isinstance(mapped, RateLimitError)
    
    exc2 = create_client_error(400, "ProvisionedThroughputExceededException")
    mapped2 = map_boto_error(exc2)
    assert isinstance(mapped2, RateLimitError)

def test_map_transient_error():
    exc = create_client_error(503, "ServiceUnavailable")
    mapped = map_boto_error(exc)
    assert isinstance(mapped, TransientError)

def test_map_generic_client_error():
    exc = create_client_error(400, "ValidationException")
    mapped = map_boto_error(exc)
    assert type(mapped) is CloudOperatorError  # Base class, non-retryable
    assert not isinstance(mapped, TransientError)

def test_pass_through_python_errors():
    exc = ConnectionError("Network down")
    mapped = map_boto_error(exc)
    assert isinstance(mapped, TransientError)
