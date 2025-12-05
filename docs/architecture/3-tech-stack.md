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
| **Terminal UI** | Rich | 13.9+ | Interactive output, progress, tables | Best-in-class terminal UX, spinners, live displays |
| **Validation** | Pydantic | 2.9+ | Config validation, settings | V2 performance, ConfigDict, Field validators |
| **HTTP Client** | httpx | 0.27+ | Health checks, API calls | Async support, modern API, type hints |
| **Testing** | pytest | 8.3+ | Unit and integration tests | Industry standard, fixtures, parameterization |
| **Mocking** | moto | 5.0.25 | AWS service mocking | Pinned version for stable AWS mock coverage |
| **Linting** | Ruff | 0.5+ | Code quality | Fast, replaces flake8/isort/black |
| **Type Checking** | mypy | 1.11+ | Static type analysis | Strict mode for reliability |
| **Package Manager** | uv | 0.4+ | Dependency management | Fast, modern, lockfile support |
| **Container Runtime** | Docker | 24+ | AI service deployment | Standard container platform |
| **Compose** | Docker Compose | 2.29+ | Multi-container orchestration | Service definitions, health checks |

## 3.3 AI Stack Services (Deployed on EC2)

| Service | Image | Port | Persistent Storage | Purpose |
|---------|-------|------|-------------------|---------|
| **n8n** | n8nio/n8n:latest | 5678 | /mnt/efs/n8n | Workflow automation |
| **Ollama** | ollama/ollama:latest | 11434 | /mnt/efs/ollama | LLM inference |
| **Qdrant** | qdrant/qdrant:latest | 6333, 6334 | /mnt/efs/qdrant | Vector database |
| **Crawl4AI** | unclecode/crawl4ai:latest | 8000 | - | Web scraping |
| **PostgreSQL** | postgres:16 | 5432 | /mnt/efs/postgres | n8n backend |

## 3.4 Development Tools

| Tool | Version | Purpose |
|------|---------|---------|
| **pre-commit** | 3.8+ | Git hooks for quality gates |
| **pytest-cov** | 5.0+ | Coverage reporting |
| **pytest-asyncio** | 0.24+ | Async test support |

---
