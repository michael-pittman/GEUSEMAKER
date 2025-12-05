# 2. High Level Architecture

## Design Philosophy: UI-First Rewarding Experience

The CLI is the primary user touchpoint - every deployment interaction should feel **rewarding, informative, and trustworthy**. Users must never wonder "is it working?" or "what's happening?"

**Core UX Principles:**
1. **Continuous Feedback**: Every operation shows real-time progress with Rich spinners/progress bars
2. **Deployment Visibility**: Stream Docker logs directly to CLI so users see services starting
3. **Clear Success Signals**: Visual confirmation when n8n and all services are accessible
4. **Error Recovery Guidance**: When failures occur, provide actionable next steps

## 2.1 Mandatory Architecture Decisions

**EFS ALWAYS Required**: Every deployment uses Amazon EFS for persistent storage. This is non-negotiable because:
- n8n workflows, credentials, and execution history must survive instance termination
- Qdrant vector database indexes require persistence for RAG applications
- Ollama model weights are large (2-30GB) and must not re-download on restart
- PostgreSQL data must persist across spot instance interruptions

**EFS Integration Pattern:**
```
EC2 UserData Script:
1. Install amazon-efs-utils
2. Create mount point: /mnt/efs
3. Mount EFS: mount -t efs -o tls fs-XXXXX:/ /mnt/efs
4. Create service directories: /mnt/efs/{n8n,ollama,qdrant,postgres}
5. Start Docker Compose with EFS volume mounts
```

## 2.2 Technical Summary

GeuseMaker implements a **CLI-driven infrastructure orchestration architecture** built on Python with Boto3 for direct AWS API interaction. The system follows a **layered service architecture** with clear separation between:
- **UI Layer**: Rich-powered interactive CLI with real-time feedback
- **Orchestration Layer**: Deployment coordinators managing multi-resource workflows
- **Service Layer**: AWS resource managers (EC2, VPC, EFS, ALB, CloudFront)
- **Infrastructure Layer**: Boto3 clients, state persistence, Docker log streaming

Key architectural characteristics:
- **Monorepo structure** with Python package organization
- **EFS-backed persistent storage** for all AI services (mandatory)
- **Real-time log streaming** via SSM/SSH to show deployment progress
- **Configuration-driven deployments** using Pydantic models
- **Interactive resource discovery** enabling reuse of existing AWS infrastructure

This architecture directly supports PRD goals: <6 min CPU/<10 min GPU deployments, 70% cost savings via spot instances, and three-tier deployment flexibility.

## 2.3 High Level Overview

**Architectural Style:** Layered Monolith with Service Modules

**Repository Structure:** Monorepo (single `geusemaker/` Python package)

**Primary User Flow (with UI Feedback):**
```
User invokes CLI
    ↓ [Rich: Welcome banner, deployment type selection]
Interactive prompts guide configuration
    ↓ [Rich: Spinners for each discovery phase]
Resource discovery (VPC, subnets, keypairs)
    ↓ [Rich: Progress bar for resource creation]
AWS resource creation (EFS → Security Groups → EC2)
    ↓ [Rich: Live status updates]
UserData executes: Mount EFS, start Docker Compose
    ↓ [Rich: Stream Docker logs in real-time]
Health checks on all services
    ↓ [Rich: Service status table with checkmarks]
Display access URLs + credentials
    ↓ [Rich: Success panel with n8n URL prominently displayed]
User sees: "✓ Stack ready! Access n8n at http://..."
```

## 2.4 High Level Project Diagram

```mermaid
graph TB
    subgraph "CLI Layer (Rich UI)"
        CLI[Click CLI Entry Point]
        MENU[Interactive Menus]
        PROG[Progress Displays]
        LOGS[Docker Log Stream]
        STATUS[Service Status Table]
    end

    subgraph "Orchestration Layer"
        SPOT[Spot Deployment<br/>Tier 1: Dev]
        ALB_DEPLOY[ALB Deployment<br/>Tier 2: Automation]
        CDN_DEPLOY[CDN Deployment<br/>Tier 3: GPU]
    end

    subgraph "Service Layer"
        EFS_SVC[EFS Service<br/>Create + Mount Target]
        EC2_SVC[EC2 Service<br/>Spot/OnDemand]
        VPC_SVC[VPC Service<br/>Discovery/Create]
        SG_SVC[Security Group Service]
        ALB_SVC[ALB Service]
        CF_SVC[CloudFront Service]
    end

    subgraph "Infrastructure Layer"
        BOTO[Boto3 Clients]
        STATE[State Manager<br/>~/.geusemaker/*.json]
        CONFIG[Pydantic Config<br/>Validation]
        USERDATA[UserData Generator<br/>EFS Mount + Docker]
    end

    subgraph "AWS Cloud"
        direction TB
        AWSEFS[(EFS File System<br/>Persistent Storage)]
        AWSEC2[EC2 Instance]
        AWSVPC[VPC + Subnets]
        AWSALB[Application LB]
        AWSCF[CloudFront CDN]
    end

    subgraph "EC2 Instance Runtime"
        DOCKER[Docker Compose]
        EFS_MNT[/mnt/efs Mount]

        subgraph "AI Stack Services"
            N8N[n8n:5678<br/>/mnt/efs/n8n]
            OLLAMA[Ollama:11434<br/>/mnt/efs/ollama]
            QDRANT[Qdrant:6333<br/>/mnt/efs/qdrant]
            CRAWL[Crawl4AI:8000]
            PG[PostgreSQL:5432<br/>/mnt/efs/postgres]
        end
    end

    CLI --> MENU --> PROG
    CLI --> SPOT & ALB_DEPLOY & CDN_DEPLOY

    SPOT & ALB_DEPLOY & CDN_DEPLOY --> EFS_SVC & EC2_SVC & VPC_SVC & SG_SVC
    ALB_DEPLOY & CDN_DEPLOY --> ALB_SVC
    CDN_DEPLOY --> CF_SVC

    EFS_SVC & EC2_SVC & VPC_SVC & SG_SVC & ALB_SVC & CF_SVC --> BOTO
    BOTO --> CONFIG
    BOTO --> STATE
    EC2_SVC --> USERDATA

    BOTO --> AWSEFS & AWSEC2 & AWSVPC
    ALB_SVC --> AWSALB
    CF_SVC --> AWSCF

    AWSEFS -.->|NFS Mount| EFS_MNT
    AWSEC2 --> DOCKER
    DOCKER --> EFS_MNT
    EFS_MNT --> N8N & OLLAMA & QDRANT & PG
    DOCKER --> CRAWL

    DOCKER -.->|Log Stream| LOGS
    N8N & OLLAMA & QDRANT -.->|Health Check| STATUS

    AWSALB -.-> AWSEC2
    AWSCF -.-> AWSALB
```

## 2.5 Architectural and Design Patterns

| Pattern | Description | Rationale |
|---------|-------------|-----------|
| **Layered Architecture** | CLI → Orchestration → Services → Infrastructure | Clear separation; each layer has single responsibility |
| **Observer Pattern** | Progress callbacks from services to Rich UI | Real-time status updates during deployments |
| **Builder Pattern** | Pydantic models for AWS resource configuration | Type-safe config; validation before deployment |
| **Factory Pattern** | Deployment type creates appropriate orchestrator | Clean Tier 1/2/3 variations |
| **Strategy Pattern** | Pluggable instance selection (spot vs on-demand) | Cost optimization per PRD requirements |
| **Service Module Pattern** | Each AWS resource type has dedicated service | Encapsulates Boto3; enables mocking for tests |
| **Repository Pattern** | StateManager abstracts JSON persistence | Future migration to DB if needed |

**Communication Patterns:**
- **Synchronous calls** for most AWS operations (create, describe)
- **Polling with exponential backoff** for async operations (instance ready, health checks)
- **SSM Session Manager** for Docker log streaming to CLI
- **Structured logging** with correlation IDs for debugging

**EFS Volume Mapping (Docker Compose):**
```yaml
volumes:
  n8n_data:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: /mnt/efs/n8n
  ollama_data:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: /mnt/efs/ollama
  qdrant_data:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: /mnt/efs/qdrant
  postgres_data:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: /mnt/efs/postgres
```

---
