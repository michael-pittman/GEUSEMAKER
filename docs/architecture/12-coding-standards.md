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

## 12.4 Python Specifics

```python