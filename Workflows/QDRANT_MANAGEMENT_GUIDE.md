# Qdrant Management Guide

## Overview

The **AI-Powered Qdrant Vector Database Manager** (workflow 06) provides comprehensive tools for managing your Qdrant vector database collections through multiple interfaces:

1. **🤖 AI Agent Chat Interface** - Natural language commands
2. **🚀 Quick Setup Prerequisites** - One-click setup for web-scrapes collection
3. **⚙️ Custom Collection Builder** - Full control over collection settings
4. **📝 Document Ingestion** - Direct document embedding and storage

---

## Quick Start: Setup Prerequisites for Web Scraping Workflow

### 🚀 One-Click Setup

**To enable the Web Scrape → Qdrant RAG workflow (04), you need to create the `web-scrapes` collection:**

1. Open workflow **06-qdrant-management.json** in n8n
2. Find the **"Manual Trigger - Setup Prerequisites"** node
3. Click **"Execute node"** or **"Test workflow"**
4. Done! The `web-scrapes` collection is now ready

**What this creates:**
- **Collection name**: `web-scrapes`
- **Vector size**: 768 (for nomic-embed-text embeddings)
- **Distance metric**: Cosine (optimal for semantic search)
- **HNSW config**: `m=16`, `ef_construct=100` (balanced speed/accuracy)
- **Indexing threshold**: 10,000 points (optimized for web scraping)

**Verification:**
\`\`\`bash
# Check collection exists
curl http://qdrant:6333/collections/web-scrapes

# Expected response:
{
  "result": {
    "status": "green",
    "vectors_count": 0,
    "indexed_vectors_count": 0,
    "points_count": 0,
    "config": {
      "params": {
        "vectors": {
          "size": 768,
          "distance": "Cosine"
        }
      }
    }
  }
}
\`\`\`

---

## Workflow 06 Architecture

\`\`\`
┌─────────────────────────────────────────────────────────────────────┐
│                    QDRANT MANAGEMENT WORKFLOW 06                     │
└─────────────────────────────────────────────────────────────────────┘

🤖 AI AGENT CHAT INTERFACE
├── Chat Trigger (public hosted chat)
├── Qdrant Management Agent (Qwen 2.5)
└── 5 AI Tools:
    ├── list_collections
    ├── get_collection_info
    ├── create_collection
    ├── delete_collection
    └── search_collection

🚀 QUICK SETUP PREREQUISITES (Recommended)
├── Manual Trigger - Setup Prerequisites
├── Preset: web-scrapes Collection
│   ├── collection_name: "web-scrapes"
│   ├── vector_size: 768
│   ├── distance: "Cosine"
│   └── HNSW: m=16, ef_construct=100
└── Create web-scrapes Collection → Qdrant HTTP PUT

⚙️ CUSTOM COLLECTION BUILDER
├── Manual Trigger - Custom Collection
├── Set Custom Parameters
│   ├── operation: create|list|delete
│   ├── collection_name: (editable)
│   ├── vector_size: (editable)
│   └── distance: (editable)
├── Route Operation (Switch)
└── Direct HTTP operations

📝 DOCUMENT INGESTION
├── Manual Trigger - Document Ingestion
├── Set Document to Ingest
├── Generate Embedding (Ollama)
└── Insert into Qdrant
\`\`\`

---

## How to Use: Step-by-Step

### Method 1: Quick Setup (Recommended for First-Time Users)

**Goal**: Create `web-scrapes` collection for workflow 04

1. **Import workflow 06** into n8n
2. **Open the workflow** in edit mode
3. **Find the node**: "Manual Trigger - Setup Prerequisites"
   - It has a 🚀 icon and green note
4. **Execute**:
   - Click the node
   - Click "Execute node" button
   - OR click "Test workflow" in top right
5. **Verify**:
   - You should see success response from Qdrant
   - Collection `web-scrapes` is now created

**That's it!** You can now use workflow 04 to scrape and store web content.

---

### Method 2: AI Chat Interface

**Goal**: Manage collections via natural language

1. **Activate the workflow** (toggle switch in top right)
2. **Get the chat URL**:
   - Click "Production URL" or "Test URL" on Chat Trigger node
   - URL format: `https://your-n8n.com/chat/<workflow-id>`
3. **Use natural language**:

**Example Conversations:**

\`\`\`
👤 User: "List all my collections"
🤖 Agent: I found 2 collections:
        • web-scrapes: 0 points (768-dim, Cosine)
        • knowledge-base: 145 points (768-dim, Cosine)

👤 User: "Create a new collection called customer-docs with 768 dimensions"
🤖 Agent: ✅ Created collection 'customer-docs' with 768-dimensional vectors 
        using Cosine distance metric.

👤 User: "Search web-scrapes for 'RAG best practices'"
🤖 Agent: 🔍 Found 3 results:
        1. Score 0.89: "RAG (Retrieval Augmented Generation) best practices..."
        2. Score 0.82: "Implementing RAG systems with vector databases..."
        3. Score 0.78: "Best practices for chunking and embedding..."

👤 User: "Get detailed info about web-scrapes"
🤖 Agent: ℹ️ Collection: web-scrapes
        • Vector size: 768 dimensions
        • Distance metric: Cosine
        • Total points: 145
        • Indexed: 145/145
        • Status: Green ✅

👤 User: "Delete collection test-data"
🤖 Agent: ⚠️ WARNING: This will permanently delete 'test-data' and all 
        its 1,234 points. Are you sure? Reply 'yes' to confirm.
👤 User: "yes"
🤖 Agent: ✅ Collection 'test-data' has been deleted successfully.
\`\`\`

---

### Method 3: Custom Collection Builder

**Goal**: Create collections with specific configurations

1. **Find the node**: "Set Custom Parameters"
2. **Edit the parameters**:
   - Click the node
   - Update the values in the "Assignments" section:

\`\`\`javascript
operation: "create"           // create | list | delete
collection_name: "my-docs"    // Your collection name
vector_size: 768              // Must match your embedding model
distance: "Cosine"            // Cosine | Euclid | Dot
\`\`\`

3. **Execute**:
   - Click "Manual Trigger - Custom Collection"
   - Click "Execute node"

**Common Configurations:**

#### For nomic-embed-text (default in GeuseMaker):
\`\`\`javascript
{
  operation: "create",
  collection_name: "web-scrapes",
  vector_size: 768,
  distance: "Cosine"
}
\`\`\`

#### For OpenAI text-embedding-ada-002:
\`\`\`javascript
{
  operation: "create",
  collection_name: "openai-docs",
  vector_size: 1536,
  distance: "Cosine"
}
\`\`\`

#### For all-MiniLM-L6-v2:
\`\`\`javascript
{
  operation: "create",
  collection_name: "minilm-docs",
  vector_size: 384,
  distance: "Cosine"
}
\`\`\`

---

### Method 4: Document Ingestion

**Goal**: Manually upload a single document

1. **Find the node**: "Set Document to Ingest"
2. **Edit the document**:

\`\`\`javascript
text: "Your document content here. Can be multiple paragraphs."
collection_name: "web-scrapes"  // Target collection
metadata: {
  source: "manual",
  timestamp: "2025-12-20T12:00:00Z",
  topic: "AI/RAG",
  author: "Admin"
}
\`\`\`

3. **Execute**:
   - Click "Manual Trigger - Document Ingestion"
   - Click "Execute node"

**What happens:**
- Text is sent to Ollama for embedding
- 768-dim vector is generated
- Point is stored in Qdrant with unique ID
- Metadata is attached to the point

---

## Configuration Reference

### Vector Size by Embedding Model

| Model | Dimension | Distance | Use Case |
|-------|-----------|----------|----------|
| **nomic-embed-text** | 768 | Cosine | Text (GeuseMaker default) |
| mxbai-embed-large | 1024 | Cosine | High-quality text |
| all-MiniLM-L6-v2 | 384 | Cosine | Fast, lightweight text |
| text-embedding-ada-002 | 1536 | Cosine | OpenAI embeddings |
| embed-english-v3.0 | 1024 | Cosine | Cohere embeddings |

**Rule**: Vector size MUST match your embedding model exactly, or inserts will fail.

---

### Distance Metrics Explained

#### Cosine (Recommended for Text)
- **Range**: -1 to 1 (1 = identical, -1 = opposite)
- **Use**: Text embeddings, semantic search
- **Why**: Handles different vector magnitudes well
- **Models**: nomic, OpenAI, Cohere, sentence-transformers

#### Euclidean
- **Range**: 0 to ∞ (0 = identical)
- **Use**: Image embeddings, dense vectors
- **Why**: Absolute distance in vector space
- **Models**: Some image models, scientific data

#### Dot Product
- **Range**: -∞ to ∞ (higher = more similar)
- **Use**: Unnormalized vectors
- **Why**: Efficient when vectors aren't normalized
- **Models**: Specific models that output unnormalized vectors

**Default**: Always use **Cosine** for text unless you have a specific reason not to.

---

### HNSW Configuration (Advanced)

HNSW (Hierarchical Navigable Small World) controls search performance:

\`\`\`json
{
  "hnsw_config": {
    "m": 16,              // Links per node
    "ef_construct": 100   // Search depth during indexing
  }
}
\`\`\`

**Presets:**

| Preset | m | ef_construct | Speed | Accuracy | Memory | Use Case |
|--------|---|--------------|-------|----------|--------|----------|
| **Balanced** | 16 | 100 | Medium | Medium | Medium | Default (recommended) |
| High Recall | 32 | 200 | Slower | High | High | Production RAG |
| Fast Search | 8 | 50 | Fast | Lower | Low | Real-time apps |
| Memory Efficient | 12 | 80 | Medium | Medium | Low | Large datasets |

**Trade-offs:**
- ↑ `m` = Better recall + More memory
- ↑ `ef_construct` = Better indexing + Slower indexing
- ↓ Values = Faster + Less accurate

---

### Indexing Threshold

Controls when Qdrant builds the HNSW index:

\`\`\`json
{
  "optimizers_config": {
    "indexing_threshold": 10000
  }
}
\`\`\`

| Dataset Size | Recommended Threshold | Reason |
|--------------|----------------------|--------|
| < 1K points | 100-500 | Fast indexing, quick search |
| 1K-10K | 1,000-5,000 | Balanced |
| 10K-100K | 10,000 | **Default** (GeuseMaker) |
| 100K-1M | 20,000-50,000 | Fewer re-indexes |
| Streaming | 5,000 | Frequent updates |

**How it works:**
- Below threshold: Points stored but not indexed (slower search)
- At threshold: HNSW index built (fast search enabled)
- Lower = Faster search availability, more frequent re-indexing
- Higher = Delayed search optimization, fewer re-indexes

---

## Common Tasks

### Task 1: Verify Collection Exists

**Via AI Chat:**
\`\`\`
User: "list all collections"
\`\`\`

**Via curl:**
\`\`\`bash
curl http://qdrant:6333/collections
\`\`\`

**Expected output:**
\`\`\`json
{
  "result": {
    "collections": [
      {
        "name": "web-scrapes",
        "vectors_count": 0,
        "points_count": 0
      }
    ]
  }
}
\`\`\`

---

### Task 2: Check Collection Health

**Via AI Chat:**
\`\`\`
User: "get info about web-scrapes collection"
\`\`\`

**Via curl:**
\`\`\`bash
curl http://qdrant:6333/collections/web-scrapes
\`\`\`

**Look for:**
- ✅ `status: "green"` (healthy)
- ✅ `indexed_vectors_count ≈ vectors_count` (fully indexed)
- ❌ `status: "yellow"` or `"red"` (issues)

---

### Task 3: Delete and Recreate Collection

**Why**: Change vector size, distance metric, or start fresh

**Steps:**
1. **Delete** (via AI chat with confirmation):
   \`\`\`
   User: "delete collection web-scrapes"
   Agent: ⚠️ Confirm deletion?
   User: "yes"
   Agent: ✅ Deleted
   \`\`\`

2. **Recreate** (via Setup Prerequisites):
   - Execute "Manual Trigger - Setup Prerequisites"
   - OR use AI chat: "create collection web-scrapes with 768 dimensions"

---

### Task 4: Backup Collection

**Create snapshot:**
\`\`\`bash
curl -X POST http://qdrant:6333/collections/web-scrapes/snapshots
\`\`\`

**List snapshots:**
\`\`\`bash
curl http://qdrant:6333/collections/web-scrapes/snapshots
\`\`\`

**Download snapshot:**
\`\`\`bash
curl -O http://qdrant:6333/collections/web-scrapes/snapshots/<snapshot-name>
\`\`\`

**Restore** (requires Qdrant API or restart):
\`\`\`bash
# Place snapshot in Qdrant storage directory
# Restart Qdrant service
\`\`\`

---

## Troubleshooting

### Error: "Collection already exists"

\`\`\`json
{
  "status": {
    "error": "Collection `web-scrapes` already exists"
  }
}
\`\`\`

**Solution:**
1. Check if this is the correct collection: `curl http://qdrant:6333/collections/web-scrapes`
2. If yes, no action needed
3. If you want to recreate:
   - Delete first: AI chat → "delete collection web-scrapes" → confirm
   - Then recreate via Setup Prerequisites

---

### Error: "Wrong vector dimension"

\`\`\`json
{
  "status": {
    "error": "Wrong vector dimension: expected 768, got 384"
  }
}
\`\`\`

**Cause**: Embedding model mismatch

**Solution:**
1. Check your embedding model:
   - `nomic-embed-text` = 768
   - `all-MiniLM-L6-v2` = 384
2. Create collection with matching dimension
3. OR use correct embedding model for collection

---

### Error: "No results found" in Search

**Possible causes:**
1. Collection is empty (no points)
2. Score threshold too high (0.5 → try 0.3)
3. Wrong embedding model (query ≠ indexed)
4. Collection not indexed yet

**Debug:**
\`\`\`bash
# Check point count
curl http://qdrant:6333/collections/web-scrapes/points/count

# Search without threshold
curl -X POST http://qdrant:6333/collections/web-scrapes/points/search \
  -H "Content-Type: application/json" \
  -d '{
    "vector": [...],
    "limit": 5,
    "with_payload": true
  }'
\`\`\`

---

### Error: "Collection not found"

\`\`\`json
{
  "status": {
    "error": "Collection `web-scrapes` not found"
  }
}
\`\`\`

**Solution:**
1. List collections: AI chat → "list all collections"
2. Create if missing: Execute "Setup Prerequisites"
3. Check spelling (case-sensitive!)

---

## Integration with Workflow 04

### Prerequisites

Before using **workflow 04** (Web Scrape → Qdrant RAG):

1. ✅ **Create `web-scrapes` collection**:
   - Use workflow 06 → "Setup Prerequisites"
   - Verify: AI chat → "list all collections"

2. ✅ **Ensure Ollama has nomic-embed-text**:
   \`\`\`bash
   docker exec ollama ollama list
   # Should show: nomic-embed-text
   \`\`\`

3. ✅ **Test embedding generation**:
   \`\`\`bash
   curl -X POST http://ollama:11434/api/embed \
     -d '{"model": "nomic-embed-text", "input": "test"}'
   \`\`\`

### Workflow 04 Flow

\`\`\`
User Input (URL) → Crawl4AI → Chunk → Embed → Store in web-scrapes
                                       ↓
                                 nomic-embed-text
                                      (768-dim)
\`\`\`

### Query Ingested Data

**Via AI Chat (workflow 06):**
\`\`\`
User: "Search web-scrapes for 'machine learning RAG best practices'"
\`\`\`

**Via Direct API:**
\`\`\`bash
# 1. Embed query
EMBEDDING=$(curl -s -X POST http://ollama:11434/api/embed \
  -d '{"model": "nomic-embed-text", "input": "machine learning RAG"}' \
  | jq -r '.embeddings[0]')

# 2. Search Qdrant
curl -X POST http://qdrant:6333/collections/web-scrapes/points/search \
  -H "Content-Type: application/json" \
  -d "{
    \"vector\": $EMBEDDING,
    \"limit\": 5,
    \"with_payload\": true,
    \"score_threshold\": 0.5
  }"
\`\`\`

---

## Best Practices

### ✅ DO

1. **Use Setup Prerequisites** for standard collections
2. **Match vector dimensions** to your embedding model
3. **Use Cosine distance** for text embeddings
4. **Backup before deletion** (create snapshot)
5. **Monitor collection health** regularly
6. **Use AI chat** for exploratory tasks
7. **Test search** after ingestion

### ❌ DON'T

1. **Don't hardcode dimensions** - check your model first
2. **Don't use Euclid for text** - always use Cosine
3. **Don't delete without backup** - snapshots are easy
4. **Don't mix embedding models** - query and indexed must match
5. **Don't ignore indexing status** - wait for full indexing
6. **Don't set threshold too low** - causes frequent re-indexing
7. **Don't expose Qdrant publicly** - use n8n as proxy

---

## Performance Tips

### Faster Search
- Increase `m` to 24-32
- Increase `ef_construct` to 150-200
- Wait for full indexing before querying
- Use SSD storage (not HDD)

### Lower Memory
- Decrease `m` to 8-12
- Decrease `ef_construct` to 50-80
- Use smaller vector dimensions if possible
- Set higher `indexing_threshold`

### Faster Ingestion
- Use batch inserts (100-1000 points)
- Disable `wait: true` for async inserts
- Set higher `indexing_threshold`
- Use parallel embedding generation

---

## API Quick Reference

\`\`\`bash
# List collections
GET http://qdrant:6333/collections

# Get collection info
GET http://qdrant:6333/collections/{name}

# Create collection
PUT http://qdrant:6333/collections/{name}
{"vectors": {"size": 768, "distance": "Cosine"}}

# Delete collection
DELETE http://qdrant:6333/collections/{name}

# Insert points
PUT http://qdrant:6333/collections/{name}/points
{"points": [{"id": "1", "vector": [...], "payload": {...}}]}

# Search
POST http://qdrant:6333/collections/{name}/points/search
{"vector": [...], "limit": 5, "with_payload": true}

# Count points
GET http://qdrant:6333/collections/{name}/points/count

# Create snapshot
POST http://qdrant:6333/collections/{name}/snapshots
\`\`\`

---

## Support

- **Qdrant Docs**: https://qdrant.tech/documentation/
- **n8n Community**: https://community.n8n.io
- **GeuseMaker**: Check README.md and docs/

---

## Summary

**🚀 Quick Start Checklist:**

1. ✅ Import workflow 06 into n8n
2. ✅ Execute "Manual Trigger - Setup Prerequisites"
3. ✅ Verify: AI chat → "list all collections" → see `web-scrapes`
4. ✅ Ready to use workflow 04 for web scraping!

**🎯 What You Created:**
- Collection: `web-scrapes`
- Dimensions: 768 (nomic-embed-text)
- Distance: Cosine
- Optimized HNSW config
- Ready for RAG ingestion

**🎉 You're all set!** Start scraping and storing web content with workflow 04.
