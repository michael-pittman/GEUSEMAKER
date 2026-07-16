# Epic 6: Deployment Updates & Destruction

## Epic Goal

Enable users to update existing deployments (scale, reconfigure, patch) and safely destroy deployments while preserving reused resources.

## Epic Description

**Context:**
Users need to manage the lifecycle of their deployments beyond initial creation. They need to update configurations, scale resources, and safely destroy deployments.

**Requirements from PRD:**
- Section 6.5: Deployment Updates
- Section 6.6: Deployment Destruction

**Success Criteria:**
- Users can update deployment configurations
- Resource scaling works correctly
- Data is preserved during updates
- Destruction only deletes created resources
- Reused resources are preserved

## Stories

1. **Story 6.1:** Deployment Update Command
   - Update service configurations
   - Scale compute resources (instance type, count)
   - Update container images
   - Preserve data during updates

2. **Story 6.2:** Deployment Rollback Implementation
   - Rollback to previous deployment configuration
   - Rollback service updates
   - Preserve data during rollback
   - Validate rollback success

3. **Story 6.3:** Deployment Destruction Command
   - Confirm destruction (require explicit confirmation)
   - Delete created resources in correct order
   - Preserve reused resources
   - Handle resource dependencies
   - Generate destruction report

4. **Story 6.4:** Resource Cleanup and Orphan Detection
   - Detect orphaned resources
   - Clean up resources in dependency order
   - Remove deployment state
   - Validate cleanup completion

5. **Story 6.5:** Credential Rotation and Security Patches
   - Rotate service credentials (n8n, PostgreSQL, API keys)
   - Apply security patches to container images
   - Preserve data during operations
   - Validate patch compatibility

## Dependencies

- Requires: Epic 4 (Deployment Lifecycle) - needs deployments to update/destroy
- Requires: Epic 2 (Resource Discovery) - Story 2.4 provides provenance tracking for safe destruction
- Requires: Epic 3 (Cost Optimization) - Story 3.4 provides resource tagging for orphan detection
- Requires: Epic 5 (Validation & Health Monitoring) - Story 5.2 provides health checks for auto-rollback
- Blocks: None (enhancement feature)

### Dependency Validation Status

✅ **Epic 2 (Provenance Tracking)**: Story 2.4 is Done - Provenance tracking available for Story 6.3  
✅ **Epic 3 (Resource Tagging)**: Story 3.4 is Done - Tagging available for Story 6.4  
✅ **Epic 5 (Health Checks)**: Story 5.2 is Done - Health service available for Story 6.2 auto-rollback  
✅ **Epic 4 (Deployment Lifecycle)**: All stories Done - Deployment infrastructure available

## Definition of Done

- [ ] Deployment updates work correctly
- [ ] Data is preserved during updates
- [ ] Rollback functionality works
- [ ] Destruction only deletes created resources
- [ ] Reused resources are preserved
- [ ] Unit and integration tests with 80%+ coverage

## QA Validation Results

**Validated by:** Quinn (QA Agent)  
**Validation Date:** 2025-01-21  
**Overall Status:** ⚠️ **APPROVED WITH GAPS**

### PRD Requirements Coverage Analysis

#### Section 6.5: Deployment Updates
| PRD Requirement | Story Coverage | Status |
|----------------|----------------|--------|
| Update service configurations | Story 6.1 | ✅ Covered |
| Scale compute resources (instance type, count) | Story 6.1 | ✅ Covered |
| **Rotate credentials** | **None** | ❌ **GAP IDENTIFIED** |
| Update container images | Story 6.1 | ✅ Covered |
| **Apply security patches** | **None** | ❌ **GAP IDENTIFIED** |
| Preserve data during updates | Story 6.1 | ✅ Covered |

#### Section 6.6: Deployment Destruction
| PRD Requirement | Story Coverage | Status |
|----------------|----------------|--------|
| Confirm destruction (explicit confirmation) | Story 6.3 | ✅ Covered |
| Delete created resources | Story 6.3 | ✅ Covered |
| Preserve reused resources | Story 6.3 | ✅ Covered |
| Handle resource dependencies | Story 6.3 | ✅ Covered |
| Detect and clean up orphaned resources | Story 6.4 | ✅ Covered |
| Generate destruction report | Story 6.3 | ✅ Covered |
| Remove deployment state | Story 6.3 | ✅ Covered |

### Story Quality Assessment

#### Story 6.1: Deployment Update Command
**Status:** ✅ **APPROVED**  
**Strengths:**
- Clear acceptance criteria with measurable outcomes
- Comprehensive task breakdown covering all update scenarios
- Proper data preservation focus (EFS)
- State backup for rollback capability
- Good test coverage requirements (80%+)

**Issues Identified:**
1. ⚠️ **AC #3**: "Update supports scaling (future: multiple instances)" - Too vague. Should specify if this is in-scope for this story or deferred.
2. ⚠️ **Missing PRD Coverage**: Credential rotation (PRD 6.5) not addressed
3. ⚠️ **Missing PRD Coverage**: Security patches (PRD 6.5) not addressed
4. ℹ️ **Task 2**: Instance type update requires stop/start - should mention potential downtime impact

**Recommendations:**
- Clarify AC #3 scope or defer to future story
- Consider adding credential rotation as separate story or task
- Consider adding security patch mechanism (may be handled via container image updates)

#### Story 6.2: Deployment Rollback Implementation
**Status:** ✅ **APPROVED**  
**Strengths:**
- Well-structured rollback flow
- Supports both manual and automatic rollback
- Multiple rollback levels (last N states)
- Integration with health checks for automatic rollback
- Comprehensive rollback history tracking

**Issues Identified:**
1. ⚠️ **AC #8**: Automatic rollback on health check failure - needs validation that health check service (Epic 5) is available
2. ℹ️ **Task 7**: Rollback history storage - should specify retention policy (mentions "last 5 states" in constraints)
3. ℹ️ **Task 8**: Auto-rollback timeout (15 min) - should validate this is sufficient for all update scenarios

**Recommendations:**
- Verify Epic 5 (Health Monitoring) dependency is met before implementing AC #8
- Clarify rollback state retention policy in data model
- Consider making auto-rollback timeout configurable per deployment tier

#### Story 6.3: Deployment Destruction Command
**Status:** ✅ **APPROVED**  
**Strengths:**
- Explicit confirmation requirement (type name) - excellent safety measure
- Provenance-based deletion logic (reused vs created)
- Correct dependency order for resource deletion
- Comprehensive destruction report
- State archival for audit trail
- Force flag for automation scenarios

**Issues Identified:**
1. ⚠️ **Task 3**: Deletion order mentions ALB/CloudFront but these are Tier 2+ features - should validate tier before attempting deletion
2. ℹ️ **Task 4**: Provenance checking - should verify provenance tracking is implemented in Epic 2/4
3. ℹ️ **Missing**: No mention of handling partial deletion failures (mentioned in constraints but not in tasks)

**Recommendations:**
- Add tier validation before attempting ALB/CloudFront deletion
- Verify provenance tracking implementation in Epic 2/4
- Add explicit task for handling partial deletion failures with retry logic

#### Story 6.4: Resource Cleanup and Orphan Detection
**Status:** ✅ **APPROVED**  
**Strengths:**
- Comprehensive orphan detection across all resource types
- Multi-region scanning capability
- Cost estimation for orphaned resources
- Selective deletion with dry-run support
- Good safety measures (confirmation, dry-run)

**Issues Identified:**
1. ⚠️ **Task 2**: Orphan detection relies on `geusemaker:deployment` tag - should verify tagging strategy from Epic 3/4
2. ℹ️ **Task 9**: Multi-region scan - should specify performance expectations (may take "several minutes")
3. ℹ️ **Missing**: No explicit handling for resources that fail to delete (mentioned in constraints)

**Recommendations:**
- Verify tagging strategy consistency across all epics
- Add explicit error handling task for failed deletions
- Consider adding progress indicators for long-running multi-region scans

### Dependency Validation

✅ **Epic 4 Dependency**: Correctly identified - update/destroy operations require existing deployments  
✅ **No Blocking Dependencies**: Correctly identified as enhancement feature

**Additional Dependencies to Verify:**
- Epic 2: Provenance tracking (required for Story 6.3)
- Epic 3: Resource tagging (required for Story 6.4)
- Epic 5: Health monitoring (required for Story 6.2 auto-rollback)

### Definition of Done Assessment

**Current DoD:**
- ✅ Covers functional requirements
- ✅ Includes test coverage requirement (80%+)
- ⚠️ Lacks specific acceptance criteria validation
- ⚠️ No integration test requirements specified
- ⚠️ No performance requirements for update/destroy operations

**Recommendations:**
- Add integration test requirements (e.g., "Integration tests cover end-to-end update and destroy workflows")
- Add performance criteria (e.g., "Update operations complete within 10 minutes for instance type changes")
- Specify validation that all acceptance criteria are met

### Critical Gaps Summary

1. **🔴 HIGH PRIORITY**: Credential rotation (PRD 6.5) - Not covered in any story
2. **🔴 HIGH PRIORITY**: Security patches (PRD 6.5) - Not covered in any story
3. **🟡 MEDIUM PRIORITY**: Partial deletion failure handling - Mentioned in constraints but not in tasks
4. **🟡 MEDIUM PRIORITY**: Multi-instance scaling clarification - AC #3 in Story 6.1 is vague

### Overall Assessment

**Epic Status:** ⚠️ **APPROVED WITH GAPS**

**Summary:**
Epic 6 provides comprehensive coverage for deployment updates and destruction with well-structured stories and clear acceptance criteria. However, two PRD requirements (credential rotation and security patches) are not addressed. The stories are technically sound and follow good practices for safety (confirmations, provenance tracking, data preservation).

**Recommendations:**
1. **Immediate**: Address credential rotation and security patches - either add tasks to Story 6.1 or create new story
2. **Before Implementation**: Verify dependencies (Epic 2 provenance, Epic 3 tagging, Epic 5 health checks)
3. **During Implementation**: Add explicit error handling for partial failures
4. **Future Consideration**: Clarify multi-instance scaling scope

**Risk Level:** 🟡 **MEDIUM** - Gaps exist but core functionality is well-defined

### Dependency Validation Summary**Epic 2 (Resource Discovery) - Provenance Tracking:**
- ✅ **Status**: Story 2.4 (Resource Selection UI and Validation) is **Done**
- ✅ **Coverage**: Task 5 implements provenance tracking with `ResourceProvenance` enum (CREATED, REUSED, AUTO_DISCOVERED)
- ✅ **Usage**: Story 6.3 (Destruction) can use provenance to preserve reused resources
- ✅ **Verification**: Provenance is stored in `DeploymentState` for each resource**Epic 3 (Cost Optimization) - Resource Tagging:**
- ✅ **Status**: Story 3.4 (Cost Tracking and Budget Alerts) is **Done**
- ✅ **Coverage**: Task 1 implements resource tagging with `geusemaker:deployment` tag
- ✅ **Usage**: Story 6.4 (Orphan Detection) can use tags to identify GeuseMaker resources
- ✅ **Verification**: Standard tag schema includes `geusemaker:deployment`, `geusemaker:tier`, `geusemaker:created-at`, `geusemaker:created-by`**Epic 5 (Validation & Health Monitoring) - Health Checks:**
- ✅ **Status**: Story 5.2 (Health Service Implementation) is **Done**
- ✅ **Coverage**: Implements `HealthCheckClient` with service-specific health checks
- ✅ **Usage**: Story 6.2 (Rollback) can use health checks for automatic rollback on failure
- ✅ **Verification**: Health service supports n8n, Ollama, Qdrant, Crawl4AI, PostgreSQL health checks**Conclusion**: All dependencies are satisfied. Epic 6 stories can proceed with implementation.