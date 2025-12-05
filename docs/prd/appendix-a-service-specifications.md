# Appendix A: Service Specifications

## n8n (Workflow Automation)
- **Image**: `n8nio/n8n:latest`
- **Port**: 5678 (HTTP)
- **Database**: PostgreSQL
- **Health Endpoint**: `/healthz`
- **Volume**: Persistent storage for workflow data

## Ollama (LLM Inference)
- **Image**: `ollama/ollama:latest`
- **Port**: 11434 (HTTP)
- **API Endpoints**: `/api/generate`, `/api/chat`, `/api/tags`, `/api/pull`
- **Health Endpoint**: `/api/tags`
- **Volume**: Persistent storage for models

## Qdrant (Vector Database)
- **Image**: `qdrant/qdrant:latest`
- **Ports**: 6333 (HTTP), 6334 (gRPC)
- **API**: REST and gRPC
- **Health Endpoint**: `/health`
- **Volume**: Persistent storage for collections

## Crawl4AI (Web Scraping)
- **Image**: `unclecode/crawl4ai:latest`
- **Port**: 8000 (HTTP)
- **Health Endpoint**: `/health`
- **Volume**: Persistent storage for crawl data

## PostgreSQL (Database)
- **Image**: `postgres:16-alpine`
- **Port**: 5432 (internal only)
- **Health**: `pg_isready` command
- **Volume**: Persistent storage for database

---
