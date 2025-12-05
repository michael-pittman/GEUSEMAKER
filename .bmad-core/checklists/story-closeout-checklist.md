# Story Close-Out Checklist

The Scrum Master should use this checklist to validate that completed stories meet all requirements and are ready for stakeholder handoff. This ensures quality delivery and proper closure of development work.

[[LLM: INITIALIZATION INSTRUCTIONS - STORY CLOSE-OUT VALIDATION

Before proceeding with this checklist, ensure you have access to:

1. The completed story document with implementation details
2. The original story requirements and acceptance criteria
3. QA review results and any resolution notes
4. Test results and validation reports
5. Documentation updates and user guides
6. Stakeholder feedback or demo results (if applicable)

IMPORTANT: This checklist validates completed stories AFTER implementation is finished.

CLOSE-OUT PRINCIPLES:

1. Completeness - All acceptance criteria must be met
2. Quality - Code meets standards and passes all tests
3. Documentation - All changes are properly documented
4. Integration - Changes work with existing systems
5. Handoff Ready - Stakeholders can use the delivered functionality

REMEMBER: We're ensuring the story delivers value and is ready for production use.]]

## 1. ACCEPTANCE CRITERIA VALIDATION

[[LLM: Every acceptance criterion must be demonstrably met. Verify:

1. Each AC has clear evidence of completion
2. Implementation matches the original requirements
3. No scope creep or missing functionality
4. Edge cases and error scenarios are handled
5. Performance and security requirements are met

Look for concrete evidence, not just claims of completion.]]

- [ ] All acceptance criteria have been implemented and tested
- [ ] Implementation matches the original story requirements
- [ ] No unauthorized scope changes were made
- [ ] Edge cases and error scenarios are properly handled
- [ ] Performance requirements are met (if specified)
- [ ] Security requirements are satisfied (if applicable)

## 2. CODE QUALITY ASSESSMENT

[[LLM: Code must meet project standards and best practices. Check:

1. Code follows established patterns and conventions
2. Error handling is comprehensive and graceful
3. Performance considerations are addressed
4. Security best practices are followed
5. Code is maintainable and well-structured

Review both the implementation and any refactoring performed.]]

- [ ] Code follows project coding standards and conventions
- [ ] Error handling is comprehensive and provides clear messages
- [ ] Performance optimizations are implemented (if required)
- [ ] Security best practices are followed
- [ ] Code is well-structured and maintainable
- [ ] No technical debt was introduced
- [ ] Refactoring was performed if needed (see QA notes)

## 3. TESTING VALIDATION

[[LLM: Comprehensive testing ensures reliability. Verify:

1. All test types specified in the story are completed
2. Test results show passing status
3. Edge cases and error scenarios are tested
4. Integration testing validates system compatibility
5. Performance testing confirms requirements are met

Look for actual test results, not just test plans.]]

- [ ] Unit tests are implemented and passing
- [ ] Integration tests validate system compatibility
- [ ] End-to-end tests confirm full functionality
- [ ] Error scenarios and edge cases are tested
- [ ] Performance tests meet specified requirements
- [ ] Cross-platform testing completed (if applicable)
- [ ] Test coverage meets project standards

## 4. DOCUMENTATION COMPLETENESS

[[LLM: Documentation enables future maintenance and usage. Check:

1. All code changes are documented
2. User guides and README files are updated
3. API documentation is current (if applicable)
4. Configuration changes are documented
5. Troubleshooting guides are provided

Ensure documentation is accurate and accessible.]]

- [ ] Code comments and inline documentation are complete
- [ ] README files and user guides are updated
- [ ] API documentation is current (if applicable)
- [ ] Configuration changes are documented
- [ ] Troubleshooting and error recovery guides are provided
- [ ] Architecture diagrams are updated (if needed)
- [ ] Change logs and version notes are complete

## 5. INTEGRATION AND DEPLOYMENT

[[LLM: Changes must work in the broader system context. Verify:

1. Changes integrate with existing systems
2. Deployment procedures are updated
3. Environment configurations are correct
4. Rollback procedures are documented
5. Monitoring and alerting are configured

Ensure the system remains stable and operational.]]

- [ ] Changes integrate properly with existing systems
- [ ] Deployment procedures are updated and tested
- [ ] Environment configurations are correct
- [ ] Rollback procedures are documented and tested
- [ ] Monitoring and alerting are configured
- [ ] No breaking changes to existing functionality
- [ ] System stability is maintained

## 6. QA AND REVIEW COMPLETION

[[LLM: Quality assurance ensures delivery standards. Check:

1. QA review is completed and approved
2. All identified issues are resolved
3. Code review feedback is addressed
4. Security review is completed (if required)
5. Performance review validates requirements

Ensure all quality gates are passed.]]

- [ ] QA review is completed and approved
- [ ] All identified issues are resolved
- [ ] Code review feedback is addressed
- [ ] Security review is completed (if required)
- [ ] Performance review validates requirements
- [ ] Stakeholder demo/feedback is positive
- [ ] Final approval is obtained

## 7. KNOWLEDGE TRANSFER

[[LLM: Knowledge transfer ensures long-term success. Verify:

1. Implementation details are documented
2. Key decisions and trade-offs are explained
3. Future maintenance considerations are noted
4. Team knowledge is shared
5. Lessons learned are captured

Enable future developers to understand and maintain the code.]]

- [ ] Implementation approach and decisions are documented
- [ ] Key technical decisions and trade-offs are explained
- [ ] Future maintenance considerations are noted
- [ ] Team knowledge sharing is completed
- [ ] Lessons learned are captured and shared
- [ ] Handoff documentation is complete
- [ ] Support procedures are established

## 8. STORY CLOSURE VALIDATION

[[LLM: Final validation ensures complete closure. Check:

1. All story tasks are completed
2. Story status is updated to "Done"
3. Time tracking is accurate
4. Story is ready for sprint review
5. No loose ends remain

Ensure clean closure and proper handoff.]]

- [ ] All story tasks and subtasks are completed
- [ ] Story status is updated to "Done"
- [ ] Time tracking and effort estimates are accurate
- [ ] Story is ready for sprint review/demo
- [ ] No loose ends or follow-up items remain
- [ ] Stakeholder acceptance is confirmed
- [ ] Story can be marked as complete

## VALIDATION RESULT

[[LLM: FINAL CLOSE-OUT VALIDATION REPORT

Generate a comprehensive close-out report:

1. Quick Summary
   - Story completion status: COMPLETE / PARTIAL / BLOCKED
   - Quality score (1-10)
   - Handoff readiness assessment

2. Fill in the validation table with:
   - PASS: All requirements met
   - PARTIAL: Some gaps but acceptable
   - FAIL: Critical issues prevent closure

3. Specific Issues (if any)
   - List any remaining issues
   - Provide resolution recommendations
   - Identify any blocking dependencies

4. Handoff Readiness
   - Is the story ready for stakeholder handoff?
   - What support or documentation is needed?
   - Any risks or concerns for production use?

5. Lessons Learned
   - What went well during implementation?
   - What could be improved for future stories?
   - Key insights for the team

Be thorough - this is the final gate before stakeholder handoff.]]

| Category                           | Status | Issues |
| ---------------------------------- | ------ | ------ |
| 1. Acceptance Criteria Validation  | _TBD_  |        |
| 2. Code Quality Assessment         | _TBD_  |        |
| 3. Testing Validation              | _TBD_  |        |
| 4. Documentation Completeness      | _TBD_  |        |
| 5. Integration and Deployment      | _TBD_  |        |
| 6. QA and Review Completion        | _TBD_  |        |
| 7. Knowledge Transfer              | _TBD_  |        |
| 8. Story Closure Validation        | _TBD_  |        |

**Final Assessment:**

- **COMPLETE**: Story is fully implemented and ready for stakeholder handoff
- **PARTIAL**: Story is mostly complete but has minor issues to address
- **BLOCKED**: Critical issues prevent story closure (specify blocking factors)

**Handoff Readiness:**
- **READY**: Stakeholders can immediately use the delivered functionality
- **NEEDS SUPPORT**: Additional documentation or training required
- **NOT READY**: Significant issues prevent production use

**Quality Score:** ___/10

**Key Insights:**
- What went well during implementation?
- What could be improved for future stories?
- Any important lessons learned?

**Next Steps:**
- [ ] Mark story as "Done" in tracking system
- [ ] Schedule stakeholder demo/presentation
- [ ] Update sprint burndown and velocity
- [ ] Archive story documentation
- [ ] Plan retrospective discussion points 