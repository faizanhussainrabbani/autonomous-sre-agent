"""
Tests for Phase 1.5 — Azure Cloud Operator Adapters.

Validates: AC-1.5.7 (Azure Adapters)
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from sre_agent.adapters.cloud.azure.app_service_operator import AppServiceOperator
from sre_agent.adapters.cloud.azure.functions_operator import FunctionsOperator


# ---------------------------------------------------------------------------
# App Service Operator — AC-1.5.7.1, AC-1.5.7.2
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_app_service_restart():
    """AC-1.5.7.1: restart issues a restart call to web_apps."""
    mock_web = MagicMock()
    op = AppServiceOperator(web_client=mock_web)

    result = await op.restart_compute_unit(
        resource_id="my-webapp",
        metadata={"resource_group": "prod-rg"},
    )

    mock_web.web_apps.restart.assert_called_once_with("prod-rg", "my-webapp")
    assert result["action"] == "restart"


@pytest.mark.asyncio
async def test_app_service_scale():
    """AC-1.5.7.2: scale modifies App Service Plan instance count."""
    mock_plan = MagicMock()
    mock_plan.sku.capacity = 1

    mock_web = MagicMock()
    mock_web.app_service_plans.get.return_value = mock_plan
    op = AppServiceOperator(web_client=mock_web)

    await op.scale_capacity(
        resource_id="my-webapp",
        desired_count=3,
        metadata={"resource_group": "prod-rg", "plan_name": "my-plan"},
    )

    mock_web.app_service_plans.get.assert_called_once_with("prod-rg", "my-plan")
    assert mock_plan.sku.capacity == 3
    mock_web.app_service_plans.create_or_update.assert_called_once()


# ---------------------------------------------------------------------------
# Functions Operator — AC-1.5.7.3
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_functions_restart():
    """AC-1.5.7.3: Functions restart calls web_apps.restart."""
    mock_web = MagicMock()
    op = FunctionsOperator(web_client=mock_web)

    result = await op.restart_compute_unit(
        resource_id="my-function-app",
        metadata={"resource_group": "prod-rg"},
    )

    mock_web.web_apps.restart.assert_called_once_with("prod-rg", "my-function-app")
    assert result["action"] == "restart"


@pytest.mark.asyncio
async def test_functions_scale_premium():
    """AC-1.5.7.3: Functions scale modifies Premium plan instance count."""
    mock_plan = MagicMock()
    mock_plan.sku.capacity = 1

    mock_web = MagicMock()
    mock_web.app_service_plans.get.return_value = mock_plan
    op = FunctionsOperator(web_client=mock_web)

    await op.scale_capacity(
        resource_id="my-function-app",
        desired_count=5,
        metadata={"resource_group": "prod-rg", "plan_name": "premium-plan"},
    )

    assert mock_plan.sku.capacity == 5
    mock_web.app_service_plans.create_or_update.assert_called_once()
