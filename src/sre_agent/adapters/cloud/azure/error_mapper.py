"""
Azure Error Mapper — Translates azure-core HttpResponseErrors to canonical
CloudOperatorErrors.

Phase 1.5.1: Added to ensure accurate resilience behavior (e.g. not retrying 404s)
and better support for fault injection tests.
"""

from typing import Any

from sre_agent.adapters.cloud.resilience import AuthenticationError
from sre_agent.adapters.cloud.resilience import CloudOperatorError
from sre_agent.adapters.cloud.resilience import RateLimitError
from sre_agent.adapters.cloud.resilience import ResourceNotFoundError
from sre_agent.adapters.cloud.resilience import TransientError


def map_azure_error(exc: Exception) -> CloudOperatorError:
    """Map an Azure HttpResponseError to our canonical resilience exceptions.
    """
    if isinstance(exc, (ConnectionError, TimeoutError)):
        return TransientError(f"Azure Connection/Timeout Error: {exc}")

    status_code = getattr(exc, "status_code", 0)

    # 1. Authentication / Authorization
    if status_code in (401, 403):
        return AuthenticationError(f"Azure Auth Error ({status_code}): {exc}")

    # 2. Not Found
    if status_code == 404:
        return ResourceNotFoundError(f"Azure Resource Not Found ({status_code}): {exc}")

    # 3. Rate Limiting / Throttling
    if status_code == 429:
        return RateLimitError(f"Azure Rate Limit Exceeded ({status_code}): {exc}")

    # 4. Server Errors (Transient)
    if status_code >= 500:
        return TransientError(f"Azure Transient Error ({status_code}): {exc}")

    # 5. Default fallback for other ClientErrors (e.g. 400 Bad Request) - Non-retryable
    if type(exc).__name__ == "HttpResponseError" or status_code:
        return CloudOperatorError(f"Azure Client Error ({status_code}): {exc}")

    # If it's some other generic exception not caught above
    return CloudOperatorError(f"Unexpected Azure Error: {exc}")
