# Epic 2: AWS Resource Discovery & Management

## Epic Goal

Enable GeuseMaker to discover, validate, and manage existing AWS resources (VPCs, subnets, security groups, key pairs, EFS, load balancers, CloudFront) to support resource reuse and reduce deployment costs.

## Epic Description

**Context:**
Users often have existing AWS infrastructure they want to reuse rather than creating new resources. This epic enables GeuseMaker to discover existing resources, validate their compatibility, and allow users to select existing resources or create new ones.

**Requirements from PRD:**
- Section 4.1: AWS Resource Discovery
- Section 4.2: Resource Selection
- Section 4.3: Resource Provenance

**Success Criteria:**
- System can discover all required AWS resource types
- Users can select existing resources or create new ones
- Resource validation ensures compatibility
- Resource provenance is tracked for safe cleanup

## Stories

1. **Story 2.1:** VPC and Subnet Discovery Service
   - Discover existing VPCs in selected region
   - Discover subnets within selected VPC
   - Validate subnet availability zones and CIDR blocks
   - Cache discovery results

2. **Story 2.2:** Security Group and Key Pair Discovery
   - Discover existing security groups in VPC
   - Discover SSH key pairs in region
   - Validate security group rules for compatibility
   - Display resource details for user selection

3. **Story 2.3:** EFS and Load Balancer Discovery
   - Discover existing EFS file systems in region
   - Discover existing load balancers in VPC
   - Discover CloudFront distributions (global)
   - Validate resource compatibility

4. **Story 2.4:** Resource Selection UI and Validation
   - Interactive resource selection with Rich tables
   - Resource validation logic
   - Dependency validation (e.g., subnet in VPC)
   - Resource provenance tracking

## Dependencies

- Requires: Epic 1 (Project Foundation) - needs AWS client factory and CLI infrastructure
- Blocks: Epic 4 (Deployment Lifecycle) - deployment needs resource discovery

## Definition of Done

- [x] All resource types can be discovered
- [x] Resource validation ensures compatibility
- [x] Users can select existing or create new resources
- [x] Resource provenance is tracked in deployment state
- [x] Discovery results are cached to reduce API calls
- [x] Unit tests with 80%+ coverage (90% overall coverage achieved)
- [ ] Integration tests with real AWS resources (acceptable to defer - unit tests provide sufficient coverage)
