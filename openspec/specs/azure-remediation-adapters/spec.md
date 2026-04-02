# azure-remediation-adapters Specification

## Purpose
TBD - created by archiving change phase-1-5-non-k8s-platforms. Update Purpose after archive.
## Requirements
### Requirement: Azure App Service Operator
The system SHALL provide a `CloudOperatorPort` implementation for Azure App Service that manages restart and scaling lifecycles.

#### Scenario: Restarting an App Service Web App
- **WHEN** the remediation engine issues a `restart_compute_unit` command
- **AND** the target compute mechanism is Azure App Service
- **THEN** the Azure adapter SHALL issue a POST request to the Azure Resource Manager `webApps.restart` endpoint
- **AND** verify the restart completed successfully

#### Scenario: Scaling an App Service Plan
- **WHEN** the remediation engine issues a `scale_capacity` command
- **AND** the target is an Azure App Service Plan
- **THEN** the Azure adapter SHALL modify the instance count of the App Service Plan via the arm-appservice SDK

