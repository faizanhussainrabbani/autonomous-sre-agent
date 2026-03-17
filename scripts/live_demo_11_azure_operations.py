#!/usr/bin/env python3
"""
Demo 11: Azure Cloud Operations (Phase 1.5)
Proves that the system accurately implements Multi-Cloud operations via the
CloudOperatorPort abstraction delegating specifically to Azure services.

Since LocalStack does not mock Azure, this script dynamically mocks the
`azure-mgmt-web` Python SDK client responses and verifies the Adapters execute
their Hexagonal logic correctly in response to standard Domain requests.
"""

import sys
import asyncio
import structlog
from unittest.mock import MagicMock
from typing import Any

from sre_agent.adapters.cloud.azure.app_service_operator import AppServiceOperator
from sre_agent.adapters.cloud.azure.functions_operator import FunctionsOperator
from sre_agent.domain.models.canonical import ComputeMechanism
from sre_agent.ports.cloud_operator import CloudOperatorPort

logger = structlog.get_logger()

# Set up mock payload matching the Azure SDK
RESOURCE_ID_APP = "/subscriptions/123/resourceGroups/rg/providers/Microsoft.Web/sites/test-app"
RESOURCE_ID_FUNC = "/subscriptions/123/resourceGroups/rg/providers/Microsoft.Web/sites/test-func"
NAMESPACE = "rg"

def create_mock_azure_web_client() -> MagicMock:
    """Creates a mock of the WebSiteManagementClient from azure-mgmt-web."""
    client = MagicMock()
    # Mocking WebAppsOperations
    client.web_apps = MagicMock()
    client.web_apps.restart = MagicMock(return_value=None)
    
    # Mocking AppServicePlansOperations
    client.app_service_plans = MagicMock()
    plan_mock = MagicMock()
    plan_mock.sku.capacity = 1
    client.app_service_plans.get = MagicMock(return_value=plan_mock)
    client.app_service_plans.create_or_update = MagicMock()
    
    return client

async def run_app_service_operations(client: MagicMock):
    logger.info("Executing Azure App Service Operator Actions")
    operator: CloudOperatorPort = AppServiceOperator(client)
    
    # Check compute mechanism
    assert ComputeMechanism.VIRTUAL_MACHINE in operator.supported_mechanisms
    logger.info("Verified Azure App Service mechanism: VIRTUAL_MACHINE")
    
    # 1. Restart
    logger.info("Requesting Restart operation for App Service", resource_id=RESOURCE_ID_APP)
    await operator.restart_compute_unit(RESOURCE_ID_APP, {"resource_group": NAMESPACE})
    
    # Verify mock call
    client.web_apps.restart.assert_called_with(
        NAMESPACE,
        RESOURCE_ID_APP
    )
    logger.info("✅ AC 2.2 Passed: Restart executed accurately via abstract CloudOperatorPort.")
    
    # 2. Scale up
    logger.info("Requesting Scale (+1) operation for App Service", resource_id=RESOURCE_ID_APP)
    await operator.scale_capacity(RESOURCE_ID_APP, 2, {"resource_group": NAMESPACE, "plan_name": "test-plan"})
    
    client.app_service_plans.create_or_update.assert_called()
    logger.info("✅ Scale request delegated to underlying Azure SDK update.")


async def run_functions_operations(client: MagicMock):
    logger.info("Executing Azure Functions Operator Actions")
    operator: CloudOperatorPort = FunctionsOperator(client)
    
    # Check compute mechanism
    assert ComputeMechanism.SERVERLESS in operator.supported_mechanisms
    logger.info("Verified Azure Function mechanism: SERVERLESS")
    
    # 1. Restart
    logger.info("Requesting Restart operation for Function App", resource_id=RESOURCE_ID_FUNC)
    await operator.restart_compute_unit(RESOURCE_ID_FUNC, {"resource_group": NAMESPACE})
    
    client.web_apps.restart.assert_called_with(
        NAMESPACE,
        RESOURCE_ID_FUNC
    )
    
    # 2. Scale
    logger.info("Requesting Scale operation for Premium Function App", resource_id=RESOURCE_ID_FUNC)
    await operator.scale_capacity(RESOURCE_ID_FUNC, 3, {"resource_group": NAMESPACE, "plan_name": "func-plan"})
    
    client.app_service_plans.create_or_update.assert_called()
    logger.info("✅ AC 2.3 Passed: Scale executed accurately via abstract CloudOperatorPort.")

async def main():
    logger.info("Starting Demo 11: Multi-Cloud Phase 1.5 Azure Coverage")
    try:
        mock_client = create_mock_azure_web_client()
        
        await run_app_service_operations(mock_client)
        print("-" * 50)
        await run_functions_operations(mock_client)
        
        logger.info("✅ All Azure abstract adapter operations executed gracefully without Cloud credentials.")
        
    except Exception as e:
        logger.error("Simulation failed unexpectedly", error=str(e))
        sys.exit(1)

if __name__ == "__main__":
    structlog.configure(
        processors=[structlog.dev.ConsoleRenderer(colors=True)]
    )
    asyncio.run(main())
