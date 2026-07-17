# 3. Tech Stack

**IMPORTANT**: This table is the **single source of truth** for all technology choices. All other documents must reference these selections.

## 3.1 Cloud Infrastructure

- **Provider:** AWS
- **Key Services:** EC2 (Spot/On-Demand), VPC, EFS, ALB, CloudFront, Security Groups, SSM
- **Deployment Regions:** User-selected (default: us-east-1)

## 3.2 Technology Stack Table

| Category | Technology | Version | Purpose | Rationale |
|----------|------------|---------|---------|-----------|
| **Language** | Python | 3.12+ | Primary development language | Latest stable, pattern matching, performance improvements |
| **AWS SDK** | Boto3 | 1.35+ | AWS API integration | Native AWS support, comprehensive service coverage |
| **CLI Framework** | Click | 8.1+ | Command-line interface | Decorator-based, groups, lazy loading, excellent DX |
| **Wizard UI** | Rich + Questionary | Rich 14.2–15.x; Questionary 2.1+ | Default guided, scrollback-friendly shell | Available in the base install; preserves CI and machine-output behavior |
| **Full-screen TUI** | Textual | 8.2–8.x (optional `[tui]`) | Opt-in deploy, monitor, inspect, and logs hub | Shares domain services and progress events without adding Textual to the base install |
| **Validation** | Pydantic | 2.9+ | Config validation, settings | V2 performance, ConfigDict, Field validators |
| **HTTP Client** | httpx | 0.27+ | Health checks, API calls | Async support, modern API, type hints |
| **Testing** | pytest | 8.3+ | Unit and integration tests | Industry standard, fixtures, parameterization |
| **Mocking** | moto | 5.0.25 | AWS service mocking | Pinned version for stable AWS mock coverage |
| **Linting** | Ruff | 0.5+ | Code quality | Fast, replaces flake8/isort/black |
| **Type Checking** | mypy | 1.11+ | Static type analysis | Strict mode for reliability |
| **Build Backend** | hatchling | - | Packaging | `python3.12 -m venv` + `pip install -e` for setup |
| **Container Runtime** | Docker | 24+ | AI service deployment | Standard container platform |
| **Compose** | Docker Compose | 2.29+ | Multi-container orchestration | Service definitions, health checks |

## 3.3 AI Stack Services (Deployed on EC2)

| Service | Image | Port | Persistent Storage | Purpose |
|---------|-------|------|-------------------|---------|
| **n8n** | n8nio/n8n:latest | 5678 | /mnt/efs/n8n | Workflow automation |
| **Ollama** | ollama/ollama:latest | 11434 | /mnt/efs/ollama | LLM inference |
| **Qdrant** | qdrant/qdrant:latest | 6333, 6334 | /mnt/efs/qdrant | Vector database |
| **Crawl4AI** | unclecode/crawl4ai:latest | 11235 | - | Web scraping |
| **PostgreSQL** | postgres:16 | 5432 | /mnt/efs/postgres | n8n backend |

## 3.4 Development Tools

| Tool | Version | Purpose |
|------|---------|---------|
| **pytest-cov** | 5.0+ | Coverage reporting |
| **pytest-asyncio** | 0.24+ | Async test support |

---
