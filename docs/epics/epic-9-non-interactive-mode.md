# Epic 9: User Experience - Non-Interactive Mode

## Epic Goal

Implement non-interactive deployment mode for automation and CI/CD integration with single-command deployment, configuration files, and machine-readable output.

## Epic Description

**Context:**
Non-interactive mode enables automation and CI/CD integration. Users need to deploy via single commands with configuration files and get machine-readable output.

**Requirements from PRD:**
- Section 3.2: Non-Interactive Mode
- Section 3.3: Informational Display

**Success Criteria:**
- Single command deployment with parameters
- Environment variable configuration support
- Configuration file support (JSON/YAML)
- Machine-readable output (JSON/YAML)
- Exit codes for success/failure detection
- Silent mode (suppress progress, only errors)

## Stories

1. **Story 9.1:** Configuration File Support
   - Parse JSON configuration files
   - Parse YAML configuration files
   - Validate configuration file format
   - Merge CLI args with config file values

2. **Story 9.2:** Environment Variable Configuration
   - Support environment variable overrides
   - Environment variable naming convention
   - Configuration precedence (CLI > env > file > defaults)

3. **Story 9.3:** Machine-Readable Output
   - JSON output format for all commands
   - YAML output format option
   - Structured text output
   - Exit codes for programmatic detection

4. **Story 9.4:** Silent Mode and Error-Only Output
   - Silent mode flag
   - Suppress progress indicators
   - Show only errors and warnings
   - Final status output

5. **Story 9.5:** Informational Display Command
   - Display service endpoints and URLs
   - Show default credentials (if applicable)
   - Display estimated hourly cost
   - Show health status of all services
   - Provide SSH access information
   - Show next steps and recommendations

## Dependencies

- Requires: Epic 4 (Deployment Lifecycle), Epic 5 (Validation)
- Blocks: None (enhancement feature)

## Definition of Done

- [ ] Single command deployment works
- [ ] Configuration files are supported (JSON/YAML)
- [ ] Environment variables work correctly
- [ ] Machine-readable output is available
- [ ] Exit codes indicate success/failure
- [ ] Silent mode suppresses non-error output
- [ ] Unit tests with 80%+ coverage

