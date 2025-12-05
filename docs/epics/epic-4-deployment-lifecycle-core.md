# Epic 4: Deployment Lifecycle - Core Operations

## Epic Goal

Implement core deployment operations: create, list, and inspect deployments. This includes AWS resource provisioning, service deployment, and deployment state management.

## Epic Description

**Context:**
The core deployment workflow is the primary user-facing feature. Users need to create deployments, view their deployments, and inspect deployment details.

**Requirements from PRD:**
- Section 6.1: Deployment Creation
- Section 6.2: Deployment Listing
- Section 6.3: Deployment Inspection

**Success Criteria:**
- Users can create deployments via CLI
- All AWS resources are provisioned correctly
- Services are deployed and accessible
- Deployment state is persisted
- Users can list and inspect deployments

## Stories

1. **Story 4.1:** VPC Service Implementation
   - Create VPC with subnets
   - Create internet gateway and route tables
   - Discover existing VPCs
   - Validate VPC configuration

2. **Story 4.2:** EFS Service Implementation
   - Create EFS file system
   - Create mount targets in subnets
   - Wait for mount target availability
   - Validate EFS is accessible

3. **Story 4.3:** Security Group Service Implementation
   - Create security groups with proper rules
   - Configure ingress/egress rules for AI stack
   - Support tier-specific security group rules
   - Validate security group configuration

4. **Story 4.4:** EC2 Service Implementation
   - Launch EC2 instances (spot/on-demand)
   - Generate and inject UserData scripts
   - Wait for instance readiness
   - Retrieve instance metadata (IPs, status)

5. **Story 4.5:** UserData Script Generation
   - Generate EFS mount commands
   - Generate Docker Compose startup script
   - Configure service environment variables
   - Handle tier-specific configurations

6. **Story 4.6:** Deployment Orchestrator - Tier 1 (Dev)
   - Coordinate VPC → EFS → Security Group → EC2 workflow
   - Handle resource creation dependencies
   - Save deployment state
   - Display deployment progress with Rich UI

7. **Story 4.7:** Deployment Listing Command
   - List all deployments from state directory
   - Display deployment status, tier, region
   - Filter by status, region, tier
   - Sort by name, creation time, cost

8. **Story 4.8:** Deployment Inspection Command
   - Show detailed deployment information
   - Display service endpoints and URLs
   - Show resource inventory
   - Display health status and costs

9. **Story 4.9:** UserData Log Display After Deployment
   - Automatically fetch and display UserData initialization logs
   - Wait for SSM agent readiness and UserData completion
   - Display logs using Rich formatting
   - Fallback to cloud-init logs if needed

10. **Story 4.10:** Deep Learning AMI Support
    - Configurable OS selection (Amazon Linux 2023, Ubuntu 22.04, Ubuntu 24.04, Amazon Linux 2)
    - Architecture selection (x86_64, ARM64/Graviton)
    - Deep Learning AMI type selection (Base, PyTorch, TensorFlow, Multi-Framework)
    - Query AWS Deep Learning AMIs using official AMI name patterns
    - CLI and config file support for AMI configuration
    - Maintain backward compatibility with existing deployments

## Dependencies

- Requires: Epic 1 (Foundation), Epic 2 (Resource Discovery), Epic 3 (Cost Optimization)
- Blocks: Epic 5 (Validation), Epic 6 (Updates/Destruction)

## Definition of Done

- [x] Tier 1 (Dev) deployments can be created end-to-end
- [x] All AWS resources are created correctly
- [x] Services are accessible after deployment
- [x] Deployment state is persisted
- [x] List and inspect commands work correctly
- [x] UserData logs are displayed after deployment
- [x] Unit and integration tests with 80%+ coverage (85% orchestrator, 86-94% CLI commands)
- [ ] Deep Learning AMI selection with configurable OS, architecture, and AMI type (Story 4.10)

## Epic Status

**Status:** 🔄 **IN PROGRESS** - 9 stories completed, 1 story ready (2025-01-27)

Completed stories in Epic 4:
- Stories 4.1-4.4: Core AWS resource services (VPC, EFS, Security Groups, EC2)
- Story 4.5: UserData script generation with templates
- Story 4.6: Tier 1 deployment orchestrator with full workflow
- Story 4.7: Deployment listing with filters and sorting
- Story 4.8: Deployment inspection with detailed information
- Story 4.9: UserData log display after deployment

Ready for implementation:
- Story 4.10: Deep Learning AMI Support - Configurable AMI selection with OS, architecture, and AMI type options

**Key Achievements:**
- Complete end-to-end deployment workflow operational
- All gaps identified in earlier reviews have been resolved
- Comprehensive test coverage achieved across all components
- Enhanced AMI selection capability with Deep Learning AMI support
