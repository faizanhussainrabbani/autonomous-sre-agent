"""
AWS Error Mapper — Translates botocore ClientErrors to canonical CloudOperatorErrors.

Phase 1.5.1: Added to ensure accurate resilience behavior (e.g. not retrying 404s)
and better support for Chaos Engineering fault injection tests.
"""

from typing import Any

from sre_agent.adapters.cloud.resilience import AuthenticationError
from sre_agent.adapters.cloud.resilience import CloudOperatorError
from sre_agent.adapters.cloud.resilience import RateLimitError
from sre_agent.adapters.cloud.resilience import ResourceNotFoundError
from sre_agent.adapters.cloud.resilience import TransientError


def map_boto_error(exc: Exception) -> CloudOperatorError:
    """Map a boto3 exception to our canonical resilience exceptions.
    
    If it's not a boto3 ClientError or recognized type, it passes through
    as a base exception or TransientError depending on the hierarchy.
    """
    if isinstance(exc, (ConnectionError, TimeoutError)):
        return TransientError(f"AWS Connection/Timeout Error: {exc}")

    error_code = getattr(exc, "response", {}).get("Error", {}).get("Code", "")
    status_code = getattr(exc, "response", {}).get("ResponseMetadata", {}).get("HTTPStatusCode", 0)

    # 1. Authentication / Authorization
    if status_code in (401, 403) or error_code in (
        "AccessDenied", "AccessDeniedException", "AuthFailure", "UnauthorizedOperation",
    ):
        return AuthenticationError(f"AWS Auth Error ({error_code}): {exc}")

    # 2. Not Found
    if status_code == 404 or "NotFound" in error_code:
        return ResourceNotFoundError(f"AWS Resource Not Found ({error_code}): {exc}")

    # 3. Rate Limiting / Throttling
    if status_code == 429 or "Throttling" in error_code or "ProvisionedThroughputExceeded" in error_code or "LimitExceeded" in error_code:
        return RateLimitError(f"AWS Rate Limit Exceeded ({error_code}): {exc}")

    # 4. Server Errors (Transient)
    if status_code >= 500 or "ServiceUnavailable" in error_code or "InternalFailure" in error_code:
        return TransientError(f"AWS Transient Error ({status_code} - {error_code}): {exc}")

    # 5. Default fallback for other ClientErrors (e.g. 400 Bad Request) - Non-retryable
    if type(exc).__name__ == "ClientError":
        return CloudOperatorError(f"AWS Client Error ({status_code} - {error_code}): {exc}")

    # If it's some other generic exception not caught above, wrap it generically
    return CloudOperatorError(f"Unexpected AWS Error: {exc}")
