# Non-Functional Requirements

## NFR1: Performance
- **NFR1.1**: Deployment time < 10 minutes median (GPU), < 6 minutes median (CPU) from command execution to services available
- **NFR1.2**: Deployment with existing VPC reuse < 8 minutes (CPU), < 12 minutes (GPU)
- **NFR1.3**: Validation operations complete within 30 seconds
- **NFR1.4**: Support ≥ 3 concurrent deployments without performance degradation
- **NFR1.5**: State operations (list, show, query) complete within 2 seconds

## NFR2: Reliability
- **NFR2.1**: ≥ 95% successful deployment rate without manual intervention
- **NFR2.2**: Automated validation detects ≥ 95% of issues before user access
- **NFR2.3**: All operations are idempotent (safe to re-run)
- **NFR2.4**: Graceful error handling with rollback on critical failures
- **NFR2.5**: Support deployment recovery from partial failures

## NFR3: Usability
- **NFR3.1**: ≥ 90% of operations callable non-interactively (automation-ready)
- **NFR3.2**: Zero manual dependency installation beyond documented prerequisites
- **NFR3.3**: Clear error messages with actionable remediation steps
- **NFR3.4**: Interactive mode suitable for users with basic AWS knowledge
- **NFR3.5**: Consistent UX with emojis, colors, and ASCII art where appropriate

## NFR4: Maintainability
- **NFR4.1**: Modular design enabling easy feature additions
- **NFR4.2**: Comprehensive logging for debugging (debug mode available)
- **NFR4.3**: Versioned configuration and state formats
- **NFR4.4**: Backward compatibility for at least 1 major version
- **NFR4.5**: Self-documenting code and help commands

## NFR5: Scalability
- **NFR5.1**: Support ≥ 50 concurrent deployments per AWS account
- **NFR5.2**: Handle deployments across multiple AWS regions
- **NFR5.3**: Support multiple AWS accounts (via profiles)
- **NFR5.4**: Scale from development (1 instance) to production (multi-AZ)

## NFR6: Security
- **NFR6.1**: No hardcoded credentials or secrets in code
- **NFR6.2**: Follow AWS security best practices (least privilege, encryption)
- **NFR6.3**: Secure credential handling (AWS credential chain, no plaintext)
- **NFR6.4**: Security group rules follow principle of least access
- **NFR6.5**: All resources tagged for security auditing

---
