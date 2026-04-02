# aws-remediation-adapters Specification

## Purpose
TBD - created by archiving change phase-1-5-non-k8s-platforms. Update Purpose after archive.
## Requirements
### Requirement: ECS Cloud Operator
The system SHALL provide a `CloudOperatorPort` implementation for Amazon ECS that manages service capacities and task lifecycles via the boto3 SDK.

#### Scenario: Restarting an ECS Task
- **WHEN** the remediation engine issues a `restart_compute_unit` command
- **AND** the target compute mechanism is `CONTAINER_INSTANCE` on AWS ECS
- **THEN** the ECS adapter SHALL issue a `StopTask` API call to the ECS cluster
- **AND** rely on the ECS Service scheduler to start a replacement task automatically

#### Scenario: Scaling an ECS Service
- **WHEN** the remediation engine issues a `scale_capacity` command
- **AND** the target is an ECS Service
- **THEN** the ECS adapter SHALL issue an `UpdateService` API call
- **AND** modify the `desiredCount` to the requested new limit

### Requirement: EC2 Auto Scaling Operator
The system SHALL provide a `CloudOperatorPort` implementation for Amazon EC2 Auto Scaling Groups (ASG).

#### Scenario: Scaling an EC2 ASG
- **WHEN** the remediation engine issues a `scale_capacity` command
- **AND** the target is an EC2 ASG
- **THEN** the ASG adapter SHALL issue a `SetDesiredCapacity` API call via boto3

