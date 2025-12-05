# GeuseMaker: AI Infrastructure Platform - Product Requirements Document

**Version**: 2.0 (Fresh Start)
**Status**: Draft
**Last Updated**: 2025-01-18

---

## Executive Summary

GeuseMaker is an AI infrastructure deployment platform that provisions and manages a complete AI application stack on AWS. The system enables users to deploy workflow automation, LLM inference, vector databases, and web scraping services through a simple, guided interface with intelligent cost optimization and resource management.

---

## Problem Statement

Organizations need to rapidly deploy AI infrastructure for development, testing, and production workloads. Current solutions require:
- Deep AWS expertise to configure networking, compute, storage, and security
- Manual resource management and cost optimization
- Complex setup procedures for multi-service AI stacks
- Time-consuming troubleshooting and validation

**Target**: Enable users to deploy a complete, production-ready AI infrastructure stack in under 10 minutes with minimal AWS knowledge.

---

## Goals & Success Metrics

### Primary Goals
1. **Speed**: Deploy complete AI stack in < 10 minutes (median for GPU), < 6 minutes (CPU-only)
2. **Simplicity**: Require zero manual AWS console intervention for 95% of deployments
3. **Cost**: Achieve 50-70% cost savings vs. on-demand AWS pricing (via spot instances)
4. **Reliability**: 95%+ successful deployment rate without manual intervention

### Success Metrics
- **P0 Metrics** (Must Achieve):
  - Deployment time: < 10 minutes median (GPU), < 6 minutes median (CPU), < 15 minutes 95th percentile
  - Success rate: ≥ 95% deployments complete without errors
  - Automation: ≥ 90% of operations callable non-interactively

- **P1 Metrics** (Should Achieve):
  - Cost optimization: 50-70% savings through intelligent resource selection
  - Validation accuracy: ≥ 95% of issues detected before user access
  - Resource reuse: Support existing VPC reuse in < 10 minutes

- **P2 Metrics** (Nice to Have):
  - Concurrent deployments: Support ≥ 3 simultaneous deployments
  - Time to information: Full deployment status available within 30 seconds

---

## Core Requirements

### 1. AI Application Stack

The system must deploy and manage these services:

#### 1.1 Workflow Automation Platform
- **Purpose**: Visual workflow creation and orchestration
- **Requirements**:
  - Web-based UI accessible via HTTP/HTTPS
  - Persistent storage for workflows and execution history
  - Database backend for state management
  - Authentication/authorization for admin access
  - API for programmatic workflow execution
  - Health monitoring endpoints

#### 1.2 LLM Inference Server
- **Purpose**: Local large language model hosting and inference
- **Requirements**:
  - REST API for model management (pull, list, delete models)
  - REST API for inference (generate, chat, embeddings)
  - Support for multiple concurrent models
  - Persistent model storage across restarts
  - GPU acceleration when available
  - CPU fallback when GPU unavailable
  - Health monitoring endpoints

#### 1.3 Vector Database
- **Purpose**: High-performance vector storage and similarity search
- **Requirements**:
  - REST API for collection and point management
  - gRPC interface for high-performance operations
  - Web-based dashboard for administration
  - Persistent storage for collections and points
  - Support for multiple vector collections
  - Health monitoring endpoints

#### 1.4 Web Scraping Service
- **Purpose**: Web content extraction and processing
- **Requirements**:
  - REST API for crawling requests
  - Configurable concurrency limits
  - Configurable timeout settings
  - Integration with LLM for content extraction
  - Health monitoring endpoints

#### 1.5 Supporting Services
- **Database**: PostgreSQL for workflow platform backend
- **Container Runtime**: Docker with optional GPU support (NVIDIA runtime)
- **Service Networking**: Internal service discovery and communication

---

### 2. Deployment Tiers

The system must support multiple deployment configurations:

#### Tier 1: Development (CPU-Based)
- **Use Case**: Development, testing, experimentation without GPU requirements
- **Requirements**:
  - Single compute instance (CPU-only, no GPU)
  - Cost-optimized instance selection (prefer lowest-cost available)
  - Direct public access via public IP
  - Persistent data storage
  - Basic health monitoring
  - Estimated cost: ~$0.01-0.05/hour with spot instances

#### Tier 2: Automation Engineer (Minimal Stack)
- **Use Case**: Pre-production testing, demos, CI/CD pipelines
- **Requirements**:
  - CPU-enabled compute instances with optimized AMI
  - Optimized for workflow automation (n8n + PostgreSQL primary)
  - Minimal services deployment (can exclude Ollama for CPU-only workflows)
  - Estimated cost: ~$0.02-0.10/hour with spot instances

#### Tier 3: GPU-Optimized (AI Workloads)
- **Use Case**: Production LLM inference workloads
- **Requirements**:
  - GPU-enabled compute instances (minimum g4dn.xlarge for 8B parameter models)
  - NVIDIA runtime for Docker GPU support
  - Optimized for LLM inference workloads (Ollama with GPU acceleration)
  - Can be combined with features from other tiers
  - Optional: Load balancer for high availability
  - Optional: Content Delivery Network (CDN) for global access
  - Comprehensive monitoring and alerting
  - Estimated cost: ~$0.15-0.50/hour with spot instances (70% savings vs on-demand)

---

### 3. User Experience

#### 3.1 Interactive Mode
- **Purpose**: Guided deployment for users learning the system
- **Requirements**:
  - Step-by-step prompts for all decisions
  - Resource discovery and selection (VPCs, subnets, security groups, etc.)
  - Cost estimation before deployment
  - Clear explanation of each option
  - Visual feedback (progress indicators, success/error messages)
  - Ability to abort deployment at any step

#### 3.2 Non-Interactive Mode
- **Purpose**: Automation and CI/CD integration
- **Requirements**:
  - Single command deployment with parameters
  - Environment variable configuration
  - Configuration file support (JSON, YAML, or similar)
  - Machine-readable output (JSON, YAML, or structured text)
  - Exit codes for success/failure detection
  - Silent mode (suppress progress, only show errors)

#### 3.3 Informational Display
- **Requirements**:
  - Service endpoints and access URLs
  - Default credentials (if applicable)
  - Estimated hourly cost
  - Health status of all services
  - SSH access information
  - Next steps and recommendations

---

### 4. Resource Discovery & Management

#### 4.1 AWS Resource Discovery
- **Requirements**:
  - Discover existing VPCs in selected region
  - Discover existing subnets within selected VPC
  - Discover existing security groups within selected VPC
  - Discover existing SSH key pairs in selected region (SSH keys are region-scoped, not VPC-scoped)
  - Discover existing load balancers within selected VPC
  - Discover existing CloudFront distributions (CloudFront is a global service, not VPC-scoped)
  - Discover existing EFS in selected region
  - Validate discovered resources for compatibility
  - Cache discovery results to avoid repeated API calls

#### 4.2 Resource Selection
- **Requirements**:
  - Allow user to choose existing resource or create new
  - Show resource details (CIDR blocks, availability zones, tags, etc.)
  - Validate selected resources meet requirements
  - Handle resource dependencies (e.g., subnet must be in selected VPC)
  - Support multi-region resource discovery

#### 4.3 Resource Provenance
- **Requirements**:
  - Track which resources were created vs. reused
  - Record creation timestamps for new resources
  - Store resource relationships (VPC → Subnets → Instances)
  - Enable safe cleanup (only delete created resources, not reused ones)

---

### 5. Cost Optimization

#### 5.1 Instance Selection
- **Requirements**:
  - Analyze current spot instance pricing across availability zones and regions
  - Select lowest-cost spot instances when appropriate
  - Fallback to on-demand instances when spot unavailable
  - Handle spot instance interruption gracefully (2-minute warning notification)
  - Support instance type overrides (user-specified type)
  - Validate instance type supports required features (GPU, network throughput, etc.)
  - Note: Security groups are VPC-scoped; cross-region resource reuse is not possible for security groups

#### 5.2 Cost Estimation
- **Requirements**:
  - Calculate estimated hourly and monthly cost before deployment
  - Display cost breakdown by resource (compute, storage, networking)
  - Show cost comparison between deployment tiers
  - Update cost estimates when configuration changes
  - Track actual costs post-deployment (if possible)

#### 5.3 Cost Tracking
- **Requirements**:
  - Tag all resources with deployment identifier
  - Enable cost allocation by deployment
  - Generate cost reports per deployment
  - Support cost alerting when thresholds exceeded
  - Give budget limit for deployments if estimate exceeds budget, give warning and make user confirm deployment
---

### 6. Deployment Lifecycle

#### 6.1 Deployment Creation
- **Requirements**:
  - Validate prerequisites (AWS credentials, permissions, quotas)
  - Create required AWS resources (VPC, subnets, security groups, instances, etc.)
  - Configure networking (internet access, security rules, routing)
  - Provision compute instances with required software
  - Note: Compute instance type may dictate networking and AWS resource requirements; validate all resources can be launched together as a cohesive solution 
  - Deploy application services with UserData scripts (Docker containers)
  - Validate deployment health
  - Save deployment state and metadata

#### 6.2 Deployment Listing
- **Requirements**:
  - List all active deployments
  - Show deployment status (running, stopped, failed, deploying)
  - Display key metadata (name, tier, region, creation time)
  - Filter by status, region, or tier
  - Sort by name, creation time, or cost

#### 6.3 Deployment Inspection
- **Requirements**:
  - Show detailed deployment information
  - Display all service endpoints and URLs
  - Show resource inventory (instances, volumes, load balancers, etc.)
  - Display current health status
  - Show estimated vs. actual costs
  - Provide SSH access commands

#### 6.4 Deployment Validation
- **Requirements**:
  - Validate all services are running
  - Check health endpoints for all services
  - Verify network connectivity between services
  - Test external access to exposed services
  - Validate persistent storage is mounted
  - Generate validation report with pass/fail status

#### 6.5 Deployment Updates
- **Requirements**:
  - Update service configurations
  - Scale compute resources (instance type, count)
  - Rotate credentials
  - Update container images
  - Apply security patches
  - Preserve data during updates

#### 6.6 Deployment Destruction
- **Requirements**:
  - Confirm destruction (require explicit user confirmation)
  - Delete created resources (instances, volumes, security groups, etc.)
  - Preserve reused resources (don't delete VPC/subnets if reused)
  - Handle resource dependencies (delete in correct order)
  - Detect and clean up orphaned resources
  - Generate destruction report
  - Remove deployment state

---

### 7. State Management

#### 7.1 Deployment State
- **Requirements**:
  - Store deployment metadata (name, tier, region, creation time)
  - Store resource inventory (IDs, ARNs, types)
  - Store configuration (instance types, service ports, credentials)
  - Store provenance (created vs. reused resources)
  - Support state persistence across system restarts
  - Enable state export (JSON, YAML, or similar)

#### 7.2 State Location
- **Requirements**:
  - Store state locally on user's machine
  - Support custom state storage location
  - Enable state sharing across team members (optional)
  - Backup state automatically
  - Restore state from backup

#### 7.3 State Operations
- **Requirements**:
  - Initialize new deployment state
  - Update state during deployment
  - Query state for deployment information
  - Validate state integrity
  - Migrate state between versions
  - Archive old deployment states

---

### 8. Validation & Health Monitoring

#### 8.1 Pre-Deployment Validation
- **Requirements**:
  - Validate AWS credentials and permissions
  - Check AWS service quotas and limits
  - Verify required services available in region
  - Validate configuration parameters
  - Check for naming conflicts
  - Estimate resource requirements

#### 8.2 Deployment Health Checks
- **Requirements**:
  - Check compute instance status
  - Verify service containers are running
  - Test service health endpoints (HTTP GET /health or equivalent)
  - Validate inter-service connectivity
  - Check persistent storage is mounted
  - Verify external access (load balancer, CDN)

#### 8.3 Continuous Monitoring
- **Requirements**:
  - Periodic health checks for all services
  - Alert on service failures
  - Track service uptime and availability
  - Monitor resource utilization (CPU, memory, disk)
  - Detect configuration drift

#### 8.4 Validation Reporting
- **Requirements**:
  - Generate validation report with pass/fail status
  - Show details for each validation check
  - Provide actionable remediation steps for failures
  - Export validation results (JSON, YAML, or similar)

---

### 9. Security & Compliance

#### 9.1 Network Security
- **Requirements**:
  - Isolate services in private network
  - Configure security groups with minimum required access
  - Use HTTPS/TLS for external access
  - Enable VPC flow logs (optional)

#### 9.2 Access Control
- **Requirements**:
  - Use IAM roles for service permissions
  - Apply principle of least privilege
  - Support AWS Organizations and SCPs
  - Audit all access attempts

#### 9.3 Data Protection
- **Requirements**:
  - Encrypt data at rest (volumes, object storage)
  - Encrypt data in transit (TLS/SSL)
  - Secure credential storage (no plaintext passwords)
  - Support customer-managed encryption keys (optional)
  - Enable backup and recovery

#### 9.4 Compliance & Auditing
- **Requirements**:
  - Tag all resources for compliance tracking
  - Enable CloudTrail logging
  - Generate compliance reports
  - Support regulatory requirements (GDPR, HIPAA, etc.) through AWS native services

---

### 10. Error Handling & Recovery

#### 10.1 Error Detection
- **Requirements**:
  - Detect AWS API errors (throttling, quotas, permissions)
  - Detect resource creation failures
  - Detect service deployment failures
  - Detect configuration errors
  - Detect networking issues

#### 10.2 Error Reporting
- **Requirements**:
  - Show clear, actionable error messages
  - Provide error context (what was being done, why it failed)
  - Suggest remediation steps
  - Log errors for debugging
  - Support error codes for programmatic handling

#### 10.3 Failure Recovery
- **Requirements**:
  - Retry transient failures (network errors, throttling)
  - Rollback partial deployments on critical failures
  - Clean up resources on deployment failure
  - Save partial state for manual recovery
  - Support manual intervention when needed

#### 10.4 Rollback Capabilities
- **Requirements**:
  - Rollback to previous deployment configuration
  - Rollback service updates
  - Preserve data during rollback
  - Validate rollback success
  - Support partial rollback (specific services only)

---

## User Personas & Use Cases

### Persona 1: Automation Engineer
**Background**: Experienced developer who wants to automate AI stack provisioning for CI/CD pipelines.

**Goals**:
- Deploy AI stack via single command or API call
- Integrate deployments into automated testing workflows
- Manage multiple deployments programmatically
- Retrieve deployment information via structured output

**Requirements**:
- Non-interactive CLI commands
- Machine-readable output (JSON/YAML)
- API or SDK for programmatic access
- Idempotent operations (safe to re-run)
- Environment variable configuration

**Use Cases**:
1. Deploy staging environment before integration tests
2. Spin up ephemeral test environments
3. Retrieve service endpoints for test configuration
4. Destroy test environments after test completion

---

### Persona 2: Platform SRE
**Background**: Site Reliability Engineer managing production AI infrastructure with focus on reliability and cost.

**Goals**:
- Deploy production-grade AI stacks with high availability
- Monitor deployment health and performance
- Optimize costs across multiple deployments
- Ensure security and compliance
- Manage multiple environments (dev, staging, prod)

**Requirements**:
- Multi-tier deployment options
- Comprehensive monitoring and alerting
- Cost tracking and optimization
- Audit trails and compliance reporting
- Rollback and recovery capabilities

**Use Cases**:
1. Deploy production AI stack with multi-AZ HA
2. Monitor health and performance of all deployments
3. Generate cost reports for budget tracking
4. Perform blue/green deployments with rollback
5. Audit resource configurations for compliance

---

### Persona 3: Data Scientist / Builder
**Background**: Technical user who needs AI infrastructure for experimentation and prototyping.

**Goals**:
- Quickly spin up AI infrastructure without AWS expertise
- Understand cost implications before deploying
- Access services easily for development
- Clean up resources when done

**Requirements**:
- Interactive guided deployment
- Resource discovery and selection
- Clear cost estimates
- Simple service access information
- Easy cleanup

**Use Cases**:
1. Deploy development environment for AI experimentation
2. Select existing VPC to stay within budget
3. Access n8n to create workflows
4. Load models into Ollama for testing
5. Destroy environment when project complete

---

## Non-Functional Requirements

### NFR1: Performance
- **NFR1.1**: Deployment time < 10 minutes median (GPU), < 6 minutes median (CPU) from command execution to services available
- **NFR1.2**: Deployment with existing VPC reuse < 8 minutes (CPU), < 12 minutes (GPU)
- **NFR1.3**: Validation operations complete within 30 seconds
- **NFR1.4**: Support ≥ 3 concurrent deployments without performance degradation
- **NFR1.5**: State operations (list, show, query) complete within 2 seconds

### NFR2: Reliability
- **NFR2.1**: ≥ 95% successful deployment rate without manual intervention
- **NFR2.2**: Automated validation detects ≥ 95% of issues before user access
- **NFR2.3**: All operations are idempotent (safe to re-run)
- **NFR2.4**: Graceful error handling with rollback on critical failures
- **NFR2.5**: Support deployment recovery from partial failures

### NFR3: Usability
- **NFR3.1**: ≥ 90% of operations callable non-interactively (automation-ready)
- **NFR3.2**: Zero manual dependency installation beyond documented prerequisites
- **NFR3.3**: Clear error messages with actionable remediation steps
- **NFR3.4**: Interactive mode suitable for users with basic AWS knowledge
- **NFR3.5**: Consistent UX with emojis, colors, and ASCII art where appropriate

### NFR4: Maintainability
- **NFR4.1**: Modular design enabling easy feature additions
- **NFR4.2**: Comprehensive logging for debugging (debug mode available)
- **NFR4.3**: Versioned configuration and state formats
- **NFR4.4**: Backward compatibility for at least 1 major version
- **NFR4.5**: Self-documenting code and help commands

### NFR5: Scalability
- **NFR5.1**: Support ≥ 50 concurrent deployments per AWS account
- **NFR5.2**: Handle deployments across multiple AWS regions
- **NFR5.3**: Support multiple AWS accounts (via profiles)
- **NFR5.4**: Scale from development (1 instance) to production (multi-AZ)

### NFR6: Security
- **NFR6.1**: No hardcoded credentials or secrets in code
- **NFR6.2**: Follow AWS security best practices (least privilege, encryption)
- **NFR6.3**: Secure credential handling (AWS credential chain, no plaintext)
- **NFR6.4**: Security group rules follow principle of least access
- **NFR6.5**: All resources tagged for security auditing

---

## Integration Requirements

### AWS Services
The system must integrate with these AWS services:

- **Compute**: EC2 (on-demand and spot instances)
- **Networking**: VPC, Subnets, Internet Gateway, Route Tables, NAT Gateway
- **Security**: Security Groups, IAM (roles, policies, instance profiles)
- **Load Balancing**: Application Load Balancer (ALB), Target Groups
- **Content Delivery**: CloudFront
- **Storage**: EBS (block storage), EFS (shared file system)
- **Monitoring**: CloudWatch (metrics, logs, alarms)
- **Cost Management**: Cost Explorer, Cost Allocation Tags

### External Services
- **Container Registry**: Docker Hub or equivalent for service images
- **Service Images**: n8n, Ollama, Qdrant, Crawl4AI, PostgreSQL (official images)

---

## Constraints & Assumptions

### Constraints
- Must work with standard AWS account permissions (no organization admin required)
- Must operate within AWS service quotas and limits
- Must support AWS regions where all required services are available
- Must handle AWS API rate limits gracefully
- Must use latest stable versions of all tools and dependencies
- Internet connectivity required for AWS API access and service image downloads

### Assumptions
- Users have AWS account with EC2, VPC, and IAM permissions
- Users have AWS CLI configured or equivalent credentials available
- Users have basic understanding of AWS concepts (VPC, EC2, security groups)
- Service container images are publicly accessible (Docker Hub, etc.)
- Users accept AWS costs for deployed resources
- Users are responsible for securing service credentials post-deployment

---

## Out of Scope

The following are explicitly **OUT OF SCOPE** for this version:

1. **Workflow Content Management**: System deploys n8n but does not create or manage workflows
2. **Model Management**: System deploys Ollama but users pull models manually
3. **Multi-Cloud Support**: AWS only (no Azure, GCP, on-premises)
4. **Custom Container Builds**: Uses official public images only
5. **Advanced Monitoring**: Basic health checks only (no custom dashboards, alerting beyond AWS native)
6. **Backup Automation**: Users responsible for backup strategies
7. **Service Configuration**: Uses default service configurations (users customize post-deployment)
8. **Auto-Scaling Policies**: Manual scaling or simple auto-scaling (no complex predictive scaling)
9. **Multi-Tenancy**: Single tenant per deployment
10. **Service Mesh**: No service mesh integration (Istio, App Mesh, etc.)

---

## Acceptance Criteria

A successful implementation must demonstrate:

1. ✅ **Deployment**: Deploy all 4 AI services (n8n, Ollama, Qdrant, Crawl4AI) + PostgreSQL in functional state
2. ✅ **Tiers**: Support minimum 3 deployment tiers (development, staging, production)
3. ✅ **Interfaces**: Provide both interactive and non-interactive interfaces
4. ✅ **Discovery**: Discover and optionally reuse existing AWS resources (VPCs, subnets, etc.)
5. ✅ **Validation**: Validate deployments and report health status for all services
6. ✅ **State**: Track deployment state and enable listing, inspection, and cleanup
7. ✅ **Cost**: Provide cost estimates and achieve 50-70% savings through optimization
8. ✅ **Speed**: Complete deployments in < 10 minutes (GPU) / < 6 minutes (CPU) median for new infrastructure
9. ✅ **Reliability**: Achieve ≥ 95% success rate without manual intervention
10. ✅ **Automation**: Support non-interactive usage for ≥ 90% of operations

### Verification Methods
- **Automated Testing**: Unit tests, integration tests, end-to-end deployment tests
- **User Testing**: Beta testing with each persona (3-5 users per persona)
- **Performance Testing**: Measure deployment times, concurrent deployments
- **Cost Validation**: Compare costs with baseline deployments
- **Documentation Review**: Verify documentation completeness and accuracy

---

## Appendix A: Service Specifications

### n8n (Workflow Automation)
- **Image**: `n8nio/n8n:latest`
- **Port**: 5678 (HTTP)
- **Database**: PostgreSQL
- **Health Endpoint**: `/healthz`
- **Volume**: Persistent storage for workflow data

### Ollama (LLM Inference)
- **Image**: `ollama/ollama:latest`
- **Port**: 11434 (HTTP)
- **API Endpoints**: `/api/generate`, `/api/chat`, `/api/tags`, `/api/pull`
- **Health Endpoint**: `/api/tags`
- **Volume**: Persistent storage for models

### Qdrant (Vector Database)
- **Image**: `qdrant/qdrant:latest`
- **Ports**: 6333 (HTTP), 6334 (gRPC)
- **API**: REST and gRPC
- **Health Endpoint**: `/health`
- **Volume**: Persistent storage for collections

### Crawl4AI (Web Scraping)
- **Image**: `unclecode/crawl4ai:latest`
- **Port**: 8000 (HTTP)
- **Health Endpoint**: `/health`
- **Volume**: Persistent storage for crawl data

### PostgreSQL (Database)
- **Image**: `postgres:16-alpine`
- **Port**: 5432 (internal only)
- **Health**: `pg_isready` command
- **Volume**: Persistent storage for database

---

## Appendix B: Deployment Flow

This describes the **WHAT** happens during deployment (not the implementation):

1. **Pre-Validation**:
   - Validate AWS credentials
   - Check service quotas
   - Verify region availability
   - Validate configuration

2. **Resource Planning**:
   - Discover existing resources (if reuse enabled)
   - Determine resources to create
   - Calculate cost estimate
   - Display plan to user
   - Obtain confirmation (in interactive mode)

3. **Infrastructure Provisioning**:
   - Create/select VPC
   - Create/select subnets
   - Create/select security groups
   - Create compute instances
   - Attach storage
   - Attach persistant storage
   - Configure networking

4. **Service Deployment**:
   - Install container runtime on instances
   - Deploy service containers
   - Configure service networking
   - Mount persistent storage

5. **Post-Deployment**:
   - Validate service health
   - Test connectivity
   - Save deployment state
   - Display service endpoints
   - Show access information

---

## Appendix C: Cost Estimation Model

Cost estimation must include these components:

1. **Compute Costs**:
   - EC2 instance hourly cost (spot or on-demand)
   - Number of instances × hourly rate
   - Consider spot interruption rates

2. **Storage Costs**:
   - EBS volume costs (GB × hourly rate)
   - EFS costs (GB × hourly rate) if applicable
   - Snapshot costs if backup enabled

3. **Network Costs**:
   - Data transfer out (estimated based on tier)
   - NAT Gateway hourly costs
   - Load Balancer hourly costs (if applicable)

4. **Additional Services**:
   - CloudFront costs (if CDN enabled)
   - CloudWatch costs (metrics, logs)

**Display Format**:
- Show hourly cost estimate
- Show daily cost estimate (24 hours)
- Show monthly cost estimate (730 hours)
- Break down by component
- Compare spot vs. on-demand savings

---

## Document Change Log

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 2.0 | 2025-01-18 | AI Assistant | Fresh start - functional requirements only, no implementation details |
| 1.0 | 2024-XX-XX | Original | Initial PRD with implementation details (now deprecated) |

---

**END OF DOCUMENT**

This PRD describes the functional requirements for GeuseMaker. Implementation teams should design solutions that meet these requirements using appropriate tools, technologies, and AWS services. The goal is to build a system that delivers the described functionality with excellent user experience, reliability, and cost optimization.
