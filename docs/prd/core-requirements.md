# Core Requirements

## 1. AI Application Stack

The system must deploy and manage these services:

### 1.1 Workflow Automation Platform
- **Purpose**: Visual workflow creation and orchestration
- **Requirements**:
  - Web-based UI accessible via HTTP/HTTPS
  - Persistent storage for workflows and execution history
  - Database backend for state management
  - Authentication/authorization for admin access
  - API for programmatic workflow execution
  - Health monitoring endpoints

### 1.2 LLM Inference Server
- **Purpose**: Local large language model hosting and inference
- **Requirements**:
  - REST API for model management (pull, list, delete models)
  - REST API for inference (generate, chat, embeddings)
  - Support for multiple concurrent models
  - Persistent model storage across restarts
  - GPU acceleration when available
  - CPU fallback when GPU unavailable
  - Health monitoring endpoints

### 1.3 Vector Database
- **Purpose**: High-performance vector storage and similarity search
- **Requirements**:
  - REST API for collection and point management
  - gRPC interface for high-performance operations
  - Web-based dashboard for administration
  - Persistent storage for collections and points
  - Support for multiple vector collections
  - Health monitoring endpoints

### 1.4 Web Scraping Service
- **Purpose**: Web content extraction and processing
- **Requirements**:
  - REST API for crawling requests
  - Configurable concurrency limits
  - Configurable timeout settings
  - Integration with LLM for content extraction
  - Health monitoring endpoints

### 1.5 Supporting Services
- **Database**: PostgreSQL for workflow platform backend
- **Container Runtime**: Docker with optional GPU support (NVIDIA runtime)
- **Service Networking**: Internal service discovery and communication

---

## 2. Deployment Topologies and Workloads

Topology and workload are separate decisions. The legacy tier keys remain stable for
configuration compatibility, but they define network and edge shape rather than CPU/GPU eligibility.

### Tier 1: Development (`dev`)
- **Use Case**: Development, testing, and low-complexity deployments
- **Requirements**:
  - Single compute instance
  - Direct public access via public IP
  - Optional self-signed HTTPS through NGINX
  - Persistent data storage
  - Basic health monitoring

### Tier 2: Production (`automation`)
- **Use Case**: Production automation and applications requiring a managed ingress
- **Requirements**:
  - Application Load Balancer
  - ACM HTTPS certificate and redirect support
  - Route 53 DNS validation when certificates are provisioned interactively
  - CPU or GPU workload support

### Tier 3: Global (`gpu`, legacy key)
- **Use Case**: Globally distributed applications requiring an edge CDN
- **Requirements**:
  - Tier 2 ALB and HTTPS capabilities
  - CloudFront distribution
  - CPU or GPU workload support

### Workload and recommendation policy

- `workload=cpu` selects CPU candidates.
- `workload=gpu` selects GPU candidates and compatible runtime behavior.
- Older configurations that omit `workload` infer GPU only for the legacy `gpu` tier.
- Recommendation policies are `balanced`, `lowest_cost`, `highest_availability`, and `performance`.
- The selector evaluates eligible candidates and returns ranked alternatives before deployment.

---

## 3. User Experience

### 3.1 Interactive Mode
- **Purpose**: Guided deployment for users learning the system
- **Requirements**:
  - Quick setup with derived defaults and advanced setup with full control
  - Step-by-step prompts for decisions appropriate to the selected mode
  - Resource discovery and selection (VPCs, subnets, security groups, etc.)
  - Cost estimation before deployment
  - Clear explanation of each option
  - Visual feedback (progress indicators, success/error messages)
  - Ability to abort deployment at any step
  - Back navigation and resumable local sessions
  - Optional full-screen TUI installed through the `[tui]` extra

### 3.2 Non-Interactive Mode
- **Purpose**: Automation and CI/CD integration
- **Requirements**:
  - Single command deployment with parameters
  - Environment variable configuration
  - Configuration file support (JSON, YAML, or similar)
  - Machine-readable output (JSON, YAML, or structured text)
  - Exit codes for success/failure detection
  - Silent mode (suppress progress, only show errors)

### 3.3 Informational Display
- **Requirements**:
  - Service endpoints and access URLs
  - Default credentials (if applicable)
  - Estimated hourly cost
  - Health status of all services
  - SSH access information
  - Next steps and recommendations

---

## 4. Resource Discovery & Management

### 4.1 AWS Resource Discovery
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

### 4.2 Resource Selection
- **Requirements**:
  - Allow user to choose existing resource or create new
  - Show resource details (CIDR blocks, availability zones, tags, etc.)
  - Validate selected resources meet requirements
  - Handle resource dependencies (e.g., subnet must be in selected VPC)
  - Support multi-region resource discovery

### 4.3 Resource Provenance
- **Requirements**:
  - Track which resources were created vs. reused
  - Record creation timestamps for new resources
  - Store resource relationships (VPC → Subnets → Instances)
  - Enable safe cleanup (only delete created resources, not reused ones)

---

## 5. Cost Optimization

### 5.1 Instance Selection
- **Requirements**:
  - Analyze current spot instance pricing across availability zones and regions
  - Select lowest-cost spot instances when appropriate
  - Fallback to on-demand instances when spot unavailable
  - Handle spot instance interruption gracefully (2-minute warning notification)
  - Support instance type overrides (user-specified type)
  - Validate instance type supports required features (GPU, network throughput, etc.)
  - Note: Security groups are VPC-scoped; cross-region resource reuse is not possible for security groups

### 5.2 Cost Estimation
- **Requirements**:
  - Calculate estimated hourly and monthly cost before deployment
  - Display cost breakdown by resource (compute, storage, networking)
  - Show cost comparison between deployment tiers
  - Update cost estimates when configuration changes
  - Track actual costs post-deployment (if possible)

### 5.3 Cost Tracking
- **Requirements**:
  - Tag all resources with deployment identifier
  - Enable cost allocation by deployment
  - Generate cost reports per deployment
  - Support cost alerting when thresholds exceeded
  - Give budget limit for deployments if estimate exceeds budget, give warning and make user confirm deployment
---

## 6. Deployment Lifecycle

### 6.1 Deployment Creation
- **Requirements**:
  - Validate prerequisites (AWS credentials, permissions, quotas)
  - Create required AWS resources (VPC, subnets, security groups, instances, etc.)
  - Configure networking (internet access, security rules, routing)
  - Provision compute instances with required software
  - Note: Compute instance type may dictate networking and AWS resource requirements; validate all resources can be launched together as a cohesive solution 
  - Deploy application services with UserData scripts (Docker containers)
  - Validate deployment health
  - Save deployment state and metadata

### 6.2 Deployment Listing
- **Requirements**:
  - List all active deployments
  - Show deployment status (running, stopped, failed, deploying)
  - Display key metadata (name, tier, region, creation time)
  - Filter by status, region, or tier
  - Sort by name, creation time, or cost

### 6.3 Deployment Inspection
- **Requirements**:
  - Show detailed deployment information
  - Display all service endpoints and URLs
  - Show resource inventory (instances, volumes, load balancers, etc.)
  - Display current health status
  - Show estimated vs. actual costs
  - Provide SSH access commands

### 6.4 Deployment Validation
- **Requirements**:
  - Validate all services are running
  - Check health endpoints for all services
  - Verify network connectivity between services
  - Test external access to exposed services
  - Validate persistent storage is mounted
  - Generate validation report with pass/fail status

### 6.5 Deployment Updates
- **Requirements**:
  - Update service configurations
  - Scale compute resources (instance type, count)
  - Rotate credentials
  - Update container images
  - Apply security patches
  - Preserve data during updates

### 6.6 Deployment Destruction
- **Requirements**:
  - Confirm destruction (require explicit user confirmation)
  - Delete created resources (instances, volumes, security groups, etc.)
  - Preserve reused resources (don't delete VPC/subnets if reused)
  - Handle resource dependencies (delete in correct order)
  - Detect and clean up orphaned resources
  - Generate destruction report
  - Remove deployment state

---

## 7. State Management

### 7.1 Deployment State
- **Requirements**:
  - Store deployment metadata (name, tier, region, creation time)
  - Store resource inventory (IDs, ARNs, types)
  - Store configuration (instance types, service ports, credentials)
  - Store provenance (created vs. reused resources)
  - Support state persistence across system restarts
  - Enable state export (JSON, YAML, or similar)

### 7.2 State Location
- **Requirements**:
  - Store state locally on user's machine
  - Support custom state storage location
  - Enable state sharing across team members (optional)
  - Backup state automatically
  - Restore state from backup

### 7.3 State Operations
- **Requirements**:
  - Initialize new deployment state
  - Update state during deployment
  - Query state for deployment information
  - Validate state integrity
  - Migrate state between versions
  - Archive old deployment states

---

## 8. Validation & Health Monitoring

### 8.1 Pre-Deployment Validation
- **Requirements**:
  - Validate AWS credentials and permissions
  - Check AWS service quotas and limits
  - Verify required services available in region
  - Validate configuration parameters
  - Check for naming conflicts
  - Estimate resource requirements

### 8.2 Deployment Health Checks
- **Requirements**:
  - Check compute instance status
  - Verify service containers are running
  - Test service health endpoints (HTTP GET /health or equivalent)
  - Validate inter-service connectivity
  - Check persistent storage is mounted
  - Verify external access (load balancer, CDN)

### 8.3 Continuous Monitoring
- **Requirements**:
  - Periodic health checks for all services
  - Alert on service failures
  - Track service uptime and availability
  - Monitor resource utilization (CPU, memory, disk)
  - Detect configuration drift

### 8.4 Validation Reporting
- **Requirements**:
  - Generate validation report with pass/fail status
  - Show details for each validation check
  - Provide actionable remediation steps for failures
  - Export validation results (JSON, YAML, or similar)

---

## 9. Security & Compliance

### 9.1 Network Security
- **Requirements**:
  - Isolate services in private network
  - Configure security groups with minimum required access
  - Use HTTPS/TLS for external access
  - Enable VPC flow logs (optional)

### 9.2 Access Control
- **Requirements**:
  - Use IAM roles for service permissions
  - Apply principle of least privilege
  - Support AWS Organizations and SCPs
  - Audit all access attempts

### 9.3 Data Protection
- **Requirements**:
  - Encrypt data at rest (volumes, object storage)
  - Encrypt data in transit (TLS/SSL)
  - Secure credential storage (no plaintext passwords)
  - Support customer-managed encryption keys (optional)
  - Enable backup and recovery

### 9.4 Compliance & Auditing
- **Requirements**:
  - Tag all resources for compliance tracking
  - Enable CloudTrail logging
  - Generate compliance reports
  - Support regulatory requirements (GDPR, HIPAA, etc.) through AWS native services

---

## 10. Error Handling & Recovery

### 10.1 Error Detection
- **Requirements**:
  - Detect AWS API errors (throttling, quotas, permissions)
  - Detect resource creation failures
  - Detect service deployment failures
  - Detect configuration errors
  - Detect networking issues

### 10.2 Error Reporting
- **Requirements**:
  - Show clear, actionable error messages
  - Provide error context (what was being done, why it failed)
  - Suggest remediation steps
  - Log errors for debugging
  - Support error codes for programmatic handling

### 10.3 Failure Recovery
- **Requirements**:
  - Retry transient failures (network errors, throttling)
  - Rollback partial deployments on critical failures
  - Clean up resources on deployment failure
  - Save partial state for manual recovery
  - Support manual intervention when needed

### 10.4 Rollback Capabilities
- **Requirements**:
  - Rollback to previous deployment configuration
  - Rollback service updates
  - Preserve data during rollback
  - Validate rollback success
  - Support partial rollback (specific services only)

---
