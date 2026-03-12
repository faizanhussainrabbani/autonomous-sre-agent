"""
AWS Resource Metadata Fetcher — retrieves configuration context for AWS resources.

Provides concrete resource configuration data (memory limits, timeouts,
concurrency, task counts) that the LLM can use for more precise diagnosis
and remediation suggestions.

Implements: Area 8 — Resource Metadata Enrichment
Validates: AC-CW-5.1 through AC-CW-5.5
"""

from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class AWSResourceMetadataFetcher:
    """Fetches configuration metadata for AWS compute resources.

    All methods return ``dict[str, Any]`` and never raise exceptions
    to callers — failures are logged and return empty dicts.
    """

    def __init__(
        self,
        lambda_client: Any | None = None,
        ecs_client: Any | None = None,
        autoscaling_client: Any | None = None,
    ) -> None:
        self._lambda = lambda_client
        self._ecs = ecs_client
        self._autoscaling = autoscaling_client

    async def fetch_lambda_context(self, function_name: str) -> dict[str, Any]:
        """Fetch Lambda function configuration.

        Returns:
            Dict with memory_mb, timeout_s, runtime, reserved_concurrency,
            last_modified, handler, code_size_bytes. Empty dict on failure.
        """
        if self._lambda is None:
            return {}

        try:
            config = self._lambda.get_function_configuration(
                FunctionName=function_name
            )
            return {
                "memory_mb": config.get("MemorySize", 0),
                "timeout_s": config.get("Timeout", 0),
                "runtime": config.get("Runtime", "unknown"),
                "handler": config.get("Handler", ""),
                "code_size_bytes": config.get("CodeSize", 0),
                "last_modified": config.get("LastModified", ""),
                "reserved_concurrency": self._get_lambda_concurrency(function_name),
                "layers": [
                    layer.get("Arn", "") for layer in config.get("Layers", [])
                ],
            }
        except Exception as exc:
            logger.warning(
                "resource_metadata_lambda_failed",
                function=function_name,
                error=str(exc),
            )
            return {}

    async def fetch_ecs_context(
        self, cluster: str, service: str
    ) -> dict[str, Any]:
        """Fetch ECS service configuration.

        Returns:
            Dict with desired_count, running_count, pending_count,
            task_definition, deployment_status, launch_type. Empty dict on failure.
        """
        if self._ecs is None:
            return {}

        try:
            response = self._ecs.describe_services(
                cluster=cluster, services=[service]
            )
            services = response.get("services", [])
            if not services:
                return {}

            svc = services[0]
            deployments = svc.get("deployments", [])
            primary_deployment = deployments[0] if deployments else {}

            return {
                "desired_count": svc.get("desiredCount", 0),
                "running_count": svc.get("runningCount", 0),
                "pending_count": svc.get("pendingCount", 0),
                "task_definition": svc.get("taskDefinition", ""),
                "launch_type": svc.get("launchType", ""),
                "deployment_status": primary_deployment.get("status", ""),
                "deployment_rollout_state": primary_deployment.get(
                    "rolloutState", ""
                ),
                "service_status": svc.get("status", ""),
            }
        except Exception as exc:
            logger.warning(
                "resource_metadata_ecs_failed",
                cluster=cluster,
                service=service,
                error=str(exc),
            )
            return {}

    async def fetch_ec2_asg_context(self, asg_name: str) -> dict[str, Any]:
        """Fetch EC2 Auto Scaling Group configuration.

        Returns:
            Dict with desired_capacity, min_size, max_size, instances,
            health_status. Empty dict on failure.
        """
        if self._autoscaling is None:
            return {}

        try:
            response = self._autoscaling.describe_auto_scaling_groups(
                AutoScalingGroupNames=[asg_name]
            )
            groups = response.get("AutoScalingGroups", [])
            if not groups:
                return {}

            asg = groups[0]
            instances = asg.get("Instances", [])

            return {
                "desired_capacity": asg.get("DesiredCapacity", 0),
                "min_size": asg.get("MinSize", 0),
                "max_size": asg.get("MaxSize", 0),
                "instance_count": len(instances),
                "healthy_count": sum(
                    1
                    for i in instances
                    if i.get("HealthStatus", "").upper() == "HEALTHY"
                ),
                "unhealthy_count": sum(
                    1
                    for i in instances
                    if i.get("HealthStatus", "").upper() != "HEALTHY"
                ),
                "availability_zones": asg.get("AvailabilityZones", []),
                "launch_template": asg.get("LaunchTemplate", {}).get(
                    "LaunchTemplateName", ""
                ),
            }
        except Exception as exc:
            logger.warning(
                "resource_metadata_asg_failed",
                asg_name=asg_name,
                error=str(exc),
            )
            return {}

    def _get_lambda_concurrency(self, function_name: str) -> int | None:
        """Get reserved concurrency for a Lambda function."""
        try:
            response = self._lambda.get_function_concurrency(
                FunctionName=function_name
            )
            return response.get("ReservedConcurrentExecutions")
        except Exception:
            return None
