# GeuseMaker Epics and Stories Summary

> **Delivery record.** Status counts reflect the story documents and may lag code that
> was implemented outside the original epic sequence. Current behavior is documented in
> [the documentation index](README.md), CLI help, and the canonical architecture.

**Generated:** 2025-11-21
**Last Updated:** 2025-12-21
**Codebase Review Date:** 2025-12-08
**Status Snapshot:** 14 epics / 59 stories — Draft: 1 epic, 15 stories; In Progress: 2 epics, 0 stories; Ready: 1 epic, 0 stories; Done: 10 epics, 44 stories

**✅ RECENT COMPLETIONS (2025-12-08):**
- **Epic 12 Complete:** Tier 2 ALB orchestration fully implemented
  - Tier2Orchestrator: 256 LOC with comprehensive error handling and rollback
  - ALB cleanup added to DestructionService
  - 5 new unit tests, all 212 tests passing
- **Next:** Tier 3 GPU/CloudFront orchestration (Epic 13)

**📋 NEWLY DESIGNED (2025-12-21):**
- **Epic 14:** ComfyUI Integration for LTX-2 Video Generation
  - Designed integration for ComfyUI service with LTX-2 custom nodes
  - Requires GPU tier deployments (Epic 13)
  - 4 stories covering service integration, health checks, LTX-2 setup, and NGINX proxy

**✅ Codebase Health:** Grade **A**
- 100% test pass rate (212 tests, +5 from Tier2Orchestrator)
- 0 type errors, 0 lint errors
- 14,642 production LOC (+512), 6,082 test LOC (+437)
- Test coverage: 41.6% (was 39.9%)
- See detailed analysis: [docs/CODEBASE_REVIEW.md](CODEBASE_REVIEW.md)

**✅ Recent Completions (2025-12-08):**
- **Epic 12 Complete:** Tier2Orchestrator with ALB support
  - New: `geusemaker/orchestration/tier2.py` (256 LOC)
  - Updated: `geusemaker/services/destruction/service.py` (ALB cleanup)
  - Tests: `tests/unit/test_orchestration/test_tier2.py` (437 LOC, 5 tests)
- ALB Service expanded: 42 → 274 LOC with 5 new methods

**Note:** Story statuses are taken from the individual story files. Epics 1–9 are complete. Epics 11–13 are partially complete (services implemented, orchestrators pending). Epic 14 (ComfyUI/LTX-2) is newly designed and pending implementation.

**Terminology Clarification:** `RollbackService` handles versioned state rollbacks, while orchestrator cleanup (`Tier1Orchestrator._cleanup_partial_deployment`) deletes partial resources after failures. Use the former for restoring prior configs; rely on the latter for failure cleanup.

---

## Epic 1: Project Foundation and Core Infrastructure
**Status:** Done (stories Draft: 0, In Progress: 0, Done: 1)  
**Goal:** Establish the Python project skeleton, CLI entry point, core models, AWS client factory, and state management baseline.  
**Stories:**
- **1.1** ✅ Project Foundation and Core Infrastructure Setup — Project structure, CLI branding, core Pydantic models, AWS client factory, state manager, lint/test scaffolding.  
**Dependencies:** None; unlocks all other epics.

---

## Epic 2: AWS Resource Discovery & Management
**Status:** Done (stories Draft: 0, In Progress: 0, Done: 4)  
**Goal:** Discover, validate, and reuse existing VPC, subnet, security group, key pair, EFS, load balancer, and CloudFront resources.  
**Stories:**
- **2.1** VPC and Subnet Discovery Service — Discover and validate VPCs/subnets with AZ/route checks and caching.
- **2.2** Security Group and Key Pair Discovery — Enumerate security groups and key pairs; surface details and compatibility checks.
- **2.3** EFS and Load Balancer Discovery — Discover EFS, load balancers, and CloudFront distributions with compatibility validation.
- **2.4** Resource Selection UI and Validation — Interactive selection tables with dependency validation and provenance tracking.  
**Dependencies:** Requires Epic 1; feeds Epic 4 and Epic 8.

---

## Epic 3: Cost Optimization
**Status:** Done (stories Draft: 0, In Progress: 0, Done: 4)  
**Goal:** Provide spot-aware pricing, cost estimation, and ongoing cost tracking to reach 50–70% savings.  
**Stories:**
- **3.1** ✅ AWS Pricing Service — Query and cache spot/on-demand pricing across regions.
- **3.2** ✅ Spot Instance Selection Logic — Choose lowest-cost spot options with fallbacks and interruption handling.
- **3.3** ✅ Cost Estimation Engine — Compute hourly/monthly estimates and spot vs on-demand comparisons.
- **3.4** ✅ Cost Tracking and Budget Alerts — Tag resources, track actuals, report costs, and warn on budget thresholds.  
**Dependencies:** Requires Epic 1; prerequisite for Epic 4 and informs Epic 8.

---

## Epic 4: Deployment Lifecycle - Core Operations
**Status:** Done (stories Draft: 0, In Progress: 0, Done: 10)  
**Goal:** Deliver end-to-end deployment creation, listing, and inspection with resource provisioning and state persistence.  
**Stories:**
- **4.1** ✅ VPC Service Implementation — Create/validate VPCs, subnets, IGW, and route tables with discovery support.
- **4.2** ✅ EFS Service Implementation — Create EFS file systems and mount targets; wait for readiness and validate access.
- **4.3** ✅ Security Group Service Implementation — Build tier-aware security groups with ingress/egress rules and validation.
- **4.4** ✅ EC2 Service Implementation — Launch spot/on-demand instances with UserData and readiness checks.
- **4.5** ✅ UserData Script Generation — Generate EFS mounts, Docker Compose startup, environment configuration, and tier variants.
- **4.6** ✅ Deployment Orchestrator - Tier 1 (Dev) — Coordinate resource workflow, save state, and show Rich progress.
- **4.7** ✅ Deployment Listing Command — List deployments with filters and sorting.
- **4.8** ✅ Deployment Inspection Command — Show endpoints, inventory, health, and costs for a deployment.
- **4.9** ✅ UserData Log Display After Deployment — Automatically fetch and display UserData initialization logs in CLI after deployment using SSM.
- **4.10** ✅ Deep Learning AMI Support — Configurable AWS Deep Learning AMI selection with OS (Ubuntu/Amazon Linux), architecture (x86_64/ARM64), and AMI type (Base/PyTorch/TensorFlow/Multi-Framework) options.  
**Dependencies:** Requires Epics 1, 2, and 3; prerequisite for 5, 6, 8, 9, 10, 11, 12.

---

## Epic 5: Deployment Validation & Health Monitoring
**Status:** Done (stories Draft: 0, In Progress: 0, Done: 5)  
**Goal:** Validate deployments pre/post creation and provide ongoing health monitoring and reporting.  
**Stories:**
- **5.1** ✅ Pre-Deployment Validation — Credential, quota, region, and configuration validation with conflict checks.
- **5.2** ✅ Health Service Implementation — Shared health check client covering n8n, Ollama, Qdrant, Crawl4AI, PostgreSQL.
- **5.3** ✅ Post-Deployment Health Validation — Verify instances, containers, health endpoints, connectivity, and storage mounts.
- **5.4** ✅ Validation Reporting — Generate pass/fail reports with remediation guidance and export formats.
- **5.5** ✅ Continuous Health Monitoring — Periodic checks, alerts, uptime tracking, and utilization monitoring.  
**Dependencies:** Requires Epic 4; supports Epic 9.

---

## Epic 6: Deployment Updates & Destruction
**Status:** Done (stories Draft: 1, In Progress: 0, Done: 4)  
**Goal:** Update, rollback, and destroy deployments safely while preserving reused resources.  
**Stories:**
- **6.1** ✅ Deployment Update Command — Apply configuration changes, scale resources, update images with data preservation.
- **6.2** ✅ Deployment Rollback Implementation — Revert to prior configurations and validate rollback success.
- **6.3** ✅ Deployment Destruction Command — Confirm and tear down created resources in order, preserving reused assets.
- **6.4** ✅ Resource Cleanup and Orphan Detection — Detect and remove orphaned resources; clean state.
- **6.5** 📋 Credential Rotation and Security Patches — Rotate credentials, apply security patches, and update AMIs (Draft).  
**Dependencies:** Requires Epic 4.

---

## Epic 7: State Management
**Status:** Done (stories Draft: 0, In Progress: 0, Done: 3)  
**Goal:** Persist, validate, migrate, and back up deployment state under `~/.geusemaker`.  
**Stories:**
- **7.1** ✅ Enhanced State Manager — State persistence, querying/filtering, exports, and integrity checks.
- **7.2** ✅ State Migration and Versioning — Track versions, handle migrations, and validate schemas.
- **7.3** ✅ State Backup and Restore — Automatic/manual backups with restore and management commands.  
**Dependencies:** Requires Epic 1.

---

## Epic 8: User Experience - Interactive Mode
**Status:** Done (stories Draft: 0, In Progress: 0, Done: 3)  
**Goal:** Provide guided, step-by-step interactive deployments with discovery results, costs, and visual feedback.  
**Stories:**
- **8.1** ✅ Interactive Deployment Flow — Prompted workflow for all decisions with discovery and cost previews.
- **8.2** ✅ Rich UI Components for Interactive Mode — Progress, success/error displays, selection tables, cost breakdowns, abort handling.
- **8.3** ✅ Interactive Mode Integration — Wire interactive flow into the orchestrator with resume/abort handling.  
**Dependencies:** Requires Epics 2, 3, and 4.

---

## Epic 9: User Experience - Non-Interactive Mode
**Status:** Done (stories Draft: 0, In Progress: 0, Done: 5)  
**Goal:** Enable automation-friendly deployments via CLI args/env/config files with machine-readable output.  
**Stories:**
- **9.1** ✅ Configuration File Support — Parse/validate JSON and YAML configs and merge with CLI args.
- **9.2** ✅ Environment Variable Configuration — Environment variable overrides with clear precedence rules.
- **9.3** ✅ Machine-Readable Output — JSON/YAML/structured text output plus exit codes.
- **9.4** ✅ Silent Mode and Error-Only Output — Suppress progress output while surfacing errors and warnings.
- **9.5** ✅ Informational Display Command — Surface endpoints, credentials, estimated cost, health, SSH info, next steps.  
**Dependencies:** Requires Epics 4 and 5.

---

## Epic 10: Security & Compliance
**Status:** Ready (stories Draft: 4, In Progress: 0, Done: 0)  
**Goal:** Enforce network security, least-privilege access, encryption, and compliance tagging/auditing.  
**Stories:**
- **10.1** Enhanced Network Security — Private networking, security group hardening, TLS/HTTPS, optional VPC flow logs.
- **10.2** IAM Roles and Access Control — Role-based permissions, least privilege, org/SCP awareness, access auditing.
- **10.3** Data Protection — Encrypt at rest/in transit, secure credential storage (AWS Secrets Manager/Parameter Store), optional customer-managed keys.
- **10.4** Compliance and Auditing — Resource tagging, CloudTrail, compliance reporting for regulatory needs.  
**Dependencies:** Requires Epic 4.

---

## Epic 11: Error Handling & Recovery
**Status:** In Progress (stories Draft: 3, In Progress: 0, Done: 1)  
**Goal:** Detect, classify, and report errors with retries and rollback for reliable deployments.  
**Stories:**
- **11.1** 📋 Error Detection and Classification — Identify AWS API, resource, deployment, configuration, and networking failures (Draft).
- **11.2** 📋 Error Reporting and User Guidance — Actionable messages with context, remediation steps, and logging (Draft).
- **11.3** 📋 Retry Logic and Transient Failure Handling — Exponential backoff and limits for transient issues (Draft).
- **11.4** ✅ Failure Recovery and Rollback — Roll back partial deployments, clean up resources, and persist partial state. **IMPLEMENTED** - Tier1Orchestrator has comprehensive error handling and rollback.  
**Dependencies:** Requires Epic 4.

---

## Epic 12: Tier 2 Deployment Orchestrator (Automation/ALB)
**Status:** Done (stories Draft: 0, In Progress: 0, Done: 3)
**Goal:** Add ALB-backed Tier 2 deployments with high-availability routing and health checks.
**Stories:**
- **12.1** ✅ ALB Service Implementation — Create ALB, target groups, listeners, and health checks. **IMPLEMENTED** - ALB service complete (274 LOC).
- **12.2** ✅ ALB Orchestrator Implementation — Tier2Orchestrator with conditional ALB creation, health checks, and rollback. **IMPLEMENTED** - 256 LOC, 5 new tests, 212 total passing.
- **12.3** ✅ ALB Integration with Deployment State — ALB fields pre-existing in state model, destruction logic added. **IMPLEMENTED** - DestructionService updated.
**Dependencies:** Requires Epic 4; prerequisite for Epic 13.

---

## Epic 13: Tier 3 Deployment Orchestrator (GPU/CloudFront)
**Status:** In Progress (stories Draft: 3, In Progress: 0, Done: 1)  
**Goal:** Deliver GPU-capable deployments with CloudFront CDN fronting ALB for global delivery.  
**Stories:**
- **13.1** ✅ CloudFront Service Implementation — Create distribution, origins/behaviors, and TLS certificates. **IMPLEMENTED** - CloudFront service complete (346 LOC).
- **13.2** 📋 GPU Instance Support — Validate GPU instance types, NVIDIA runtime/UserData, and AMI selection (Draft).
- **13.3** 📋 CloudFront Orchestrator Implementation — Extend orchestration for CloudFront creation and activation (Draft).
- **13.4** 📋 CloudFront Integration with Deployment State — Persist CloudFront identifiers, expose in inspection, include in costs and destruction (Draft).  
**Dependencies:** Requires Epic 12.

---

## Epic 14: ComfyUI Integration for LTX-2 Video Generation
**Status:** Draft (stories Draft: 4, In Progress: 0, Done: 0)  
**Goal:** Integrate ComfyUI service with LTX-2 custom nodes for video generation workflows in GPU deployments.  
**Stories:**
- **14.1** 📋 ComfyUI Service Integration — Add ComfyUI container to Docker Compose, configure EFS volumes for models/outputs, add port configuration to UserDataConfig, update services template for ComfyUI deployment (Draft).
- **14.2** 📋 ComfyUI Health Checks and Monitoring — Add ComfyUI health check function, integrate into health service, update default health check configs, add to status command output (Draft).
- **14.3** 📋 LTX-2 Custom Nodes Setup — Create ComfyUI setup script template, install ComfyUI Manager, install LTX-2 node pack, configure for GPU tier deployments only, add to UserData generation pipeline (Draft).
- **14.4** 📋 NGINX Proxy Configuration for ComfyUI — Add ComfyUI reverse proxy location block, configure WebSocket support for real-time updates, set extended timeouts for video generation (30 min), increase client body size for model uploads (10G) (Draft).  
**Dependencies:** Requires Epic 4 (Deployment Lifecycle) and Epic 13 (GPU Support). ComfyUI/LTX-2 requires GPU instances for video generation workloads.

---

## File Locations

- Epic files: `docs/epics/epic-{number}-{name}.md`
- Story files: `docs/stories/{epic}.{story}.{name}.md`

## Next Steps (Prioritized Roadmap)

### 🚨 IMMEDIATE (Week 1-2) - Production Readiness

**Priority 1: Refactor Tier1Orchestrator** (1 day)
- **Issue**: `deploy()` method is 232 lines (too complex)
- **Tasks**:
  - Extract helper methods: `_setup_networking()`, `_create_storage()`, `_launch_instance()`
  - Reduce function complexity from 232 → 40-50 LOC per method
  - Improve readability and maintainability
- **Deliverable**: Cleaner, more maintainable orchestration logic

### 📋 SHORT-TERM (Week 3-4) - Feature Completion

**Priority 3: Story 4.10 - Deep Learning AMI Support** ✅ **COMPLETED**
- **Status**: Done - Full implementation verified
- **Completed Tasks**:
  - ✅ Added AMI type selection: Base, PyTorch, TensorFlow, Multi-Framework
  - ✅ Updated EC2Service with `get_latest_dlami()` method
  - ✅ Added OS selection: Amazon Linux 2023, Ubuntu 22.04/24.04, Amazon Linux 2
  - ✅ Added architecture selection: x86_64, ARM64
  - ✅ Updated DeploymentConfig model with os_type, architecture, ami_type fields
  - ✅ Integrated into Tier1Orchestrator
- **Deliverable**: ✅ Support for AWS Deep Learning AMIs

**Priority 4: Expand ALB Service** ✅ **COMPLETED** (2025-12-08)
- **Status**: 274 LOC with full ALB lifecycle management
- **Completed Tasks**:
  - ✅ Added `create_target_group()` with health check config
  - ✅ Added `create_listener()` for HTTP/HTTPS routing
  - ✅ Added `register_targets()` for EC2 instance registration
  - ✅ Implemented `wait_for_healthy()` polling pattern
  - ✅ Added `describe_target_health()` for monitoring
  - ✅ Fixed AWS Tags parameter validation (conditional kwargs pattern)
  - ✅ Created comprehensive test suite (9 tests, 100% pass rate)
- **Deliverable**: ✅ Full ALB management ready for Tier 2 orchestrator

**Priority 5: CloudFront Service** ✅ **COMPLETED** (2025-12-08)
- **Status**: 346 LOC with full CloudFront lifecycle management
- **Completed Tasks**:
  - ✅ Added `create_distribution_with_alb_origin()` for ALB integration
  - ✅ Added `build_cache_behavior()` for path-specific caching
  - ✅ Implemented `wait_for_deployed()` polling pattern (15-30 min)
  - ✅ Added `create_invalidation()` for cache clearing
  - ✅ Added TLS certificate integration (ACM) support
  - ✅ Added `get_distribution()`, `delete_distribution()`, `disable_distribution()`
- **Deliverable**: ✅ Full CloudFront management ready for Tier 3 orchestrator

### 🏗️ MEDIUM-TERM (Month 2-3) - Tier 2 & 3 Deployment

**Priority 6: Epic 12 - Tier 2 ALB Deployment** ✅ **COMPLETED** (2025-12-08)
- **Status**: 256 LOC Tier2Orchestrator with comprehensive error handling
- **Completed Tasks**:
  - ✅ Implemented `Tier2Orchestrator` class extending Tier1Orchestrator
  - ✅ Added conditional ALB creation with `enable_alb` flag
  - ✅ Implemented target group creation and EC2 instance registration
  - ✅ Added health check polling with configurable timeout
  - ✅ Updated DeploymentState with ALB ARN, DNS, and target group
  - ✅ Added ALB cleanup to DestructionService (deregister → delete target group → delete ALB)
  - ✅ Created comprehensive test suite (5 tests, 100% pass rate, 212 total tests passing)
  - ✅ Updated n8n_url to use ALB DNS for Tier 2 deployments
- **Deliverable**: ✅ Production-ready ALB-backed deployments with proper rollback

**Priority 7: Epic 13 - Tier 3 GPU/CloudFront** (2-3 weeks)
- **Dependencies**: Epic 12, CloudFront service expansion (Priority 5)
- **Tasks**:
  - Implement `Tier3Orchestrator` class
  - Add CloudFront distribution with ALB origin
  - Add GPU instance type validation
  - Update UserData templates for NVIDIA runtime
  - Add CloudFront-specific health checks
  - Integrate with DeploymentState model
  - Add CloudFront teardown to DestructionService
  - Test with actual GPU workloads (g4dn.xlarge)
- **Deliverable**: GPU-enabled, globally distributed deployments

**Priority 10: Epic 14 - ComfyUI Integration for LTX-2** (1-2 weeks)
- **Dependencies**: Epic 4 (Deployment Lifecycle), Epic 13 (GPU Support)
- **Tasks**:
  - **Story 14.1**: Add ComfyUI service to Docker Compose, configure EFS volumes, update UserDataConfig model with `comfyui_port` field, update services template
  - **Story 14.2**: Add ComfyUI health check function, integrate into health service, update status command
  - **Story 14.3**: Create ComfyUI setup script template, install ComfyUI Manager and LTX-2 nodes, configure for GPU tier only
  - **Story 14.4**: Add NGINX reverse proxy configuration for ComfyUI with WebSocket support and extended timeouts
- **Deliverable**: ComfyUI service with LTX-2 video generation support for GPU deployments

### 🔒 LONG-TERM (Month 4-6) - Security & Compliance

**Priority 8: Epic 10 - Security & Compliance** (2-3 weeks)
- **Tasks**:
  - **Story 10.1**: Private subnets, NACLs, VPC flow logs, TLS/HTTPS enforcement
  - **Story 10.2**: IAM role-based access, least privilege, SCP awareness, access auditing
  - **Story 10.3**: EBS encryption, EFS encryption, KMS customer-managed keys, secrets rotation
    - **Future Enhancement**: Migrate from UserData-embedded secrets to AWS Secrets Manager or Systems Manager Parameter Store
    - **Current State**: POSTGRES_PASSWORD and other secrets are embedded in UserData scripts (base64 encoded)
    - **Target State**: Store secrets in AWS Secrets Manager/Parameter Store, inject via IAM instance profile permissions
    - **Benefits**: Centralized secret management, automatic rotation, audit trail, no secrets in UserData logs
  - **Story 10.4**: Compliance tagging, CloudTrail integration, compliance reporting
- **Deliverable**: Production-grade security and compliance

**Priority 9: Epic 11 - Complete Error Handling** (1-2 weeks)
- **Tasks**:
  - **Story 11.1**: Error detection and classification system
  - **Story 11.2**: User guidance with remediation steps
  - **Story 11.3**: Retry logic with exponential backoff
  - **Story 11.4**: ✅ Already prioritized (see Priority 1)
- **Deliverable**: Comprehensive error handling and recovery

### 🧪 ONGOING - Quality & Testing

**Integration Tests** (ongoing)
- Add smoke tests for AWS connectivity
- Test full deployment → destruction → state recovery cycle
- Add performance benchmarks (deployment speed, resource usage)
- Integrate with CI/CD pipeline

**Documentation** (ongoing)
- Update CLAUDE.md with error handling patterns
- Create troubleshooting guide with common issues
- Add deployment cookbook with best practices
- Record demo videos for each deployment tier

**Security Enhancements** (future consideration)
- **AWS Secrets Manager/Parameter Store Integration**: Migrate from UserData-embedded secrets to AWS-managed secret storage
  - **Current Limitation**: Secrets (POSTGRES_PASSWORD, etc.) are embedded in UserData scripts, visible in EC2 instance metadata and logs
  - **Proposed Solution**: Store secrets in AWS Secrets Manager or Systems Manager Parameter Store
  - **Implementation**: 
    - Create secrets in Secrets Manager/Parameter Store during deployment
    - Grant EC2 instance profile permissions to read secrets
    - Update UserData scripts to fetch secrets at runtime (not embed them)
    - Update docker-compose to use secrets from environment (fetched via AWS CLI/SDK)
  - **Benefits**: 
    - No secrets in UserData logs or instance metadata
    - Centralized secret management and rotation
    - Audit trail via CloudTrail
    - Compliance with security best practices
  - **Considerations**: 
    - Additional IAM permissions required
    - Slight increase in instance startup time (secrets fetch)
    - Cost: Secrets Manager charges per secret ($0.40/month + $0.05/10K API calls)
    - Parameter Store Standard is free, Advanced tier ($0.05/parameter/month)

## Dependencies Overview

- Epic 1 → enables Epics 2, 3, 4, and 7.
- Epics 2 and 3 → required alongside Epic 1 to deliver Epics 4 and 8.
- Epic 4 → prerequisite for Epics 5, 6, 8, 9, 10, 11, 12, and 14.
- Epic 5 → prerequisite for Epic 9.
- **Story 11.4 (Error Handling)** → ✅ **COMPLETE** - Error handling and rollback implemented.
- Epic 12 → prerequisite for Epic 13.
- Epic 13 → prerequisite for Epic 14 (GPU support required for ComfyUI/LTX-2).

## Implementation Time Estimates

| Priority | Item | Estimated Time | Cumulative |
|----------|------|----------------|------------|
| 1 | Refactor Tier1Orchestrator | 1 day | Week 1 |
| 2 | Story 4.10 (DL AMI Support) | ✅ Done | - |
| 3 | Expand ALB Service | ✅ Done | - |
| 4 | Expand CloudFront Service | ✅ Done | - |
| 6 | Epic 12 (Tier 2 ALB) | ✅ Done | - |
| 7 | Epic 13 (Tier 3 GPU/CDN) | 2-3 weeks | Month 2 |
| 8 | Epic 10 (Security) | 2-3 weeks | Month 3 |
| 9 | Epic 11 (Error Handling) | 1-2 weeks | Month 3 |
| 10 | Epic 14 (ComfyUI/LTX-2) | 1-2 weeks | Month 3-4 |

**Total**: ~3-3.5 months to complete all remaining features (including ComfyUI integration)
