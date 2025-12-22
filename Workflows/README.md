# N8N Workflows for GeuseMaker Stack

This directory contains n8n workflow JSON files that integrate with all services in the GeuseMaker stack:
- **n8n** (workflow automation)
- **Ollama** (LLM inference)
- **Qdrant** (vector database)
- **Crawl4AI** (web scraping)
- **PostgreSQL** (database)

## Workflow Files

### 1. Pull Ollama Models

#### `01-pull-ollama-model-webhook.json`
**Webhook-triggered workflow** to pull Ollama models via API.

**Trigger Type:** Webhook (POST endpoint)

**Usage:**
```bash
curl -X POST http://<n8n-url>/webhook/pull-model \
  -H "Content-Type: application/json" \
  -d '{"model_name": "nomic-embed-text"}'
```

**Features:**
- Validates input (model_name required)
- Pulls model from Ollama registry
- Verifies installation by listing models
- Returns success/error responses
- **Best for:** API integrations, external systems, automation scripts

#### `02-pull-ollama-model-manual.json`
**Manual workflow** to pull a single Ollama model.

**Trigger Type:** Manual Trigger (click "Test workflow" button)

**Usage:**
1. Import workflow into n8n
2. Edit "Set Model Name" node to change model
3. Click "Execute Workflow" or "Test workflow"

**Features:**
- Simple manual trigger (no webhook setup needed)
- Configurable model name
- Lists all models after pull
- **Best for:** One-off model installations, testing, manual operations

#### `03-batch-pull-ollama-models.json`
**Batch workflow** to pull multiple Ollama models in sequence.

**Trigger Type:** Manual Trigger (click "Test workflow" button)

**Usage:**
1. Import workflow into n8n
2. Edit "Set Models List" node with comma-separated model names
3. Execute workflow manually

**Features:**
- Pulls multiple models sequentially
- Processes comma-separated list
- Lists all installed models at end
- **Best for:** Initial setup, bulk model installation

**Example models list:**
```
nomic-embed-text,znbang/bge:small-en-v1.5,all-minilm
```

### 2. Web Scraping & Vector Storage

#### `04-web-scrape-to-qdrant.json` (Enhanced v2.0)
**Complete pipeline** to scrape websites and store embeddings in Qdrant with enhanced error handling and crawl4ai 2.0.2 features.

**Trigger Type:** Form Trigger (user-friendly web form)

**Usage:**
1. Import workflow into n8n
2. Activate workflow
3. Access the form URL (shown in n8n UI)
4. Enter website URL in the form
5. Submit to scrape and store

**Alternative:** You can also trigger via webhook if needed:
```bash
curl -X POST http://<n8n-url>/form/<form-path> \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "url=https://example.com"
```

**Workflow Steps:**
1. User submits URL via form
2. **Validates URL format** (http/https only, proper format)
3. **Crawls website with Crawl4AI 2.0.2** (enhanced parameters)
4. **Validates crawl response** (checks for errors, content length)
5. **Chunks content** with 200-char overlap for better context
6. Generates embeddings with Ollama (with retry logic)
7. Stores vectors in Qdrant collection `web-scrapes` (with retry logic)
8. **Aggregates results** and shows summary

**Enhanced Features (v2.0):**
- ✅ **URL validation** before crawling (prevents invalid requests)
- ✅ **Crawl4AI 2.0.2 parameters**: `remove_overlay_elements`, `process_iframes`, `timeout`, `word_count_threshold`
- ✅ **Response validation** with detailed error messages
- ✅ **Chunking with overlap** (200 chars) for better context preservation
- ✅ **Retry logic** on all HTTP requests (Crawl4AI, Ollama, Qdrant)
- ✅ **Enhanced error handling** at each step
- ✅ **Rich metadata** tracking (timestamps, chunk indices, embedding dimensions)
- ✅ **Result aggregation** with summary statistics
- ✅ **Timeout handling** (60s for crawl, 30s for embeddings/Qdrant)
- User-friendly form interface (no API knowledge needed)
- **Best for:** Production use, reliable scraping, content ingestion with error recovery

**Crawl4AI 2.0.2 Parameters Used:**
- `bypass_cache`: true (always fetch fresh content)
- `extract_markdown`: true (structured text extraction)
- `extract_links`: true (capture all links)
- `wait_for`: "networkidle" (wait for page to fully load)
- `remove_overlay_elements`: true (remove popups/modals)
- `process_iframes`: false (skip iframes for performance)
- `timeout`: 30000ms (30 second timeout)
- `word_count_threshold`: 100 (minimum content length)

### 3. Qdrant Management

#### `06-qdrant-management.json`
**Collection management workflow** for creating, listing, and managing Qdrant collections.

**Trigger Type:** Form Trigger (user-friendly web form)

**Usage:**
1. Import workflow into n8n
2. Activate workflow
3. Access the form URL
4. Select action: Create, List, Info, Delete, or Stats
5. Enter collection name and parameters
6. Submit

**Available Actions:**
- **Create Collection** - Create new collection with specified vector size
- **List All Collections** - View all collections with point counts
- **Get Collection Info** - View detailed collection information
- **Delete Collection** - Remove collection (careful!)
- **Get Statistics** - View collection statistics and configuration

**Features:**
- User-friendly form interface
- Supports all collection operations
- Validates inputs
- Formatted responses
- **Best for:** Collection setup, maintenance, monitoring

**Example Use Cases:**
- Create collections for new workflows
- Check collection sizes before cleanup
- Verify collection configuration
- Monitor collection health

#### `07-qdrant-cleanup.json`
**Data cleanup and maintenance workflow** for Qdrant collections.

**Trigger Type:** Form Trigger (user-friendly web form)

**Usage:**
1. Import workflow into n8n
2. Activate workflow
3. Access the form URL
4. Select collection and cleanup action
5. Enter parameters (days old, URL, etc.)
6. Submit

**Available Actions:**
- **Delete Points Older Than** - Remove points older than X days
- **Delete by URL** - Remove all points from specific URL
- **Optimize Collection** - Optimize collection index for performance
- **Create Snapshot** - Create backup snapshot

**Features:**
- Time-based data retention
- URL-based cleanup
- Collection optimization
- Snapshot creation
- Batch deletion support
- **Best for:** Data lifecycle management, maintenance, backups

**Example Use Cases:**
- Weekly cleanup of old scraped content
- Remove outdated data before re-scraping
- Optimize collections after bulk operations
- Create backups before major changes

**⚠️ Important:** Always create snapshots before bulk deletions!

### 4. Semantic Search & RAG

#### `05-semantic-search-rag.json`
**RAG (Retrieval-Augmented Generation)** workflow for semantic search.

**Trigger Type:** Chat Trigger (conversational interface)

**Usage:**
1. Import workflow into n8n
2. Activate workflow
3. Access the chat URL (shown in n8n UI when public)
4. Start chatting naturally - ask questions about scraped content
5. The AI will search Qdrant and provide answers

**Features:**
- Natural language conversation interface
- Semantic search in Qdrant
- Context-aware answer generation using RAG
- Configurable result limit (default: 5)
- Score threshold filtering (default: 0.7)
- **Best for:** End users, customer support, knowledge base queries

**Example queries:**
- "What is machine learning?"
- "Tell me about the features mentioned in the documentation"
- "Summarize the main points from the scraped articles"

## Trigger Types Explained

### Manual Trigger
- **When to use:** Testing, one-off operations, manual tasks
- **How it works:** Click "Test workflow" button in n8n UI
- **Best for:** Development, debugging, ad-hoc operations

### Webhook Trigger
- **When to use:** API integrations, external systems, automation
- **How it works:** HTTP POST/GET requests to webhook URL
- **Best for:** Programmatic access, CI/CD pipelines, external services

### Form Trigger
- **When to use:** User input, data collection, non-technical users
- **How it works:** n8n generates a web form with custom fields
- **Best for:** Content submission, user-friendly interfaces, data entry

### Chat Trigger
- **When to use:** Conversational interfaces, AI assistants, Q&A systems
- **How it works:** n8n provides a chat widget (hosted or embedded)
- **Best for:** Customer support, knowledge bases, interactive AI

### Schedule Trigger (Future Enhancement)
- **When to use:** Automated periodic tasks, scheduled scraping, maintenance
- **How it works:** Runs on cron schedule (e.g., daily, hourly)
- **Best for:** Regular content updates, automated monitoring

## Service Endpoints

All workflows use Docker container names for service communication:

- **Ollama**: `http://ollama:11434`
- **Qdrant**: `http://qdrant:6333`
- **Crawl4AI**: `http://crawl4ai:11235`
- **n8n**: `http://localhost:5678` (for webhooks/forms/chat)

**Important:** Use container names (`ollama`, `qdrant`, `crawl4ai`) when n8n runs in Docker, NOT `localhost`. Container names resolve via Docker's internal DNS.

## Prerequisites

### 1. Create Qdrant Collection

Before using workflows that store vectors, create the Qdrant collection:

```bash
curl -X PUT http://localhost:6333/collections/web-scrapes \
  -H "Content-Type: application/json" \
  -d '{
    "vectors": {
      "size": 768,
      "distance": "Cosine"
    }
  }'
```

**Note:** Vector size depends on embedding model:
- `nomic-embed-text`: 768 dimensions
- `znbang/bge:small-en-v1.5`: Check model documentation
- `all-minilm`: 384 dimensions

### 2. Install Embedding Models

Ensure embedding models are installed in Ollama:

```bash
# Check installed models
docker exec ollama ollama list

# Install embedding model if needed
docker exec ollama ollama pull nomic-embed-text
```

**Quick install using workflow:**
1. Import `02-pull-ollama-model-manual.json`
2. Edit model name in "Set Model Name" node
3. Click "Test workflow"

### 3. ADK Agent Management

#### `07-generic-service-installer.json`
**Generic service installer** for installing Python packages, npm packages, or apt packages on the n8n server.

**Trigger Type:** Webhook (POST endpoint)

**Usage:**
```bash
# Install a Python package
curl -X POST http://<n8n-url>/webhook/install-service \
  -H "Content-Type: application/json" \
  -d '{
    "service_name": "google-adk",
    "install_method": "pip",
    "version": "latest",
    "venv_path": "/opt/adk-venv"
  }'

# Install via npm
curl -X POST http://<n8n-url>/webhook/install-service \
  -H "Content-Type: application/json" \
  -d '{
    "service_name": "some-package",
    "install_method": "npm"
  }'
```

**Features:**
- Supports pip, npm, and apt installation methods
- Creates Python virtual environments automatically
- Verifies installation after completion
- Returns detailed output and verification results
- **Best for:** Installing any service/package on the n8n server

#### `08-adk-install-create-deploy.json`
**Complete ADK agent lifecycle management** - install ADK, create agents, and deploy them as systemd services.

**Trigger Type:** Webhook (POST endpoint)

**Actions:**
1. **install** - Install Google ADK in a virtual environment
2. **create** - Generate ADK agent Python code with all tools
3. **deploy** - Deploy agent as systemd service

**Usage:**

**Install ADK:**
```bash
curl -X POST http://<n8n-url>/webhook/adk-install-deploy \
  -H "Content-Type: application/json" \
  -d '{
    "action": "install",
    "adk_version": "latest",
    "venv_path": "/opt/adk-venv"
  }'
```

**Create ADK Agent:**
```bash
curl -X POST http://<n8n-url>/webhook/adk-install-deploy \
  -H "Content-Type: application/json" \
  -d '{
    "action": "create",
    "agent_name": "qdrant_manager",
    "model_name": "gemini-2.5-flash",
    "enable_qdrant_tools": true,
    "enable_ollama_tools": true,
    "enable_crawl4ai_tools": true,
    "enable_n8n_mcp": true,
    "n8n_mcp_token": "your-token-here",
    "qdrant_url": "http://qdrant:6333",
    "ollama_url": "http://ollama:11434",
    "crawl4ai_url": "http://crawl4ai:11235"
  }'
```

**Deploy ADK Agent:**
```bash
curl -X POST http://<n8n-url>/webhook/adk-install-deploy \
  -H "Content-Type: application/json" \
  -d '{
    "action": "deploy",
    "agent_name": "qdrant_manager",
    "agent_port": 8000,
    "venv_path": "/opt/adk-venv"
  }'
```

**Configuration Parameters:**
- `agent_name` - Name of the ADK agent (default: "qdrant_manager")
- `model_name` - Gemini model to use (default: "gemini-2.5-flash")
- `agent_port` - Port for ADK web server (default: 8000)
- `venv_path` - Python virtual environment path (default: "/opt/adk-venv")
- `agent_dir` - Directory for agent files (default: "/mnt/efs/adk-agents")
- `enable_qdrant_tools` - Enable Qdrant integration tools (default: true)
- `enable_ollama_tools` - Enable Ollama integration tools (default: true)
- `enable_crawl4ai_tools` - Enable Crawl4AI web scraping tools (default: true)
- `enable_n8n_mcp` - Enable n8n MCP integration (default: false)
- `qdrant_url`, `ollama_url`, `crawl4ai_url`, `n8n_url` - Service URLs
- `n8n_mcp_token` - Token for n8n MCP server authentication
- `google_api_key` - Google API key for Gemini models
- `agent_instruction` - Custom agent instruction prompt
- `deployment_method` - Deployment method (default: "systemd")

**Available Tools Generated:**

**Qdrant Tools** (when `enable_qdrant_tools: true`):
- `list_qdrant_collections` - List all collections
- `get_collection_info` - Get collection details
- `create_collection` - Create new collection
- `search_qdrant` - Semantic search in collection (uses Ollama for embeddings)

**Ollama Tools** (when `enable_ollama_tools: true`):
- `ollama_generate` - Generate text using Ollama LLM

**Crawl4AI Tools** (when `enable_crawl4ai_tools: true`):
- `crawl4ai_scrape` - Scrape a single website (returns markdown, HTML, links)
- `crawl4ai_batch_scrape` - Scrape multiple URLs in batch

**n8n MCP Tools** (when `enable_n8n_mcp: true` and `n8n_mcp_token` provided):
- `n8n_mcp_toolset` - Full n8n workflow management via MCP protocol

**Features:**
- Complete ADK agent lifecycle management
- Generates Python code with Qdrant, Ollama, and n8n MCP tools
- Creates systemd services for production deployment
- All configuration parameters exposed in workflow nodes
- Persistent storage on EFS (`/mnt/efs/adk-agents`)
- **Best for:** Managing ADK agents in hybrid n8n/ADK architecture

### 4. Activate Workflows

After importing workflows into n8n:
1. Open each workflow
2. Click "Activate" toggle
3. For webhooks/forms/chat: Copy URLs shown in trigger nodes
4. For manual triggers: Just click "Test workflow" when needed

## Workflow Customization

### Change Embedding Model

Edit the `model` field in embedding nodes:
- `Generate Embeddings` node (04-web-scrape-to-qdrant.json)
- `Embed User Query` node (05-semantic-search-rag.json)

Change from:
```json
"model": "nomic-embed-text"
```

To:
```json
"model": "znbang/bge:small-en-v1.5"
```

### Adjust Chunk Size and Overlap

Edit the chunking parameters in `Chunk Content` node (04-web-scrape-to-qdrant.json):

```javascript
const chunkSize = 1000;        // Change to desired size (500-2000 recommended)
const chunkOverlap = 200;      // Overlap between chunks for context preservation
```

**Why overlap?** Overlapping chunks preserve context at boundaries, improving embedding quality for semantic search. Recommended overlap: 10-20% of chunk size.

### Modify Search Parameters

Edit Qdrant search parameters in `Search Qdrant` node (05-semantic-search-rag.json):

```json
{
  "limit": 5,              // Number of results (1-10 recommended)
  "score_threshold": 0.7    // Minimum similarity score (0.0-1.0)
}
```

### Change LLM Model

Edit the `model` field in `Generate RAG Answer` node (05-semantic-search-rag.json):

```json
"model": "qwen2.5:1.5b-instruct"  // Change to desired model
```

Available models (preloaded in GeuseMaker):
- `qwen2.5:1.5b-instruct` (lightweight, fast)
- `qwen2.5-omni-7b` (better quality)
- `qwen3-omni-30b-a3b:q4_k_s` (GPU tier only)

### Customize Form Fields

Edit `Form Trigger` node (04-web-scrape-to-qdrant.json) to add more fields:
- Add description field
- Add tags/categories
- Add priority level
- Add custom metadata

### Customize Chat Interface

Edit `Chat Trigger` node (05-semantic-search-rag.json) options:
- Change title and subtitle
- Customize welcome message
- Adjust styling with CSS
- Enable file uploads

## Troubleshooting

### Workflow Fails with "Connection Refused"

**Problem:** n8n can't reach services

**Solution:** 
- Verify services are running: `docker ps`
- Check container names match workflow URLs
- Ensure n8n and services are on same Docker network
- Test connectivity: `docker exec n8n curl http://ollama:11434/api/tags`

### Embedding Model Not Found

**Problem:** Ollama returns error about missing model

**Solution:**
- Install model using workflow `02-pull-ollama-model-manual.json`
- Or manually: `docker exec ollama ollama pull <model-name>`
- Verify: `docker exec ollama ollama list`
- Update workflow to use installed model name

### Qdrant Collection Not Found

**Problem:** 404 error when storing/searching vectors

**Solution:**
- Create collection first (see Prerequisites)
- Verify collection name matches workflow (`web-scrapes`)
- Check Qdrant is accessible: `curl http://localhost:6333/health`
- List collections: `curl http://localhost:6333/collections`

### Crawl4AI Returns Empty Content

**Problem:** Website scraping returns no markdown

**Solution:**
- Check URL is accessible
- Some sites block scrapers - try different URL
- Verify Crawl4AI is running: `curl http://localhost:11235/health`
- Check Crawl4AI logs: `docker logs crawl4ai`

### Form/Chat Not Accessible

**Problem:** Can't access form or chat URL

**Solution:**
- Ensure workflow is activated
- Check n8n is accessible from your network
- For public access: Enable "Make Chat Publicly Available" in Chat Trigger
- Check firewall/security group settings
- Verify n8n webhook URL is correct

## Importing Workflows

### Method 1: n8n UI (Recommended)
1. Open n8n: `http://<public-ip>:5678`
2. Click "Workflows" → "Import from File"
3. Select workflow JSON file
4. Review workflow structure
5. Activate workflow (for webhooks/forms/chat)
6. Copy trigger URLs if needed

### Method 2: n8n API
```bash
curl -X POST http://localhost:5678/api/v1/workflows \
  -H "Content-Type: application/json" \
  -H "X-N8N-API-KEY: <your-api-key>" \
  -d @Workflows/01-pull-ollama-model-webhook.json
```

## Workflow Execution Flow

### Typical Usage Pattern

1. **Setup Phase:**
   - Import all workflows
   - Create Qdrant collection
   - Install embedding models (use workflow 02 or 03)

2. **Content Ingestion:**
   - Use workflow 04 (Form Trigger) to scrape websites
   - Content is automatically chunked, embedded, and stored

3. **Query Phase:**
   - Use workflow 05 (Chat Trigger) to ask questions
   - AI searches Qdrant and provides answers

4. **Maintenance:**
   - Use workflow 01 (Webhook) for automated model updates
   - Use workflow 02/03 (Manual) for ad-hoc model management

## Next Steps

1. **Import workflows** into your n8n instance
2. **Create Qdrant collection** for vector storage
3. **Install embedding models** in Ollama (use workflow 02 or 03)
4. **Test workflows** with sample data
5. **Scrape some websites** using workflow 04
6. **Try semantic search** using workflow 05
7. **Customize** for your specific use case

## Qdrant Management

For comprehensive Qdrant management guidance, see **[QDRANT_MANAGEMENT_GUIDE.md](QDRANT_MANAGEMENT_GUIDE.md)**.

**Quick Start:**
1. Import `06-qdrant-management.json` for collection operations
2. Import `07-qdrant-cleanup.json` for data maintenance
3. Read the management guide for best practices

**Key Topics Covered:**
- Collection naming conventions
- Data lifecycle management
- Performance optimization
- Backup & recovery
- Multi-workflow best practices
- Troubleshooting

## Additional Resources

- [n8n Documentation](https://docs.n8n.io/)
- [n8n Trigger Nodes](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.manualtrigger/)
- [Ollama API Documentation](https://github.com/ollama/ollama/blob/main/docs/api.md)
- [Qdrant API Documentation](https://qdrant.github.io/qdrant/redoc/index.html)
- [Qdrant Management Guide](QDRANT_MANAGEMENT_GUIDE.md) - **Comprehensive Qdrant management**
- [Crawl4AI Documentation](https://github.com/unclecode/crawl4ai)
