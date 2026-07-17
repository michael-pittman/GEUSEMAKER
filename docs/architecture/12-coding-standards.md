# 12. Coding Standards

## 12.1 Core Standards

| Category | Standard |
|----------|----------|
| **Language** | Python 3.12+ |
| **Type Checking** | Strict mypy (`--strict` flag) |
| **Linting** | Ruff (replaces flake8, isort, black) |
| **Formatting** | Ruff format (88 char line length) |
| **Test Organization** | `tests/unit/test_<module>.py`, `tests/integration/` |

## 12.2 Naming Conventions

| Element | Convention | Example |
|---------|------------|---------|
| **Classes** | PascalCase | `DeploymentState`, `EC2Service` |
| **Functions/Methods** | snake_case | `create_efs()`, `get_spot_price()` |
| **Constants** | SCREAMING_SNAKE | `MAIN_BANNER`, `EMOJI`, `STAGE_GLYPHS` |
| **Private methods** | `_prefix` | `_translate_aws_error()` |
| **Async functions** | No special prefix | `async def deploy()` |
| **Type aliases** | PascalCase | `ServiceName = Literal["n8n", "ollama", ...]` |

## 12.3 Critical Rules

These rules are **MANDATORY** for AI agents and human developers:

1. **🚫 NEVER hardcode AWS credentials** - Use `boto3.Session()` which reads from environment/config
2. **🚫 NEVER use `print()` for output** - Use `console.print()` from Rich for all user-facing output
3. **🚫 NEVER catch bare `Exception`** - Catch specific exceptions (`ClientError`, `ValidationError`)
4. **🚫 NEVER store secrets in state files** - State files are plain JSON, no passwords/keys
5. **✅ ALWAYS use Pydantic models** - No raw dicts for configuration or state
6. **✅ ALWAYS validate inputs at boundaries** - CLI arguments, user prompts, file reads
7. **✅ Use semantic UI tokens** - Branding/stage assets and the shared brutalist theme; do not rely on emoji alone
8. **✅ ALWAYS tag AWS resources** - Include `Stack: {stack_name}` tag on all resources
9. **✅ Use async for polling/monitoring** - Wrap blocking AWS calls with `asyncio.to_thread()` in monitoring, validation, and backup services
10. **💾 EFS is MANDATORY** - Every deployment MUST include EFS for data persistence

## 12.4 Service Class Pattern: BaseService vs. Facades

Two distinct service shapes coexist under `services/`; do not force one into the other.

**BaseService subclasses (own a raw boto3 client).** Any class that makes direct
boto3 API calls MUST inherit from `geusemaker.services.base.BaseService` for automatic
error wrapping (`ClientError` → `RuntimeError`) and client caching. Examples: `EC2Service`,
`EFSService`, `IAMService`, `VPCService`, `SecurityGroupService`, `ALBService`,
`CloudFrontService`, `ACMService`, `Route53Service`, `SSMService`, `SpotAutomationService`,
`InstanceResolver`, `StateRecoveryService`, and every `discovery/`, `pricing/`, and
`compute/` resource manager (`ResourceTagger`, `PreDeploymentValidator`, etc.).

**Facades (compose typed services / helpers — intentionally NOT BaseService).** These
orchestrate other services and helpers rather than owning a raw boto3 client, so they do
not subclass `BaseService`. This is deliberate and correct:

| Facade | Location | Composes |
|---|---|---|
| `DestructionService` | `services/destruction/service.py` | EC2/EFS/SG/IAM/ALB/CloudFront/ACM/Route53/Spot services |
| `UpdateOrchestrator` | `services/update/orchestrator.py` | Instance/container update collaborators |
| `RollbackService` | `services/rollback/service.py` | Destruction + state services |
| `CostEstimator` / `CostReportService` | `services/cost/` | Pricing services + state |
| `BackupService` | `services/backup/service.py` | StateManager + archive helpers |
| `HealthMonitor` | `services/monitoring/monitor.py` | `HealthCheckClient` + notifiers |
| `UserDataGenerator` | `services/userdata/generator.py` | Jinja2 templates (no AWS calls) |

**Rule:** If a facade ever starts making direct boto3 calls (owning a raw client), it
SHOULD then subclass `BaseService` to inherit error wrapping and caching. Note that
`DestructionService` keeps a couple of raw clients (`ec2`, `elbv2`) for bulk teardown calls
but remains a facade because its primary role is composing typed services; new raw-client
services should follow the BaseService pattern instead.
