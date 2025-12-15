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

## Helper Scripts

```bash
# Build runtime bundle for optimized deployments
./scripts/build_runtime_bundle.sh

# Run linting (ruff + mypy)
./scripts/lint.sh

# Run all tests
./scripts/test.sh
```

**Script details:**
- [build_runtime_bundle.sh](scripts/build_runtime_bundle.sh): Packages `runtime_assets/` into `runtime-bundle.tar.gz`
- [lint.sh](scripts/lint.sh): Runs `ruff check`, `ruff format --check`, and `mypy`
- [test.sh](scripts/test.sh): Runs `pytest` with default options

All scripts should be executed from repository root.

## Available CLI Commands

```bash
# Core deployment lifecycle
geusemaker deploy      # Deploy new infrastructure
geusemaker destroy     # Tear down deployment
geusemaker destroy --preserve-efs  # Destroy resources but keep EFS data
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

## Orchestration Tier Implementation

Each deployment tier is implemented by a specific orchestration module:

| Tier | File | Purpose | Key Features |
|------|------|---------|--------------|
| Tier 1 | [tier1.py](geusemaker/orchestration/tier1.py) | Dev/testing deployments | CPU spot instances, direct public IP, HTTPS with self-signed certs |
| Tier 2 | [tier2.py](geusemaker/orchestration/tier2.py) | Production automation | CPU instances, ALB with HTTPS listeners, ACM certificates |
| Tier 3 | (planned) | GPU-accelerated production | GPU instances, ALB + CloudFront CDN |

**Tier 1 workflow** ([orchestration/tier1.py](geusemaker/orchestration/tier1.py)):
1. Create VPC (if needed) with IGW and route tables
2. Create security group with required ports (22, 80, 5678, 2049)
3. Create EFS filesystem and wait for `available` state
4. Create EFS mount target in subnet
5. **Create IAM role and instance profile for EFS mount authentication**
6. **Wait for instance profile to be available (handles eventual consistency)**
7. Save partial state (enables rollback if EC2 launch fails)
8. Generate UserData script with embedded runtime bundle
9. Launch spot EC2 instance with UserData and IAM instance profile
10. Wait for instance to reach `running` state
11. Tag all resources with `Stack: {stack_name}`

**Adding new orchestration logic:**
- Inherit common patterns from Tier 1 implementation
- Use service classes (`EC2Service`, `EFSService`, `VPCService`, etc.)
- Always include resource tagging and state persistence
- Follow the polling pattern for AWS state transitions

**Tier 2 HTTPS Configuration** ([tier2.py:156-212](geusemaker/orchestration/tier2.py#L156-L212)):
- Supports ACM certificate integration for production HTTPS
- Creates HTTPS listener on port 443 when `enable_https=true` and `alb_certificate_arn` is provided
- Optional HTTP→HTTPS redirect when `force_https_redirect=true`
- Falls back to HTTP-only mode if no certificate provided

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
- Resource IDs (VPC, EFS, EC2, IAM, etc.)
- Cost tracking history
- Rollback records

**Partial state saving pattern** ([tier1.py:238-287](geusemaker/orchestration/tier1.py#L238-L287)):
- Save state after creating EFS and IAM resources (before EC2 launch)
- Enables cleanup/rollback if EC2 launch fails
- Allows idempotent retries of failed deployments
- State includes `status="partial"` until EC2 launch succeeds

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
from geusemaker.services import EC2Service, EFSService, IAMService, StateRecoveryService

# WRONG - Don't import from individual modules
from geusemaker.services.ec2 import EC2Service
```

**Core services**:
- `EC2Service`: EC2 instance management, AMI selection, spot instances
- `EFSService`: EFS filesystem and mount target creation, state polling
- `IAMService`: IAM roles and instance profiles for resource access
- `VPCService`: VPC, subnet, and internet gateway management
- `SecurityGroupService`: Security group creation and rule management
- `DestructionService`: Orchestrated resource cleanup and rollback

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

### Type Annotations

**Always use `Any` from typing module**, not the built-in `any` function:

```python
# WRONG - mypy error: Function "builtins.any" is not valid as a type
def process_data(config: DeploymentConfig, vpc_info: dict[str, any]) -> None:
    pass

# CORRECT - Import Any from typing
from typing import Any

def process_data(config: DeploymentConfig, vpc_info: dict[str, Any]) -> None:
    pass
```

**Common locations needing `Any` import:**
- Service methods returning dicts with mixed types
- Orchestration methods passing configuration dicts between steps
- CLI commands handling generic state objects

### Interactive Deployment Flow

The interactive deployment wizard provides comprehensive resource planning and error handling:

**Deployment Summary** ([tables.py:93-241](geusemaker/cli/components/tables.py#L93-L241)):
- Shows complete resource plan before deployment starts
- Clearly indicates which resources will be created vs. reused
- Displays estimated monthly cost if available
- Implemented via `deployment_summary_table()` function

**Cost Preview Error Handling** ([flow.py:344-373](geusemaker/cli/interactive/flow.py#L344-L373)):
- Gracefully handles cost estimation failures
- Offers user choice to continue without estimate or go back
- Prevents deployment interruption due to temporary API issues

**Spot Selection Feedback** ([spot.py:166-208](geusemaker/services/compute/spot.py#L166-L208)):
- Logs detailed reasons for spot→on-demand fallbacks
- Shows actual prices and savings percentages
- Reports stability scores for transparency

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
- `EFSService.wait_for_available()` - [efs.py:32-69](geusemaker/services/efs.py#L32-L69) - Custom polling (no boto3 waiter available)
- `EC2Service.wait_for_running()` - [ec2.py:202-209](geusemaker/services/ec2.py#L202-L209) - Uses boto3 `instance_running` waiter
- `ALBService.wait_for_healthy()` - [alb.py:216-269](geusemaker/services/alb.py#L216-L269) - Uses boto3 `target_in_service` waiter

### EC2 AMI Selection Pattern

EC2 service uses a two-tier AMI selection strategy with region-aware mappings:

```python
# 1. Deep Learning AMI lookup (for base AMI type)
# Maps to Deep Learning AMIs with Single CUDA - work on both CPU and GPU instances
EC2Service.DLAMI_BASE = {
    "us-east-1": {
        "amazon-linux-2023": {
            "x86_64": "ami-00a3a6192ba06e9ae",  # Deep Learning Base AMI with Single CUDA (30 GB)
            "arm64": "ami-0f7f69448b947f02e",
        },
        "ubuntu-22.04": {
            "x86_64": "ami-0193ca8306cf64925",
            "arm64": "ami-08f9f6bb4d8be1db8",
        },
    },
}

# 2. Pattern-based search (fallback for unmapped OS/AMI types)
# Uses describe_images with name patterns for Deep Learning AMIs
```

**AMI selection logic** ([ec2.py:97-137](geusemaker/services/ec2.py#L97-L137)):
1. Try DLAMI_BASE lookup for base AMI type (both CPU and GPU instances use same AMIs)
2. Validate AMI exists and is available via `validate_ami()`
3. Falls back to pattern-based search if:
   - No mapping exists for the region or OS type
   - AMI validation fails
   - AMI type is not "base" (pytorch, tensorflow, multi-framework)

**Benefits:**
- **Unified AMIs**: Same AMI for CPU and GPU instances (GPU drivers load only when needed)
- **Newer images**: Dec 2025 AMIs vs older Nov 2025 versions
- **Smaller size**: 30 GB vs 40 GB (saves disk space and launch time)
- **Faster deployments**: Skip describe_images API call
- **Guaranteed availability**: Validated AMIs by region
- **Graceful fallback**: Pattern search for unmapped combinations

**GPU driver behavior:**
- GPU drivers (CUDA, cuDNN, etc.) are present but dormant on CPU instances
- No performance impact on CPU-only instances (t3, c5, m5, etc.)
- Drivers automatically activate on GPU instances (p3, p4, p5, g4, g5, g6, etc.)

**Custom AMI ID override:**
Users can bypass automatic AMI selection entirely by providing a custom AMI ID:
```bash
# Use a specific AMI directly
geusemaker deploy --stack-name my-stack --ami-id ami-0123456789abcdef0

# In config file
ami_id: ami-0123456789abcdef0
```

When `ami_id` is set in DeploymentConfig, the orchestrator uses it directly and skips AMI selection logic ([tier1.py:341-351](geusemaker/orchestration/tier1.py#L341-L351)). This is useful for:
- Using custom-built AMIs with pre-installed software
- Ensuring exact AMI version for reproducible deployments
- Testing with specific AMI snapshots

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

### IAM Service Pattern

The IAM service manages roles and instance profiles for EC2 instances to access AWS resources:

**Key operations** ([iam.py](geusemaker/services/iam.py)):
```python
from geusemaker.services import IAMService

iam = IAMService(client_factory, region="us-east-1")

# Create role with EFS mount permissions
role_arn = iam.create_efs_mount_role(role_name, tags)

# Create instance profile
profile_arn = iam.create_instance_profile(profile_name, tags)

# Attach role to profile
iam.attach_role_to_profile(profile_name, role_name)

# Wait for eventual consistency (CRITICAL before EC2 launch)
iam.wait_for_instance_profile(profile_name, role_name, max_attempts=30, delay=2)
```

**IAM resources in state** ([deployment.py:149-153](geusemaker/models/deployment.py#L149-L153)):
- `iam_role_name`, `iam_role_arn`
- `iam_instance_profile_name`, `iam_instance_profile_arn`

**Best practices:**
- **Always wait for instance profile**: IAM resources are eventually consistent; use `wait_for_instance_profile()` before EC2 launch
- **Use Name for same-region profiles**: Pass instance profile Name (not ARN) for newly created profiles in same region - simpler and more reliable
- **Verify role attachment**: The wait method verifies both profile existence AND role attachment
- **Implement EC2 launch retry**: IAM and EC2 have separate propagation delays; retry EC2 launch with exponential backoff for `InvalidParameterValue` errors
- **Clean up properly**: Delete instance profile first (detaches roles automatically), then delete role (removes inline policies)

**IAM→EC2 propagation delay pattern** ([tier1.py:413-467](geusemaker/orchestration/tier1.py#L413-L467)):
```python
# Retry EC2 launch to handle IAM profile propagation delay
max_launch_attempts = 5
launch_delay = 3

for attempt in range(max_launch_attempts):
    try:
        ec2_resp = ec2_service.launch_instance(
            IamInstanceProfile={"Name": profile_name},
            ...
        )
        break  # Success
    except RuntimeError as e:
        if "InvalidParameterValue" in str(e) or "does not exist" in str(e):
            if attempt < max_launch_attempts - 1:
                console.print(f"IAM profile not yet visible to EC2, retrying...")
                time.sleep(launch_delay)
                continue
        raise  # Not a propagation error - re-raise
```

**Why this is needed:**
- `wait_for_instance_profile()` only verifies IAM readiness
- EC2 has its own cache/propagation delay (separate from IAM)
- Even after IAM confirms profile is ready, EC2 may not see it yet
- Retry pattern adds resilience without unnecessary delays when not needed

**Cleanup order** ([destruction/service.py](geusemaker/services/destruction/service.py)):
1. Terminate EC2 instance (releases instance profile)
2. Delete instance profile (automatically detaches roles)
3. Delete IAM role (automatically removes inline policies)

### NGINX Reverse Proxy Architecture

**Tier 1 (Dev) HTTPS Configuration:**
- NGINX runs on the **host system** (not in Docker), installed via apt/yum
- Uses self-signed SSL certificates for HTTPS termination
- Proxies to Docker containers via **localhost ports**, NOT container names
- HTTP (port 80) redirects to HTTPS (port 443)

**CRITICAL: Use localhost, not container names**
```nginx
# CORRECT - NGINX on host proxies to exposed container ports
location / {
    proxy_pass http://localhost:5678;  # n8n container exposes port 5678
}

# WRONG - Container names don't resolve on host system
location / {
    proxy_pass http://n8n:5678;  # ❌ Fails with "host not found" error
}
```

**Why localhost?**
- NGINX runs on host system, not inside Docker network
- Docker containers expose ports to host (0.0.0.0:5678, etc.)
- Container names only resolve within Docker's internal DNS
- Host-based services must use localhost to reach exposed ports

**Service port mappings:**
- n8n: `localhost:5678` (main application at `/`)
- Ollama: `localhost:11434` (proxied via `/api/ollama/`)
- Qdrant API: `localhost:6333` (proxied via `/qdrant/`)
- Qdrant Web UI: `localhost:6333` (built-in dashboard, proxied via `/qdrant-ui/` → `/dashboard/`)
- Crawl4AI: `localhost:11235` (proxied via `/crawl4ai/`)

**NGINX installation timing:**
- NGINX installed **AFTER** Docker services start
- Ensures containers are listening before NGINX starts proxying
- Idempotency guard: `/var/lib/geusemaker/nginx-configured`

**Configuration files:**
- Template: [nginx-ssl.conf.j2](geusemaker/services/userdata/templates/nginx-ssl.conf.j2)
- Installation: [nginx-setup.sh.j2](geusemaker/services/userdata/templates/nginx-setup.sh.j2)
- Test coverage: [test_nginx_https.py](tests/unit/test_services/test_userdata/test_nginx_https.py)

### Docker Storage Architecture

GeuseMaker uses a **split storage architecture** that separates Docker's internal storage from persistent application data:

**Architecture overview:**
1. **Docker internal storage** (`/var/lib/docker`) → **Local EBS storage**
   - Container images, layers, and overlay2 driver data
   - Requires full filesystem features (block devices, special files, etc.)
   - Stays on EC2 instance's EBS volume
   - Lost when instance terminates (acceptable for stateless containers)

2. **Application data** → **EFS persistent storage via bind mounts**
   - n8n workflows → `/mnt/efs/n8n`
   - Ollama models → `/mnt/efs/ollama`
   - Qdrant indexes → `/mnt/efs/qdrant`
   - PostgreSQL data → `/mnt/efs/postgres`
   - Defined in [docker-compose.yml](geusemaker/runtime_assets/docker-compose.yml)
   - Persists across instance termination and replacement

**Why this pattern?**
- **Avoids EFS limitations**: EFS doesn't support all filesystem features needed by Docker's overlay2 storage driver (block devices, character devices, FIFOs, etc.)
- **Optimal performance**: Local EBS for high-IOPS Docker operations, EFS for persistent data
- **Data durability**: Application data survives spot instance interruptions and instance termination
- **Clean separation**: Docker internals are ephemeral, user data is persistent

**Implementation:**
```yaml
# docker-compose.yml - bind mounts for persistent data
services:
  n8n:
    volumes:
      - /mnt/efs/n8n:/home/node/.n8n  # EFS bind mount
  ollama:
    volumes:
      - /mnt/efs/ollama:/root/.ollama  # EFS bind mount
  # Docker's /var/lib/docker stays on local EBS automatically
```

**IAM authentication for EFS mounts:**
- EC2 instances use IAM instance profiles for EFS mount authentication
- EFS mount options: `tls,iam,_netdev,addr=${EFS_MOUNT_TARGET_IP}`
- IAM role grants `elasticfilesystem:ClientMount`, `ClientWrite`, `ClientRootAccess`
- Instance profile created automatically during deployment ([tier1.py:299-336](geusemaker/orchestration/tier1.py#L299-L336))
- **Uses Name for instance profile** (simpler and more reliable for same-region deployments)
- **Verifies role attachment** before proceeding with EC2 launch to ensure profile is ready
- See [IAMService](geusemaker/services/iam.py) for implementation

**EFS mount configuration** ([efs.sh.j2](geusemaker/services/userdata/templates/efs.sh.j2)):
- Mounts EFS with `tls` (encryption in transit), `iam` (IAM authentication), `_netdev` (network dependency)
- Pins mount target IP in `/etc/hosts` to avoid DNS/DescribeMountTargets API calls
- Includes retry logic for transient network issues
- Error messages include diagnostics (mount stderr, amazon-efs-utils logs)

**Critical**: Never attempt to run Docker with `/var/lib/docker` on EFS - it will fail due to filesystem feature requirements

### UserData Generation with Jinja2 Templates

EC2 instances are provisioned using dynamically generated bash scripts from Jinja2 templates:

**Template structure** ([userdata/templates/](geusemaker/services/userdata/templates/)):
- `base.sh.j2` - System initialization, AWS CLI, package updates
- `docker.sh.j2` - Docker and Docker Compose installation
- `efs.sh.j2` - EFS mounting and persistent volume setup
- `services.sh.j2` - Application services (n8n, Ollama, Qdrant, Crawl4AI)
- `healthcheck.sh.j2` - Service health monitoring and readiness checks

**Generator pattern** ([userdata/generator.py](geusemaker/services/userdata/generator.py)):
```python
from geusemaker.services.userdata import UserDataGenerator
from geusemaker.models import UserDataConfig

generator = UserDataGenerator()
config = UserDataConfig(
    efs_id="fs-123456",
    stack_name="my-stack",
    region="us-east-1",
    use_runtime_bundle=True  # Embed runtime assets
)
script = generator.generate(config)
```

**Template rendering:**
- All templates use Jinja2 with `trim_blocks=True`, `lstrip_blocks=True`
- Variables passed via `UserDataConfig` model converted to dict
- Templates are NEVER autoscaped (bash scripts, not HTML)
- Runtime bundle embedded as base64 when `use_runtime_bundle=True`

**Cross-platform compatibility** ([base.sh.j2](geusemaker/services/userdata/templates/base.sh.j2)):
- **OS Detection**: `detect_os_family()` identifies Amazon Linux, Ubuntu, Debian
- **Package Abstraction**:
  - `pkg_install` - Works on apt-get (Debian/Ubuntu) and yum (Amazon Linux)
  - `pkg_update_once` - Updates package lists with idempotency guard
  - `with_dpkg_lock_retry` - Handles apt/dpkg lock contention on Debian
- **Performance Optimizations**:
  - Parallel downloads: apt (3 concurrent), yum (10 concurrent)
  - Lock retry logic for Debian/Ubuntu to avoid cloud-init conflicts
- **User Detection**: `get_primary_user()` handles ec2-user vs ubuntu
- **Platform-tested**: Scripts work on Amazon Linux 2023, Ubuntu 22.04, Debian

**Critical**: Templates generate bash scripts - NEVER use autoescaping (`autoescape=False`)

### Runtime Bundle Optimization

Runtime bundles pre-package deployment assets to reduce EC2 initialization time:

**Bundle contents** ([runtime_assets/](geusemaker/runtime_assets/)):
```
runtime_assets/
├── docker-compose.yml        # Service stack definition
├── runtime.env.example       # Environment template
├── bin/                      # Optional pre-compiled binaries
├── efs-utils/                # Optional amazon-efs-utils packages
└── images/                   # Optional preloaded Docker images
```

**Building bundles:**
```bash
# Add optional artifacts to runtime_assets/
cp my-docker-image.tar geusemaker/runtime_assets/images/

# Build bundle
./scripts/build_runtime_bundle.sh

# Outputs: runtime-bundle.tar.gz (embedded in UserData as base64)
```

**Deployment with bundles:**
```bash
# CLI flag
geusemaker deploy --use-runtime-bundle

# Config file
use_runtime_bundle: true
```

**How bundles work:**
1. `build_runtime_bundle.sh` creates `runtime-bundle.tar.gz`
2. Bundle is base64-encoded and embedded in UserData script
3. EC2 instance decodes and extracts bundle on first boot
4. Docker images/binaries available immediately without downloads

**Benefits:**
- Faster EC2 initialization (no downloads)
- Consistent deployments (versioned artifacts)
- Works in air-gapped/restricted network environments

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
- `--ami-id`: Use custom AMI ID (overrides os-type, architecture, ami-type)
- `--vpc-id` + `--attach-internet-gateway`: Reuse VPC and add IGW/routes
- `--security-group-id`: Reuse SG (must have ports 22, 80, 5678, 2049)
- `--skip-validation`: Bypass pre-deployment checks

**Config file format** (YAML or JSON):
```yaml
# deployment.yaml
stack_name: my-production-stack
region: us-west-2
tier: 1

# Instance configuration
instance_type: t3.large
os_type: amazon-linux-2023
ami_type: base
ami_id: ami-0123456789abcdef0  # Optional: use custom AMI (overrides os_type/ami_type)

# Network configuration (optional - will be created if omitted)
vpc_id: vpc-123456
subnet_id: subnet-789012
security_group_id: sg-345678

# EFS configuration
efs_performance_mode: generalPurpose

# Optimization
use_runtime_bundle: true      # Embed pre-packaged assets
attach_internet_gateway: true # Add IGW to existing VPC

# Service configuration
services:
  n8n:
    enabled: true
    version: latest
  ollama:
    enabled: true
    models: ["llama2", "codellama"]
  qdrant:
    enabled: true
  crawl4ai:
    enabled: false
```

**Config validation:**
- All configs validated with Pydantic models before deployment
- CLI flags override config file values when provided
- Use `geusemaker validate --config deployment.yaml` to test

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

### Logging and Monitoring Infrastructure

GeuseMaker provides comprehensive logging across all deployment phases:

**Log file locations on EC2 instances:**

| Log File | Path | Purpose | Access Method |
|----------|------|---------|---------------|
| UserData initialization | `/var/log/geusemaker-userdata.log` | Main initialization script (system setup, Docker, services) | `geusemaker logs <stack> [--follow]` |
| Model preloading | `/var/log/geusemaker/model-preload.log` | Ollama model downloads (background process) | SSH only: `tail -f /var/log/geusemaker/model-preload.log` |
| EFS mount | `/var/log/amazon/efs/mount.log` | EFS mount diagnostics and errors | SSH: `cat /var/log/amazon/efs/mount.log` |
| Cloud-init (fallback) | `/var/log/cloud-init-output.log` | AWS cloud-init system logs | Auto-fallback if userdata log unavailable |
| Docker containers | Runtime only | Individual service logs (n8n, ollama, qdrant, crawl4ai, postgres) | `geusemaker logs <stack> --service <name>` |

**CLI logging commands:**

```bash
# View UserData initialization logs
geusemaker logs my-stack                    # Last 100 lines (default)
geusemaker logs my-stack --follow           # Stream in real-time (Ctrl+C to stop)

# View Docker container logs
geusemaker logs my-stack --service n8n --tail 200
geusemaker logs my-stack --service ollama --tail 500
geusemaker logs my-stack --service qdrant
geusemaker logs my-stack --service crawl4ai
geusemaker logs my-stack --service postgres

# Available services: userdata, n8n, ollama, qdrant, crawl4ai, postgres
```

**Direct server log streaming (SSH access):**

```bash
# Get public IP
PUBLIC_IP=$(geusemaker status my-stack --output json | jq -r '.data.instance.public_ip')

# SSH to instance
ssh -i ~/.ssh/key-pair.pem ec2-user@$PUBLIC_IP

# Stream logs in real-time
tail -f /var/log/geusemaker-userdata.log           # UserData initialization
tail -f /var/log/geusemaker/model-preload.log      # Ollama model downloads
docker logs -f n8n                                  # n8n workflow engine
docker logs -f ollama                               # Ollama LLM service
docker logs -f qdrant                               # Qdrant vector database
docker logs -f crawl4ai                             # Crawl4AI web scraper
docker logs -f postgres                             # PostgreSQL database

# View multiple logs simultaneously
tail -f /var/log/geusemaker-userdata.log \
         /var/log/geusemaker/model-preload.log
```

**Log streaming implementation** ([ssm.py:212-259](geusemaker/services/ssm.py#L212-L259)):
- Real-time log streaming via AWS Systems Manager (SSM)
- Polls log file every 2 seconds for new lines
- Stops when initialization completes or error detected
- Returns generator for memory-efficient streaming

**Monitoring commands:**

```bash
# Check deployment status and service health
geusemaker status my-stack                  # Rich UI with tables
geusemaker status my-stack --output json    # JSON for parsing/automation

# Health check endpoints (HTTP):
# - n8n: http://<ip>:5678/healthz
# - Qdrant: http://<ip>:6333/health
# - Ollama: http://<ip>:11434/api/tags
# - Crawl4AI: http://<ip>:11235/health
# - PostgreSQL: TCP port 5432 check only
```

**Service health checking** ([status.py:84-127](geusemaker/cli/commands/status.py#L84-L127)):
- Performs HTTP health checks for n8n, Qdrant, Ollama, Crawl4AI
- TCP port check for PostgreSQL (no HTTP endpoint)
- Returns: `healthy`, `unhealthy`, `unreachable`, or `unavailable` (instance not running)

**Log command implementation** ([logs.py](geusemaker/cli/commands/logs.py)):
- `_stream_userdata_logs()` - Real-time streaming with SSM ([logs.py:124-136](geusemaker/cli/commands/logs.py#L124-L136))
- `_fetch_userdata_logs()` - One-time fetch ([logs.py:138-164](geusemaker/cli/commands/logs.py#L138-L164))
- `_fetch_container_logs()` - Docker logs via SSM ([logs.py:166-221](geusemaker/cli/commands/logs.py#L166-L221))

**Model preloading logs** ([ollama-models.sh.j2](geusemaker/services/userdata/templates/ollama-models.sh.j2)):
- Background process that runs after healthcheck completes
- Logs to `/var/log/geusemaker/model-preload.log` with timestamps
- Preloads: `qwen2.5:1.5b-instruct` (lightweight LLM), `znbang/bge:small-en-v1.5` (embeddings, with `nomic-embed-text` fallback)
- GPU deployments also preload: `qwen3-omni-30b-a3b:q4_k_s` or fallback `qwen2.5-omni-7b`
- Includes usage examples and model listing commands in log output

**Troubleshooting with logs:**

```bash
# Deployment stuck or failed
geusemaker logs my-stack --follow                    # Watch initialization
geusemaker logs my-stack | grep -i error             # Search for errors

# Services not starting
geusemaker status my-stack                           # Check health
geusemaker logs my-stack --service ollama --tail 500 # Container logs

# Model downloads slow/failed
ssh -i ~/.ssh/key.pem ec2-user@<ip>
tail -f /var/log/geusemaker/model-preload.log        # Monitor downloads

# EFS mount issues
ssh -i ~/.ssh/key.pem ec2-user@<ip>
cat /var/log/amazon/efs/mount.log                    # EFS diagnostics
df -h | grep efs                                      # Verify mount
```

**SSM Agent requirements:**
- AWS Systems Manager (SSM) agent must be running on EC2 instance (pre-installed in Deep Learning AMIs)
- Instance must have IAM role with `AmazonSSMManagedInstanceCore` policy
- Log commands use `SendCommand` API to execute shell scripts remotely
- 60-second timeout for SSM agent readiness checks

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

**Reference test examples:**
- IAM service tests ([test_iam.py](tests/unit/test_services/test_iam.py)): Full lifecycle testing including eventual consistency
- EFS service tests: State polling and error handling patterns
- Destruction service tests: Stub services and cleanup verification

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
