# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**GeuseMaker** is an AI infrastructure deployment platform that provisions and manages a complete AI application stack on AWS. The system enables users to deploy workflow automation (n8n), LLM inference (Ollama), vector databases (Qdrant), and web scraping services (Crawl4AI) through a CLI with intelligent cost optimization using spot instances.

**Status**: Active development with core deployment features implemented

## Common Commands

```bash
# Setup (requires Python 3.12+)
python3.12 -m venv venv && source venv/bin/activate && pip install -e ".[dev]"

# Lint and Test
./scripts/lint.sh              # ruff check + format + mypy
./scripts/test.sh              # Run all tests
pytest tests/unit/test_<module>.py::test_function_name -v  # Single test
pytest --cov=geusemaker --cov-report=term-missing           # With coverage

# Build runtime bundle
./scripts/build_runtime_bundle.sh
```

## CLI Commands Reference

```bash
# Deployment lifecycle
geusemaker deploy [--config deployment.yaml] [--skip-validation]
geusemaker destroy [--preserve-efs]
geusemaker update | rollback

# Monitoring
geusemaker status <stack> [--output json]
geusemaker logs <stack> [--follow] [--service <name>]
geusemaker health | monitor | inspect

# Management
geusemaker list [--discover-from-aws]  # State recovery from AWS
geusemaker cost | validate | report
geusemaker cleanup | backup | restore | init | info
```

**Verbosity**: `--silent`, `--verbose` (-v), or default (emojis)
**Output**: Always use `console.print()` from `geusemaker.cli`, NEVER `print()`

## MCP Tools

**aws-documentation**: Search AWS docs, read pages, get recommendations
**aws-pricing**: Get real-time pricing, generate cost reports, compare regions

## Tech Stack

| Category | Technology | Purpose |
|----------|------------|---------|
| Language | Python 3.12+ | Primary development |
| AWS SDK | Boto3 1.35+ | AWS API integration |
| CLI | Click 8.1+ / Rich 13.9+ / questionary 2.0+ | Interface |
| Validation | Pydantic 2.9+ | Config/state models |
| Testing | pytest 8.3+ / moto 5.0.25 | Test framework/mocking |
| Code Quality | Ruff 0.5+ / mypy 1.11+ | Linting/type checking |

## Project Structure

```
geusemaker/
├── geusemaker/           # Main Python package
│   ├── cli/              # Click CLI + Rich UI
│   ├── orchestration/    # Deployment workflows (tier1, tier2, tier3)
│   ├── services/         # AWS resource managers
│   ├── models/           # Pydantic models
│   ├── infra/            # Boto3 clients, state persistence
│   └── utils/            # Async helpers, retry logic
└── tests/                # Unit and integration tests
```

## Critical Coding Rules (MANDATORY)

1. **NEVER hardcode AWS credentials** - Use `boto3.Session()`
2. **NEVER use `print()`** - Use `console.print()` from Rich
3. **NEVER catch bare `Exception`** - Catch specific exceptions
4. **NEVER store secrets in state files** - Plain JSON only
5. **ALWAYS use Pydantic models** - No raw dicts
6. **ALWAYS validate inputs** - CLI args, user prompts, file reads
7. **ALWAYS include emojis** - Use `EMOJI` dict from branding.py
8. **ALWAYS tag AWS resources** - `Stack: {stack_name}` on all
9. **ALWAYS use async for AWS calls** - Wrap with `asyncio.to_thread()`
10. **EFS is MANDATORY** - Every deployment needs EFS for persistence

## Naming Conventions

- Classes: `PascalCase` (`DeploymentState`, `EC2Service`)
- Functions/Methods: `snake_case` (`create_efs()`, `get_spot_price()`)
- Constants: `SCREAMING_SNAKE` (`MAIN_BANNER`, `EMOJI`)
- Private methods: `_prefix` (`_translate_aws_error()`)

## Architecture Key Points

- **Layered Monolith**: CLI → Orchestration → Services → Infrastructure
- **EFS Always Required**: All deployments use EFS for persistent storage (n8n workflows, Ollama models, Qdrant indexes, PostgreSQL data)
- **Three Deployment Tiers**:
  - Tier 1 (Dev): CPU spot instances, direct public IP, self-signed HTTPS
  - Tier 2 (Automation): CPU with ALB, ACM certificates, HTTPS
  - Tier 3 (GPU): GPU instances with ALB + CloudFront CDN

## Orchestration Workflow

**Tier 1** ([tier1.py](geusemaker/orchestration/tier1.py)): VPC → SG → EFS → IAM → EC2 (spot)
**Tier 2** ([tier2.py](geusemaker/orchestration/tier2.py)): + ALB with HTTPS listeners

**Key patterns**:
- Save partial state after EFS/IAM (before EC2) for rollback
- Wait for AWS state transitions (EFS available, EC2 running, IAM propagation)
- Tag all resources with `Stack: {stack_name}`
- Follow service class pattern for all AWS operations

## State Management

**Location**: `~/.geusemaker/<stack_name>.json` (version 2)
**Contains**: Config, resource IDs, cost tracking, rollback records
**Usage**: Always use `StateManager` to load/save state
**Critical**: NEVER store secrets in state files (plain JSON)

## Import Patterns

```python
# Models - Import from central barrel
from geusemaker.models import DeploymentConfig, DeploymentState, VPCInfo

# Services - Import from central barrel
from geusemaker.services import EC2Service, EFSService, IAMService
```

**Core services**: EC2Service, EFSService, IAMService, VPCService, SecurityGroupService, DestructionService, StateRecoveryService

## Implementation Patterns

### BaseService Pattern

All AWS service classes inherit from `BaseService`:

```python
from geusemaker.services.base import BaseService

class MyService(BaseService):
    def __init__(self, client_factory: AWSClientFactory, region: str = "us-east-1"):
        super().__init__(client_factory, region)
        self._client = self._client("service-name")

    def operation(self, param: str) -> dict[str, Any]:
        return self._safe_call(lambda: self._client.api_call(Param=param))
```

**Benefits**: Auto error wrapping (ClientError→RuntimeError), client caching

### AWS State Polling

```python
def wait_for_available(self, resource_id: str, max_attempts: int = 60, delay: int = 5) -> None:
    """Poll describe_* API until resource reaches target state."""
    for attempt in range(max_attempts):
        state = self._client.describe_resource(ResourceId=resource_id)["State"]
        if state == "available": return
        if state in ("error", "deleted"): raise RuntimeError(f"Invalid state: {state}")
        if attempt < max_attempts - 1: time.sleep(delay)
    raise RuntimeError(f"Timeout after {max_attempts * delay}s")
```

**Critical transitions**: EFS (creating→available), EC2 (pending→running), ALB (registering→healthy)

### Type Annotations

```python
from typing import Any  # Import from typing, NOT builtins.any

def process(config: DeploymentConfig, vpc_info: dict[str, Any]) -> None: pass
```

### Lambda Closure Capture

```python
# Capture loop variables before lambda to avoid mypy errors
for service_code, quota_code in quotas:
    _sc, _qc = service_code, quota_code
    result = self._safe_call(lambda: client.get_quota(ServiceCode=_sc))
```

### CLI Styling (questionary)

```python
# Convert dict to Style object (NOT dict directly)
style = questionary.Style.from_dict({"separator": "#888888"})  # Use hex, not Rich colors
result = questionary.select(prompt, choices=choices, style=style).ask()
```

### EC2 AMI Selection

**Strategy**: DLAMI_BASE lookup → validate → fallback to pattern search
**AMIs**: Deep Learning Base AMI with Single CUDA (works on CPU and GPU)
**Custom override**: Use `--ami-id` or `ami_id` in config to bypass auto-selection

### IAM Service Pattern

**IAM→EC2 propagation delay**: Retry EC2 launch 5 times with 3s delay for `InvalidParameterValue`

```python
iam.create_efs_mount_role(role_name, tags)
iam.create_instance_profile(profile_name, tags)
iam.attach_role_to_profile(profile_name, role_name)
iam.wait_for_instance_profile(profile_name, role_name)  # CRITICAL before EC2 launch

# EC2 launch with retry
for attempt in range(5):
    try:
        ec2.launch_instance(IamInstanceProfile={"Name": profile_name}, ...)
        break
    except RuntimeError as e:
        if "InvalidParameterValue" in str(e) and attempt < 4:
            time.sleep(3)
            continue
        raise
```

**Cleanup order**: EC2 → instance profile → IAM role

### Network Interface Management

- Tag ENIs during EC2 launch: `ResourceType: "network-interface"`
- Clean up orphaned ENIs BEFORE VPC deletion in destruction service

### NGINX Reverse Proxy

**Critical**: NGINX on host system proxies to `localhost` ports, NOT container names

```nginx
# CORRECT
proxy_pass http://localhost:5678;  # n8n exposed port

# WRONG
proxy_pass http://n8n:5678;  # Container name doesn't resolve on host
```

**Service mappings**: n8n (5678), Ollama (11434), Qdrant (6333), Crawl4AI (11235), PostgreSQL (5432)

**n8n container connections**: Use `http://ollama:11434` (container name) inside n8n workflows

### Docker Storage Architecture

**Split architecture**:
- `/var/lib/docker` → Local EBS (images, layers, ephemeral)
- `/mnt/efs/*` → EFS bind mounts (persistent data: n8n, ollama, qdrant, postgres)

**Why**: EFS doesn't support all filesystem features for Docker's overlay2 driver
**Critical**: NEVER run Docker with `/var/lib/docker` on EFS

**EFS mount**: IAM authentication with `tls,iam,_netdev` options, pinned mount target IP in `/etc/hosts`

### UserData Generation

**Templates** ([userdata/templates/](geusemaker/services/userdata/templates/)): base.sh.j2, docker.sh.j2, efs.sh.j2, services.sh.j2, healthcheck.sh.j2

**Generator**:
```python
from geusemaker.services.userdata import UserDataGenerator
script = UserDataGenerator().generate(UserDataConfig(efs_id, stack_name, region, use_runtime_bundle=True))
```

**Cross-platform**: Supports Amazon Linux 2023, Ubuntu 22.04, Debian (OS detection, package abstraction)
**Critical**: Templates NEVER use autoescaping (bash scripts, not HTML)

### Runtime Bundle Optimization

**Contents**: docker-compose.yml, runtime.env.example, optional binaries/images
**Build**: `./scripts/build_runtime_bundle.sh` → base64 embedded in UserData
**Deploy**: `--use-runtime-bundle` flag or `use_runtime_bundle: true` in config
**Benefit**: Faster EC2 init (no downloads), works in air-gapped environments

### CLI Deployment Modes

1. **Interactive**: `geusemaker deploy` (guided wizard)
2. **Non-interactive**: `geusemaker deploy --no-interactive --vpc-id vpc-123 --subnet-id subnet-456`
3. **Config file**: `geusemaker deploy --config deployment.yaml` (YAML/JSON)

**Key flags**: `--ami-id`, `--vpc-id + --attach-internet-gateway`, `--security-group-id`, `--skip-validation`

See [README.md](README.md) for full deployment modes and config format.

### State Recovery from AWS

```bash
geusemaker list --discover-from-aws [--region us-west-2]
```

Scans EC2 instances with `Stack` tag, reconstructs state from metadata, saves to `~/.geusemaker/`

### Logging and Monitoring

**Log locations on EC2**:
- UserData: `/var/log/geusemaker-userdata.log` (`geusemaker logs <stack> [--follow]`)
- Model preload: `/var/log/geusemaker/model-preload.log` (SSH only)
- EFS mount: `/var/log/amazon/efs/mount.log` (SSH only)
- Containers: `geusemaker logs <stack> --service <name> --tail 200`

**Services**: userdata, n8n, ollama, qdrant, crawl4ai, postgres

**Health checks**: `geusemaker status <stack>` (HTTP health for n8n/Qdrant/Ollama/Crawl4AI, TCP for PostgreSQL)

**Implementation**: SSM-based log streaming ([ssm.py:212-259](geusemaker/services/ssm.py#L212-L259)), polls every 2s

**Requirements**: SSM agent running, IAM role with `AmazonSSMManagedInstanceCore`

### Testing Patterns

**Service tests** (moto):
```python
from moto import mock_aws

@mock_aws
def test_service_method() -> None:
    svc = SomeService(AWSClientFactory(), region="us-east-1")
    result = svc.method(param="value")
    assert result["Key"] == "expected"
```

**Orchestration tests**: Use stub services (not moto), track state, test logic not AWS APIs

**Test organization**:
- Unit tests: `@mock_aws`, zero delays (`delay=0`)
- Integration tests: Real AWS, manual only
- Stubs: Minimal valid responses, update when adding new AWS calls

## Key Documents

- **PRD**: `docs/prd.md` (sharded in `docs/prd/`)
- **Architecture**: `docs/architecture.md` (sharded in `docs/architecture/`)
- **Stories**: `docs/stories/` - Implementation stories
- **Epics**: `docs/epics/` - Feature epics

## BMAD Development Methodology

Specialized agents via slash commands:
- `/BMad/agents/dev` - Full Stack Developer (James)
- `/BMad/agents/architect` - System Architect
- `/BMad/agents/sm` - Scrum Master
- `/BMad/agents/qa` - QA Engineer

**Workflow**: SM drafts stories → Dev implements → QA reviews

**Dev agent**: Load `docs/architecture/12-coding-standards.md`, `docs/architecture/3-tech-stack.md`, `docs/architecture/9-source-tree.md`
