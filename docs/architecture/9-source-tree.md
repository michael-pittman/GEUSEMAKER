# 9. Source Tree

GeuseMaker is a Python monorepo. The package is layered so presentation code depends
on orchestration and services, while service and orchestration modules remain independent
of the optional Textual UI.

```text
GEUSEMAKER/
├── geusemaker/
│   ├── cli/
│   │   ├── commands/          # Click command implementations
│   │   ├── components/        # Dialogs, tables, messages, stages, theme
│   │   ├── display/           # Rich renderers for domain results
│   │   ├── interactive/       # Quick/advanced deployment wizard and runner
│   │   ├── output/            # Text/JSON/YAML and verbosity contracts
│   │   ├── tui/               # Optional lazy-loaded Textual shell
│   │   ├── branding.py        # Product marks and stage glyphs
│   │   ├── main.py            # Root Click application
│   │   └── progress_events.py # UI-neutral progress contract
│   ├── config/                # YAML/JSON/env configuration loading
│   ├── infra/
│   │   ├── clients.py         # AWS client factory
│   │   ├── migrations/        # State schema migrations
│   │   └── state.py           # Locked local deployment state
│   ├── models/                # Pydantic domain and state models
│   ├── orchestration/         # Tier 1/2/3 deployment workflows
│   ├── runtime_assets/        # Docker Compose and bootstrap assets
│   ├── services/
│   │   ├── backup/            # Backup operations
│   │   ├── cleanup/           # Orphan discovery and cleanup
│   │   ├── compute/           # Spot selection and recommendation policies
│   │   ├── cost/              # Estimates, budgets, reports, tags
│   │   ├── destruction/       # Resource destruction
│   │   ├── discovery/         # Existing AWS resource discovery
│   │   ├── health/            # Service health clients
│   │   ├── monitoring/        # Continuous monitoring and notifications
│   │   ├── pricing/           # AWS price adapters and cache
│   │   ├── rollback/          # Rollback operations
│   │   ├── selection/         # Resource-selection flow
│   │   ├── update/            # Instance/container updates
│   │   ├── userdata/          # EC2 bootstrap generation
│   │   └── validation/        # Pre/post-deployment checks
│   └── utils/                 # Small shared utilities
├── tests/                     # Unit tests mirroring package boundaries
├── config/                    # Version-controlled configuration examples
├── docs/
│   ├── architecture/          # Canonical sectioned architecture
│   ├── prd/                   # Canonical sectioned PRD
│   ├── epics/                 # Feature delivery records
│   ├── stories/               # Story acceptance and implementation records
│   └── analysis/              # Focused technical reviews
├── scripts/                   # Development and operator maintenance scripts
├── Workflows/                 # Importable n8n workflows and guides
├── pyproject.toml             # Package, dependency, and tool configuration
├── README.md                  # User entry point
└── CLAUDE.md                  # Repository guidance for coding agents
```

## 9.1 Ownership boundaries

| Area | Responsibility | Must not contain |
|---|---|---|
| `cli/` | User interaction and rendering | AWS resource business logic |
| `orchestration/` | Deployment ordering and rollback coordination | Textual or questionary imports |
| `services/` | AWS/domain operations | Textual or questionary imports |
| `infra/` | AWS clients and state persistence | Command-specific presentation |
| `models/` | Validated immutable data contracts | Network calls |
| `runtime_assets/` | Files shipped to deployed instances | Developer-only cache files |

## 9.2 Important entry points

| File | Purpose |
|---|---|
| `geusemaker/__main__.py` | Supports `python -m geusemaker` |
| `geusemaker/cli/main.py` | Registers the `geusemaker` command tree |
| `geusemaker/cli/commands/deploy.py` | Wizard, config, automation, and TUI deploy entry |
| `geusemaker/cli/interactive/flow.py` | Quick/advanced configuration flow |
| `geusemaker/cli/interactive/runner.py` | Validation and orchestrator dispatch |
| `geusemaker/models/deployment.py` | Deployment configuration and state |
| `geusemaker/infra/state.py` | Persistent state API |
| `geusemaker/orchestration/tier1.py` | Base deployment workflow |
| `geusemaker/orchestration/tier2.py` | ALB topology |
| `geusemaker/orchestration/tier3.py` | CloudFront topology |

## 9.3 Import direction

```text
CLI / TUI
    ↓
Orchestration
    ↓
Services
    ↓
Infrastructure clients

Models are shared contracts used by every layer.
```

The Textual dependency is optional and must only be imported lazily from `cli/tui/`.
Machine-readable command paths must continue to work without the `[tui]` extra.

## 9.4 Repository hygiene

- Generated caches, coverage data, virtual environments, build output, logs, and OS
  metadata are ignored by Git.
- `Junk/` is a local scratch area and is never part of the product source tree.
- Keep stack-specific operational designs in `docs/` and reusable workflow artifacts in
  `Workflows/`.
- Avoid moving public modules solely for aesthetics; stable imports are more valuable than
  a large mechanical reorganization.
