# 10. Infrastructure and Deployment

## 10.1 Infrastructure as Code

- **Tool:** Python + Boto3 (direct AWS API calls)
- **Location:** `geusemaker/services/` and `geusemaker/infra/`
- **Approach:** Imperative deployment via CLI commands with state tracking

GeuseMaker itself IS the infrastructure tool - it creates AWS resources directly via Boto3 rather than using Terraform or CloudFormation.

## 10.2 Package Deployment Strategy

| Method | Command | Use Case |
|--------|---------|----------|
| **PyPI Install** | `pip install geusemaker` | Production users |
| **Development** | `pip install -e ".[dev]"` | Contributors |
| **Homebrew** | `brew install geusemaker` | macOS users (future) |
| **Docker** | `docker run geusemaker deploy` | Container environments |

## 10.3 CI/CD Pipeline

**Platform:** GitHub Actions

**Pipeline Configuration:** `.github/workflows/ci.yml`

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install dependencies
        run: pip install ruff mypy
      - name: Run linters
        run: |
          ruff check geusemaker/
          mypy geusemaker/ --strict

  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install dependencies
        run: pip install -e ".[dev]"
      - name: Run tests
        run: pytest tests/unit/ -v --cov=geusemaker

  integration:
    runs-on: ubuntu-latest
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    needs: [lint, test]
    steps:
      - uses: actions/checkout@v4
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: us-east-1
      - name: Run integration tests
        run: pytest tests/integration/ -v --timeout=300

  release:
    runs-on: ubuntu-latest
    if: startsWith(github.ref, 'refs/tags/v')
    needs: [lint, test]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Build package
        run: |
          pip install build
          python -m build
      - name: Publish to PyPI
        uses: pypa/gh-action-pypi-publish@release/v1
        with:
          password: ${{ secrets.PYPI_API_TOKEN }}
```

## 10.4 Environments

| Environment | Purpose | Deployment |
|-------------|---------|------------|
| **Local Dev** | Development and testing | `pip install -e ".[dev]"` |
| **CI/CD** | Automated testing | GitHub Actions runners |
| **PyPI Staging** | Pre-release testing | TestPyPI publication |
| **PyPI Production** | Public release | PyPI publication |

## 10.5 Environment Promotion Flow

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Local     │     │   PR/CI     │     │   TestPyPI  │     │    PyPI     │
│  Development│────►│   Testing   │────►│   Staging   │────►│  Production │
│             │     │             │     │             │     │             │
│ pip install │     │ pytest      │     │ pip install │     │ pip install │
│ -e ".[dev]" │     │ ruff/mypy   │     │ --index-url │     │ geusemaker  │
└─────────────┘     └─────────────┘     │ testpypi    │     └─────────────┘
                                        └─────────────┘
                           │                   │                   │
                           ▼                   ▼                   ▼
                    All tests pass      Tag: v*-rc*         Tag: v*.*.*
```

## 10.6 Rollback Strategy

**For GeuseMaker Package:**

| Method | Trigger | Recovery |
|--------|---------|----------|
| **PyPI Rollback** | Critical bug in release | `pip install geusemaker==<previous>` |
| **Git Revert** | Bad commit merged | `git revert` + new release |
| **Yank Release** | Security vulnerability | PyPI yank + patch release |

**For Deployed AI Stacks (handled by GeuseMaker):**

| Method | Trigger | Recovery |
|--------|---------|----------|
| **Auto-Rollback** | 3 consecutive health failures | Terminate instance, restore from `last_healthy_state` |
| **Manual Rollback** | `geusemaker rollback` | User-triggered restore |
| **Spot Interruption** | AWS spot termination | Save state, preserve EFS, redeploy when ready |
| **Clean Destroy** | `geusemaker destroy` | Remove all except EFS data |

**Recovery Time Objective (RTO):**
- Auto-rollback: < 5 minutes
- Manual rollback: < 3 minutes
- Full redeploy from EFS: < 10 minutes

## 10.7 Version Strategy

```python