# Epic 12: Tier 2 Deployment Orchestrator (Automation/ALB)

## Epic Goal

Implement Tier 2 deployment orchestrator with Application Load Balancer support for production-ready automation workloads with high availability.

## Epic Description

**Context:**
Tier 2 deployments add ALB support for production workloads. This enables load balancing, health checks, and better reliability for automation engineer use cases.

**Requirements from PRD:**
- Section 2: Deployment Tiers - Tier 2: Automation Engineer
- Section 6.1: Deployment Creation (ALB support)

**Success Criteria:**
- ALB is created and configured correctly
- Target groups are configured for services
- Health checks are configured
- Services are accessible via ALB DNS
- Deployment state includes ALB information

## Stories

1. **Story 12.1:** ALB Service Implementation
   - Create Application Load Balancer
   - Create target groups for services
   - Configure health checks
   - Configure listeners and rules

2. **Story 12.2:** ALB Orchestrator Implementation
   - Extend base orchestrator for ALB support
   - Coordinate ALB creation in deployment workflow
   - Register EC2 instances with target groups
   - Wait for ALB to be active

3. **Story 12.3:** ALB Integration with Deployment State
   - Store ALB ARN and DNS in deployment state
   - Update deployment inspection to show ALB info
   - Include ALB in cost estimation
   - Handle ALB in deployment destruction

## Dependencies

- Requires: Epic 4 (Deployment Lifecycle Core) - needs base orchestrator
- Blocks: None (enhancement feature)

## Definition of Done

- [ ] ALB is created and configured correctly
- [ ] Services are accessible via ALB DNS
- [ ] Health checks work correctly
- [ ] Deployment state includes ALB information
- [ ] Unit and integration tests with 80%+ coverage

