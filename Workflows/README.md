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

#### `04-web-scrape-to-qdrant.json`
**Complete pipeline** to scrape websites and store embeddings in Qdrant.

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
2. Crawls website with Crawl4AI
3. Chunks content into 1000-character pieces
4. Generates embeddings with Ollama
5. Stores vectors in Qdrant collection `web-scrapes`
6. Shows success message

**Features:**
- User-friendly form interface (no API knowledge needed)
- Automatic content chunking
- Vector embedding generation
- Qdrant storage with metadata
- Error handling
- **Best for:** Non-technical users, manual content ingestion, one-off scraping

### 3. Semantic Search & RAG

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

### 3. Activate Workflows

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

### Adjust Chunk Size

Edit the `chunkSize` variable in `Chunk Content` node (04-web-scrape-to-qdrant.json):

```javascript
const chunkSize = 1000; // Change to desired size (500-2000 recommended)
```

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

## Additional Resources

- [n8n Documentation](https://docs.n8n.io/)
- [n8n Trigger Nodes](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.manualtrigger/)
- [Ollama API Documentation](https://github.com/ollama/ollama/blob/main/docs/api.md)
- [Qdrant API Documentation](https://qdrant.github.io/qdrant/redoc/index.html)
- [Crawl4AI Documentation](https://github.com/unclecode/crawl4ai)
