# Epic 5: Deployment Validation & Health Monitoring

## Epic Goal

Implement comprehensive deployment validation and health monitoring to ensure all services are running correctly and detect issues before users access the deployment.

## Epic Description

**Context:**
Users need confidence that their deployment is working correctly. The system must validate all services are healthy and provide ongoing monitoring capabilities.

**Requirements from PRD:**
- Section 8.1: Pre-Deployment Validation
- Section 8.2: Deployment Health Checks
- Section 8.3: Continuous Monitoring
- Section 8.4: Validation Reporting

**Success Criteria:**
- Pre-deployment validation catches issues early
- Post-deployment health checks validate all services
- Health monitoring detects service failures
- Validation reports are clear and actionable

## Stories

1. **Story 5.1:** Pre-Deployment Validation
   - Validate AWS credentials and permissions
   - Check AWS service quotas and limits
   - Verify required services available in region
   - Validate configuration parameters
   - Check for naming conflicts

2. **Story 5.2:** Health Service Implementation
   - Health check client for HTTP endpoints
   - Service health check logic (n8n, Ollama, Qdrant, Crawl4AI, PostgreSQL)
   - Health check result models
   - Retry logic with exponential backoff

3. **Story 5.3:** Post-Deployment Health Validation
   - Check compute instance status
   - Verify service containers are running
   - Test service health endpoints
   - Validate inter-service connectivity
   - Check persistent storage is mounted

4. **Story 5.4:** Validation Reporting
   - Generate validation report with pass/fail status
   - Show details for each validation check
   - Provide actionable remediation steps
   - Export validation results (JSON/YAML)

5. **Story 5.5:** Continuous Health Monitoring
   - `geusemaker monitor` command for continuous monitoring
   - Periodic health checks for all services
   - Alert on service failures
   - Track service uptime and availability
   - Monitor resource utilization (CPU, memory, disk)

## Dependencies

- Requires: Epic 4 (Deployment Lifecycle) - needs deployed services to validate
- Blocks: None (enhancement feature)

## Definition of Done

- [x] Pre-deployment validation catches common issues
- [x] Post-deployment health checks validate all services
- [x] Validation reports are clear and actionable
- [x] Health monitoring can detect service failures
- [x] Unit and integration tests with 80%+ coverage

