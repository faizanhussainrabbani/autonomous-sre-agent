"""
Mock Lambda: Payment Processor
==============================

A deliberately vulnerable Lambda function deployed to LocalStack for the
Live Incident Response Demo.  When invoked with ``{"induce_error": true}``
it simulates a database connection pool exhaustion crash, causing
CloudWatch to increment the ``Errors`` metric and trigger the alarm chain.

Normal invocations return a 200 success response.
"""

import json


def handler(event, context):
    """Lambda entry-point.

    Parameters
    ----------
    event : dict
        The invocation payload.  Set ``induce_error`` to ``true``
        to simulate a runtime failure.
    context : object
        AWS Lambda context (unused in mock).

    Returns
    -------
    dict
        Standard Lambda proxy response.

    Raises
    ------
    RuntimeError
        When ``induce_error`` is truthy, simulating a database
        connection pool exhaustion.
    """
    if event.get("induce_error"):
        raise RuntimeError(
            "Database connection pool exhausted: "
            "active=128/128, wait_queue=347, "
            "avg_checkout_ms=12400"
        )

    return {
        "statusCode": 200,
        "body": json.dumps({"message": "Payment processed successfully"}),
    }
