# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**GeuseMaker** is an AI infrastructure deployment platform that provisions and manages a complete AI application stack on AWS. The system enables users to deploy workflow automation (n8n), LLM inference (Ollama), vector databases (Qdrant), and web scraping services (Crawl4AI) through a CLI with intelligent cost optimization using spot instances.

**Status**: Active development with core deployment features implemented

## Common Commands

```bash
# Setup (requires Python 3.12+)
python3.12 -m venv venv
source venv/bin/activate
pip install -e ".[dev]"

# Run CLI
geusemaker --help

# Lint (ruff check + format + mypy)
./scripts/lint.sh

# Run all tests
./scripts/test.sh

# Run single test file
pytest tests/unit/test_<module>.py -v

# Run single test function
pytest tests/unit/test_<module>.py::test_function_name -v

# Run tests with coverage
pytest --cov=geusemaker --cov-report=term-missing

# Run with zero delays for faster tests
pytest tests/unit/test_orchestration/ -v  # Tests use delay=0 by default

# Run integration tests (hits real AWS - manual only)
pytest tests/integration/ -v --no-cov

# Type checking only
mypy geusemaker

# Format code
ruff format .

# Auto-fix lint issues
ruff check . --fix
```

## Available CLI Commands

```bash
# Core deployment lifecycle
geusemaker deploy      # Deploy new infrastructure
geusemaker destroy     # Tear down deployment
geusemaker update      # Update running deployment
geusemaker rollback    # Rollback to previous state

# Monitoring and health
geusemaker status      # Show deployment status
geusemaker health      # Check deployment health
geusemaker monitor     # Monitor deployment metrics
geusemaker logs        # View application logs
geusemaker inspect     # Inspect deployment details
geusemaker list        # List all deployments
geusemaker list --discover-from-aws  # Discover deployments from AWS resources (state recovery)

# Cost and validation
geusemaker cost        # Show cost breakdown
geusemaker validate    # Run pre-deployment validation
geusemaker report      # Generate deployment report

# Maintenance
geusemaker cleanup     # Clean up orphaned resources
geusemaker backup      # Backup deployment state
geusemaker restore     # Restore from backup
geusemaker init        # Initialize new stack configuration
geusemaker info        # Show system info
```

## CLI Output Control

All commands support verbosity flags:

```bash
# Silent mode - suppress all non-error output
geusemaker deploy --silent

# Verbose/debug mode - show detailed execution info
geusemaker deploy --verbose  # or -v

# Normal mode (default) - standard output with emojis
geusemaker deploy
```

**Output implementation**: Use `console.print()` from `geusemaker.cli`, NOT `print()`
```python
from geusemaker.cli import console

# Messages respect verbosity settings automatically
console.print("User message", verbosity="info")  # Normal and verbose
console.print("Debug info", verbosity="debug")    # Verbose only
```

## Available MCP Tools

The following MCP (Model Context Protocol) servers are enabled for this project:

### aws-documentation

Access official AWS documentation directly from Claude Code:

```python
# Search for AWS documentation
search_documentation(search_phrase="EC2 spot instances", limit=10)

# Read a specific documentation page
read_documentation(url="https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/using-spot-instances.html")

# Get related documentation recommendations
recommend(url="https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/using-spot-instances.html")
```

**Use cases for GeuseMaker:**
- Looking up EFS mount options and configuration
- Understanding EC2 spot instance best practices
- Finding VPC and security group configuration details
- Researching Application Load Balancer setup

### aws-pricing

Get real-time AWS pricing information and cost estimates:

```python
# Get EC2 instance pricing for us-east-1
get_pricing(
    service_code="AmazonEC2",
    region="us-east-1",
    filters=[
        {"Field": "instanceType", "Value": "t3.medium", "Type": "EQUALS"},
        {"Field": "operatingSystem", "Value": "Linux", "Type": "EQUALS"}
    ]
)

# Discover available service codes
get_pricing_service_codes(filter="ec2")

# Get pricing attributes for a service
get_pricing_service_attributes(service_code="AmazonEC2")

# Get valid values for specific attributes
get_pricing_attribute_values(
    service_code="AmazonEC2",
    attribute_names=["instanceType", "location"]
)

# Generate cost analysis reports
generate_cost_report(
    pricing_data=pricing_response,
    service_name="Amazon EC2",
    pricing_model="ON DEMAND"
)
```

**Use cases for GeuseMaker:**
- Calculating deployment costs for different tier configurations
- Comparing spot instance pricing across regions
- Estimating EFS storage costs
- Generating cost reports for users

### Additional Available Servers (require configuration)

- **awslabs-cloudwatch**: Metrics, alarms, and logs analysis
  - Configure: `docker mcp config set awslabs-cloudwatch aws_region=us-east-1`

- **github-official**: GitHub API integration for repository management
  - Configure: `docker mcp secret set github.personal_access_token=<token>`

## Tech Stack

| Category | Technology | Purpose |
|----------|------------|---------|
| Language | Python 3.12+ | Primary development |
| AWS SDK | Boto3 1.35+ | AWS API integration |
| CLI Framework | Click 8.1+ | Command-line interface |
| Terminal UI | Rich 13.9+ | Interactive output |
| Interactive Prompts | questionary 2.0+ | User input/selection |
| Validation | Pydantic 2.9+ | Config validation |
| Testing | pytest 8.3+ | Test framework |
| Mocking | moto 5.0.25 | AWS service mocking |
| Linting | Ruff 0.5+ | Code quality |
| Type Checking | mypy 1.11+ | Static analysis |
| Package Manager | uv 0.4+ | Dependency management |

## Project Structure

```
geusemaker/
├── geusemaker/           # Main Python package
│   ├── cli/              # Click CLI + Rich UI components
│   ├── orchestration/    # Deployment workflows (spot, alb, cdn)
│   ├── services/         # AWS resource managers (ec2, efs, vpc, sg, alb)
│   ├── models/           # Pydantic models for state/config
│   ├── infra/            # Boto3 clients, state persistence
│   └── utils/            # Async helpers, retry logic
├── tests/
│   ├── unit/             # Mocked AWS tests
│   └── integration/      # Real AWS tests
└── config/               # Docker Compose, defaults
```

## Critical Coding Rules

These rules are **MANDATORY**:

1. **NEVER hardcode AWS credentials** - Use `boto3.Session()`
2. **NEVER use `print()` for output** - Use `console.print()` from Rich
3. **NEVER catch bare `Exception`** - Catch specific exceptions (`ClientError`, `ValidationError`)
4. **NEVER store secrets in state files** - State files are plain JSON
5. **ALWAYS use Pydantic models** - No raw dicts for configuration or state
6. **ALWAYS validate inputs at boundaries** - CLI arguments, user prompts, file reads
7. **ALWAYS include emojis in user output** - Use `EMOJI` dict from branding.py
8. **ALWAYS tag AWS resources** - Include `Stack: {stack_name}` tag on all resources
9. **ALWAYS use async for AWS calls** - Wrap with `asyncio.to_thread()` for blocking calls
10. **EFS is MANDATORY** - Every deployment MUST include EFS for data persistence

## Naming Conventions

| Element | Convention | Example |
|---------|------------|---------|
| Classes | PascalCase | `DeploymentState`, `EC2Service` |
| Functions/Methods | snake_case | `create_efs()`, `get_spot_price()` |
| Constants | SCREAMING_SNAKE | `MAIN_BANNER`, `EMOJI` |
| Private methods | `_prefix` | `_translate_aws_error()` |

## Linting Configuration

Ruff ignores certain rules for codebase patterns:
- `S101`: Asserts allowed in tests
- `E501`: Line length flexible (120 char max but not enforced)
- `B023`: Lambda loop variables (use explicit capture pattern instead)
- `BLE001`: Blind exception catching acceptable in rollback/monitoring
- `E731`: Lambda assignment acceptable in test fixtures

**Line length**: 120 characters (pyproject.toml), but existing code may exceed
**Quote style**: Double quotes enforced by formatter

## Architecture Key Points

- **Layered Monolith**: CLI → Orchestration → Services → Infrastructure
- **EFS Always Required**: All deployments use EFS for persistent storage (n8n workflows, Ollama models, Qdrant indexes, PostgreSQL data)
- **Three Deployment Tiers**:
  - Tier 1 (Dev): CPU-only spot instances, direct public IP
  - Tier 2 (Automation): CPU with ALB for high availability
  - Tier 3 (GPU): GPU instances with ALB + CloudFront CDN

## State Management

**State file location**: `~/.geusemaker/<stack_name>.json`

**State schema version**: Currently `STATE_SCHEMA_VERSION = 2`

**State updates**: Always use `StateManager` to persist state
```python
from geusemaker.infra import StateManager

manager = StateManager()
state = manager.load_state("my-stack")
# ... modify state ...
manager.save_state(state)
```

**State file contains**:
- Deployment configuration (immutable)
- Resource IDs (VPC, EFS, EC2, etc.)
- Cost tracking history
- Rollback records

**CRITICAL**: State files are plain JSON - NEVER store secrets

## Model Import Pattern

All Pydantic models are exported from `geusemaker.models`:

```python
# CORRECT - Import from central barrel export
from geusemaker.models import DeploymentConfig, DeploymentState, VPCInfo

# WRONG - Don't import from individual modules
from geusemaker.models.deployment import DeploymentConfig
```

**Available models**: See [models/__init__.py:66-123](geusemaker/models/__init__.py#L66-L123) for complete list

## Service Import Pattern

All service classes are exported from `geusemaker.services`:

```python
# CORRECT - Import from central barrel export
from geusemaker.services import EC2Service, EFSService, StateRecoveryService

# WRONG - Don't import from individual modules
from geusemaker.services.ec2 import EC2Service
```

**Available services**: See [services/__init__.py](geusemaker/services/__init__.py) for complete list

**Note**: When adding new services, remember to:
1. Create the service class in its module
2. Import it in `services/__init__.py`
3. Add it to the `__all__` list for public API export

## Important Implementation Patterns

### BaseService Pattern

All AWS service classes inherit from `BaseService` which provides:

1. **Cached boto3 clients**: Use `self._client(service_name)` to get clients
2. **Consistent error handling**: Use `self._safe_call(fn)` wrapper

```python
from geusemaker.services.base import BaseService

class MyService(BaseService):
    def __init__(self, client_factory: AWSClientFactory, region: str = "us-east-1"):
        super().__init__(client_factory, region)
        self._my_client = self._client("service-name")

    def some_operation(self, param: str) -> dict[str, Any]:
        """Perform AWS operation with error handling."""
        def _call() -> dict[str, Any]:
            return self._my_client.some_api_call(Param=param)

        return self._safe_call(_call)
```

**Benefits:**
- ClientError/BotoCoreError automatically wrapped as RuntimeError
- Consistent error messages across all services
- Client caching prevents redundant session creation

### CLI Styling (questionary + prompt_toolkit)

When using questionary for interactive prompts:

```python
# WRONG - passing dict directly causes AttributeError
result = questionary.select(prompt, choices=choices, style=style_dict).ask()

# CORRECT - convert dict to Style object
style = questionary.Style.from_dict(style_dict)
result = questionary.select(prompt, choices=choices, style=style).ask()
```

**Color formats**: prompt_toolkit uses hex colors, NOT Rich color names:
```python
# WRONG - Rich color names don't work in prompt_toolkit
custom_style = {"separator": "grey70"}

# CORRECT - Use hex colors
custom_style = {"separator": "#888888"}
```

### AWS API Fallback Patterns

**Pricing API**: Always handle zero/invalid prices with fallbacks:
```python
price = Decimal(str(price_str))
if price <= 0:
    raise RuntimeError("invalid zero price from API")  # Triggers fallback
```

**Service Quotas API**: `NoSuchResourceException` should be warnings, not failures:
```python
if "NoSuchResourceException" in exc_str:
    warnings.append(f"{label} quota check skipped (API limitation)")
```

### Lambda Closure Variable Capture

When using lambdas in loops, capture variables to avoid mypy errors:
```python
# WRONG - mypy: Cannot infer type of lambda
for service_code, quota_code in quotas:
    result = self._safe_call(lambda: client.get_quota(ServiceCode=service_code))

# CORRECT - Capture loop variables before lambda
for service_code, quota_code in quotas:
    _sc, _qc = service_code, quota_code
    result = self._safe_call(lambda: client.get_quota(ServiceCode=_sc))
```

### Validation Skip Option

Use `--skip-validation` flag for bypassing pre-deployment checks:
```bash
geusemaker deploy --skip-validation
```

### AWS Resource State Polling

Many AWS resources require time to transition between states. Follow the polling pattern:

```python
# Pattern: wait_for_<state>() method in service classes
def wait_for_available(self, resource_id: str, max_attempts: int = 60, delay: int = 5) -> None:
    """Poll describe_* API until resource reaches target state."""
    def _call() -> None:
        for attempt in range(max_attempts):
            resp = self._client.describe_resource(ResourceId=resource_id)
            state = resp["Resource"]["State"]

            if state == "available":
                return

            if state in ("deleting", "deleted", "error"):
                raise RuntimeError(f"Resource entered invalid state: {state}")

            if attempt < max_attempts - 1:
                time.sleep(delay)

        raise RuntimeError(f"Resource did not become available within {max_attempts * delay}s")

    self._safe_call(_call)
```

**Critical AWS state transitions requiring polling:**
- **EFS**: `create_file_system()` returns in `"creating"` state → must wait for `"available"` before `create_mount_target()`
- **EC2**: `run_instances()` returns in `"pending"` state → must wait for `"running"` before accessing IP
- **ALB**: Target registration takes time → poll until targets are `"healthy"`

**Pattern locations:**
- `EFSService.wait_for_available()` - [efs.py:32-69](geusemaker/services/efs.py#L32-L69)
- `EC2Service.wait_for_running()` - [ec2.py](geusemaker/services/ec2.py)

### EC2 AMI Selection Pattern

EC2 service uses a two-tier AMI selection strategy with region-aware mappings:

```python
# 1. Direct AMI lookup (amazon-linux-2023 base images only)
# Maps to specific, validated AMI IDs by region
EC2Service.AL2023_BASE_AMIS = {
    "us-east-1": {"x86_64": "ami-0941ba2cd9ee2998a", "arm64": "ami-08742254cf19c5488"},
    "us-west-2": {"x86_64": "ami-019056869a13971ff", "arm64": "ami-0c5b116eea276f6f1"},
    # ... more regions
}

# 2. Pattern-based search (fallback for all other OS/AMI types)
# Uses describe_images with name patterns for Deep Learning AMIs
```

**AMI selection logic** ([ec2.py:92-123](geusemaker/services/ec2.py#L92-L123)):
1. Try direct AMI ID lookup first (amazon-linux-2023 + base only)
2. Validate AMI exists and is available via `validate_ami()`
3. Falls back to pattern-based search if:
   - No mapping exists for the region
   - AMI validation fails
   - OS type is not amazon-linux-2023
   - AMI type is not "base"

**Benefits:**
- Faster deployments (skip describe_images API call)
- Guaranteed AMI availability by region
- Graceful fallback for all AMI types

### Network Interface Management

**Tagging network interfaces** ([tier1.py:168-175](geusemaker/orchestration/tier1.py#L168-L175)):
- Network interfaces are automatically tagged during EC2 launch
- Tags include: `Name: {stack_name}-eni`, `Stack: {stack_name}`, `Tier: {tier}`
- Use `ResourceType: "network-interface"` in TagSpecifications

**VPC cleanup** ([destruction/service.py:191-217](geusemaker/services/destruction/service.py#L191-L217)):
- `_delete_vpc_dependencies()` now handles orphaned network interfaces
- Network interfaces are discovered via `describe_network_interfaces()`
- Skips ENIs attached to running instances (auto-deleted with instance)
- Forcefully detaches and deletes orphaned ENIs before VPC deletion

**Critical**: Always clean up network interfaces BEFORE attempting VPC deletion to avoid dependency errors

### CLI Deployment Modes

GeuseMaker supports three deployment modes (see [README.md](README.md)):

1. **Interactive (default)**: Guided wizard with VPC/subnet/SG discovery
   ```bash
   geusemaker deploy
   ```

2. **Non-interactive**: For scripting and automation
   ```bash
   geusemaker deploy --no-interactive --vpc-id vpc-123 --subnet-id subnet-456
   ```

3. **Config file**: YAML/JSON config with CLI flag overrides
   ```bash
   geusemaker deploy --config deployment.yaml --instance-type t3.large
   ```

**Key flags:**
- `--vpc-id` + `--attach-internet-gateway`: Reuse VPC and add IGW/routes
- `--security-group-id`: Reuse SG (must have ports 22, 80, 5678, 2049)
- `--skip-validation`: Bypass pre-deployment checks

### State Recovery from AWS

If state files are lost, use `StateRecoveryService` to reconstruct deployment state from AWS resources:

```bash
# Discover deployments from AWS resources (scans for EC2 instances with Stack tag)
geusemaker list --discover-from-aws

# Discover in specific region
geusemaker list --discover-from-aws --region us-west-2
```

**How it works:**
- Scans AWS for EC2 instances tagged with `Stack: {stack_name}`
- Reconstructs state from instance metadata, VPC config, security groups, and EFS mounts
- Automatically saves discovered states to `~/.geusemaker/`
- Creates new state with `status="discovered"` and `resource_provenance="discovered"`

**Implementation**: [state_recovery.py](geusemaker/services/state_recovery.py)

### Using MCP Tools for AWS Research

When implementing AWS features, use MCP tools to research patterns:

```python
# 1. Search AWS documentation
search_documentation(search_phrase="EFS lifecycle state transitions")

# 2. Get CLI command suggestions
suggest_aws_commands(query="Wait for EFS filesystem to become available")

# 3. Read specific documentation pages
read_documentation(url="https://docs.aws.amazon.com/efs/latest/ug/...")
```

**Best practices:**
- Always research AWS API behavior before implementing
- Use `suggest_aws_commands()` to discover CLI patterns
- Check AWS documentation for state transitions and timing requirements

### Testing Patterns

**Service tests** (in `tests/unit/test_services/`):
```python
from moto import mock_aws

@mock_aws
def test_service_method_returns_expected_value() -> None:
    """Test description following docstring pattern."""
    svc = SomeService(AWSClientFactory(), region="us-east-1")
    result = svc.some_method(param="value")
    assert result["ExpectedKey"] == "expected_value"
```

**Orchestration tests** (in `tests/unit/test_orchestration/`):
- Use stub services (not moto) for orchestration layer tests
- Stub classes should track state: `self.waited_for_available = False`
- Verify orchestration logic, not AWS API behavior

**Stub service requirements**:
- When adding new AWS API calls, update stub classes in test files
- Example: Added `describe_network_interfaces()` to destruction tests
- Stubs should return minimal valid responses: `{"NetworkInterfaces": []}`

**Test organization:**
- Unit tests use `@mock_aws` decorator for AWS service mocking
- Integration tests hit real AWS (run manually, not in CI)
- Keep test delays at 0: `wait_for_available(fs_id, max_attempts=5, delay=0)`

**Error testing patterns:**
```python
# Test error messages with regex matching
with pytest.raises(RuntimeError, match="AWS call failed.*FileSystemNotFound"):
    svc.wait_for_available("fs-nonexistent", max_attempts=1, delay=0)
```

## Key Documents

- **PRD**: `docs/prd.md` (sharded in `docs/prd/`)
- **Architecture**: `docs/architecture.md` (sharded in `docs/architecture/`)
- **Stories**: `docs/stories/` - Implementation stories
- **Epics**: `docs/epics/` - Feature epics

## BMAD Development Methodology

This project uses the **BMad Method** for agile AI-driven development with specialized agents via slash commands:

- `/BMad/agents/dev` - **James**: Full Stack Developer for code implementation
- `/BMad/agents/architect` - System Architect for design decisions
- `/BMad/agents/sm` - Scrum Master for story drafting
- `/BMad/agents/qa` - QA Engineer for code review

**Workflow**: SM drafts stories from `docs/epics/` → Dev implements tasks in story file → QA reviews

When implementing stories as Dev agent, load:
- `docs/architecture/12-coding-standards.md`
- `docs/architecture/3-tech-stack.md`
- `docs/architecture/9-source-tree.md`
