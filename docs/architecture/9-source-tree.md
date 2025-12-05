# 9. Source Tree

The project follows a **monorepo structure** with clear separation between CLI, services, orchestration, and infrastructure layers.

```
geusemaker/
├── 📁 geusemaker/                     # Main Python package
│   ├── __init__.py                    # Package init with version
│   ├── __main__.py                    # Entry point: python -m geusemaker
│   │
│   ├── 📁 cli/                        # 🖥️ CLI Layer
│   │   ├── __init__.py
│   │   ├── main.py                    # Click CLI entry point
│   │   ├── branding.py                # 🎨 ASCII art, banners, emojis
│   │   ├── ui.py                      # Rich UI components (tables, progress, panels)
│   │   ├── interactive.py             # Interactive mode menus
│   │   └── commands/                  # CLI subcommands
│   │       ├── __init__.py
│   │       ├── deploy.py              # 🚀 geusemaker deploy
│   │       ├── destroy.py             # 💥 geusemaker destroy
│   │       ├── status.py              # 💚 geusemaker status
│   │       ├── logs.py                # 📋 geusemaker logs
│   │       ├── cost.py                # 💰 geusemaker cost
│   │       └── rollback.py            # ⏪ geusemaker rollback
│   │
│   ├── 📁 orchestration/              # ⚙️ Orchestration Layer
│   │   ├── __init__.py
│   │   ├── base.py                    # BaseOrchestrator abstract class
│   │   ├── spot.py                    # SpotOrchestrator (Tier 1 - Dev)
│   │   ├── alb.py                     # ALBOrchestrator (Tier 2 - Automation)
│   │   ├── cdn.py                     # CDNOrchestrator (Tier 3 - GPU)
│   │   └── factory.py                 # Orchestrator factory function
│   │
│   ├── 📁 services/                   # 🛠️ Service Layer (AWS Operations)
│   │   ├── __init__.py
│   │   ├── base.py                    # BaseService with retry logic
│   │   ├── ec2.py                     # 🖥️ EC2Service (launch, terminate, describe)
│   │   ├── efs.py                     # 💾 EFSService (create, mount, wait)
│   │   ├── vpc.py                     # 🌐 VPCService (discover, create, subnets)
│   │   ├── sg.py                      # 🛡️ SecurityGroupService (create, rules)
│   │   ├── alb.py                     # ⚖️ ALBService (create, targets, listeners)
│   │   ├── cloudfront.py              # 🌍 CloudFrontService (distributions)
│   │   ├── ssm.py                     # 📋 SSMService (commands, log streaming)
│   │   ├── pricing.py                 # 💰 PricingService (spot/on-demand prices)
│   │   └── health.py                  # 💚 HealthService (service health checks)
│   │
│   ├── 📁 models/                     # 📐 Pydantic Models (Data Layer)
│   │   ├── __init__.py                # Export all models
│   │   ├── deployment.py              # DeploymentState, DeploymentConfig
│   │   ├── resources.py               # VPCSpec, EFSSpec, EC2Spec, etc.
│   │   ├── health.py                  # ServiceHealth, HealthCheckResult
│   │   ├── cost.py                    # CostTracking, PricingData
│   │   └── settings.py                # UserSettings, UIPreferences
│   │
│   ├── 📁 infra/                      # 🏗️ Infrastructure Layer
│   │   ├── __init__.py
│   │   ├── clients.py                 # AWSClientFactory (cached Boto3 clients)
│   │   ├── state.py                   # StateManager (JSON persistence)
│   │   ├── userdata.py                # UserDataGenerator (EC2 bootstrap scripts)
│   │   ├── cache.py                   # CacheManager (pricing, VPC cache)
│   │   └── config.py                  # ConfigManager (env vars, defaults)
│   │
│   └── 📁 utils/                      # 🔧 Utilities
│       ├── __init__.py
│       ├── async_utils.py             # Async helpers, gather with errors
│       ├── retry.py                   # Retry decorators with backoff
│       ├── validators.py              # Input validation helpers
│       └── formatters.py              # Cost/time/size formatters
│
├── 📁 tests/                          # 🧪 Test Suite
│   ├── __init__.py
│   ├── conftest.py                    # Pytest fixtures
│   ├── 📁 unit/                       # Unit tests (mocked AWS)
│   │   ├── test_cli/
│   │   │   ├── test_branding.py
│   │   │   ├── test_ui.py
│   │   │   └── test_commands.py
│   │   ├── test_services/
│   │   │   ├── test_ec2.py
│   │   │   ├── test_efs.py
│   │   │   ├── test_vpc.py
│   │   │   └── test_health.py
│   │   ├── test_orchestration/
│   │   │   ├── test_spot_orchestrator.py
│   │   │   └── test_alb_orchestrator.py
│   │   └── test_models/
│   │       ├── test_deployment.py
│   │       └── test_validation.py
│   ├── 📁 integration/                # Integration tests (real AWS)
│   │   ├── test_vpc_discovery.py
│   │   ├── test_efs_lifecycle.py
│   │   └── test_full_deployment.py
│   └── 📁 fixtures/                   # Test data
│       ├── sample_state.json
│       └── mock_aws_responses/
│
├── 📁 config/                         # 📋 Configuration Files
│   ├── ai-stack.yml                   # Docker Compose for AI services
│   ├── defaults.yml                   # Default configuration values
│   └── logging.yml                    # Logging configuration
│
├── 📁 scripts/                        # 🔧 Development Scripts
│   ├── install-dev.sh                 # Install dev dependencies
│   ├── lint.sh                        # Run linters (ruff, mypy)
│   ├── test.sh                        # Run test suite
│   └── release.sh                     # Build and publish package
│
├── 📁 docs/                           # 📚 Documentation
│   ├── architecture.md                # This document
│   ├── getting-started/
│   │   └── quick-start.md
│   └── api/
│       └── services.md
│
├── 📄 pyproject.toml                  # Python project config (Poetry/setuptools)
├── 📄 Makefile                        # Convenience targets
├── 📄 README.md                       # Project README
├── 📄 LICENSE                         # MIT License
└── 📄 .gitignore                      # Git ignore patterns
```

## 9.1 Key Files Explained

| File | Purpose | Emoji |
|------|---------|-------|
| `cli/branding.py` | ASCII art banners, stage visuals, emoji constants | 🎨 |
| `cli/ui.py` | Rich UI components: progress bars, tables, panels | 🖥️ |
| `cli/main.py` | Click CLI entry point with commands | 🚀 |
| `orchestration/spot.py` | Tier 1 deployment workflow with visual feedback | ⚙️ |
| `services/efs.py` | EFS creation and mounting (ALWAYS required) | 💾 |
| `services/health.py` | Service health checks with thresholds | 💚 |
| `models/deployment.py` | Pydantic models for state management | 📐 |
| `infra/state.py` | JSON state persistence to ~/.geusemaker/ | 💾 |
| `infra/userdata.py` | EC2 user-data script generation | 🏗️ |
| `config/ai-stack.yml` | Docker Compose for n8n, Ollama, Qdrant, etc. | 🐳 |

## 9.2 Import Structure

```python