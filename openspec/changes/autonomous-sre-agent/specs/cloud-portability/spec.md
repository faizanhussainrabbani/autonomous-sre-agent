## ADDED Requirements

### Requirement: Kubernetes Distribution Portability
The system SHALL operate on any CNCF-conformant Kubernetes distribution across AWS (EKS), Azure (AKS), and self-managed clusters, without cloud-provider-specific code in the core agent logic.

#### Scenario: Agent runs on AWS EKS
- **WHEN** the agent is deployed on an AWS EKS cluster
- **THEN** all Kubernetes API interactions SHALL use the standard Kubernetes client API
- **AND** cloud-specific integrations (IAM Roles for Service Accounts, EBS volumes, ALB) SHALL be handled via the cloud provider adapter, not hardcoded

#### Scenario: Agent runs on Azure AKS
- **WHEN** the agent is deployed on an Azure AKS cluster
- **THEN** all Kubernetes API interactions SHALL use the same standard Kubernetes client API
- **AND** cloud-specific integrations (Azure AD Workload Identity, Azure Disks, Azure KeyVault) SHALL be handled via the cloud provider adapter

#### Scenario: Agent runs on self-managed cluster
- **WHEN** the agent is deployed on a self-managed Kubernetes cluster (kubeadm, k3s, Rancher)
- **THEN** the agent SHALL operate without any cloud provider adapter
- **AND** secrets management SHALL fall back to Kubernetes Secrets or a configured Vault instance

### Requirement: Secrets Management Provider Abstraction
The system SHALL access secrets through a provider-agnostic interface, supporting cloud-native and third-party secrets managers.

#### Scenario: Secrets from AWS Secrets Manager
- **WHEN** the cloud provider is configured as "aws"
- **THEN** the system SHALL retrieve secrets (API keys, DB credentials, LLM tokens) via AWS Secrets Manager or AWS SSM Parameter Store
- **AND** credentials SHALL be rotated according to AWS-managed rotation policies

#### Scenario: Secrets from Azure Key Vault
- **WHEN** the cloud provider is configured as "azure"
- **THEN** the system SHALL retrieve secrets via Azure Key Vault
- **AND** authenticate using Azure Managed Identity or Workload Identity Federation

#### Scenario: Secrets from HashiCorp Vault (cloud-agnostic)
- **WHEN** the secrets provider is configured as "vault"
- **THEN** the system SHALL retrieve secrets via HashiCorp Vault API
- **AND** this option SHALL work identically on AWS, Azure, and self-managed clusters

### Requirement: Object Storage Provider Abstraction
The system SHALL store audit logs, incident records, and post-mortem data through a storage-agnostic interface.

#### Scenario: Audit log storage on AWS
- **WHEN** the cloud provider is "aws"
- **THEN** audit logs SHALL be written to Amazon S3 using the configured bucket and prefix
- **AND** encryption SHALL use AWS KMS

#### Scenario: Audit log storage on Azure
- **WHEN** the cloud provider is "azure"
- **THEN** audit logs SHALL be written to Azure Blob Storage using the configured container
- **AND** encryption SHALL use Azure Storage Service Encryption

#### Scenario: Audit log storage on self-managed (MinIO)
- **WHEN** no cloud provider is configured
- **THEN** audit logs SHALL be written to a configured S3-compatible store (MinIO)
- **AND** the agent SHALL use the same S3 API calls (MinIO is S3-compatible)

### Requirement: IAM and Authentication Provider Abstraction
The system SHALL authenticate to cloud services using the cloud-native identity mechanism appropriate to each provider.

#### Scenario: AWS IAM Roles for Service Accounts (IRSA)
- **WHEN** the agent runs on EKS
- **THEN** the agent SHALL authenticate to AWS services using IRSA (IAM Role bound to K8s ServiceAccount)
- **AND** no long-lived AWS credentials SHALL be stored in the agent's configuration

#### Scenario: Azure Workload Identity
- **WHEN** the agent runs on AKS
- **THEN** the agent SHALL authenticate to Azure services using Workload Identity Federation
- **AND** no long-lived Azure credentials SHALL be stored in the agent's configuration

#### Scenario: Self-managed cluster authentication
- **WHEN** the agent runs on a self-managed cluster
- **THEN** the agent SHALL authenticate using Kubernetes-native service accounts
- **AND** external service credentials SHALL be sourced exclusively from the configured secrets manager

### Requirement: Cloud Provider Configuration
The system SHALL allow operators to configure the cloud provider and provider-specific settings via a single configuration block.

#### Scenario: AWS provider configuration
- **WHEN** an operator configures the cloud provider as "aws"
- **THEN** the system SHALL expect: region, EKS cluster name, S3 bucket for audit logs, Secrets Manager prefix, and optional IAM role ARN
- **AND** validate all settings on startup before accepting incidents

#### Scenario: Azure provider configuration
- **WHEN** an operator configures the cloud provider as "azure"
- **THEN** the system SHALL expect: subscription ID, resource group, AKS cluster name, Blob Storage container, Key Vault name, and Managed Identity client ID
- **AND** validate all settings on startup before accepting incidents

#### Scenario: No cloud provider (self-managed)
- **WHEN** the cloud provider is set to "none" or omitted
- **THEN** the system SHALL operate using only Kubernetes-native resources and the configured secrets/storage providers
- **AND** log a warning that cloud-specific features (managed identity, cloud storage encryption) are unavailable
