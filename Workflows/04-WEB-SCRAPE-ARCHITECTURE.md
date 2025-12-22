# Web Scrape to Qdrant RAG Ingestion - Architecture Guide

## Overview

This workflow implements a **production-ready RAG ingestion pipeline** that combines:
- 🤖 **AI Agent** with natural language chat interface
- 🕷️ **Crawl4AI 2.0.2+** with latest parameters and anti-bot features
- 🧩 **Advanced chunking** with paragraph/sentence-aware boundaries and 200-char overlap
- 🎯 **Qdrant best practices** with comprehensive metadata enrichment
- ✅ **Validation at every step** with robust error handling
- 🔄 **Retry logic** for network resilience

## Workflow Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      Chat Trigger (n8n Hosted Chat)                     │
│                Natural language URL/topic input interface                │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│              AI Agent: URL Parser & Validator (Qwen 2.5)                │
│        Validates URLs, extracts metadata, handles topics gracefully     │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    Validate & Extract URL (Code Node)                   │
│     Multi-strategy extraction: agent response → regex → error handling  │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                                 ▼
                        ┌────────┴────────┐
                        │   IF: Valid?    │
                        └────────┬────────┘
                    YES          │          NO
                    ▼            │            ▼
         ┌──────────────────┐   │   ┌────────────────────┐
         │  Crawl4AI Scrape │   │   │ Handle Validation  │
         │  (HTTP Request)  │   │   │ Error (Code Node)  │
         └────────┬─────────┘   │   └────────────────────┘
                  │             │
                  ▼             │
         ┌──────────────────┐  │
         │ Validate & Enrich│  │
         │ Metadata (Code)  │  │
         └────────┬─────────┘  │
                  │            │
                  ▼            │
         ┌──────────────────┐ │
         │ Advanced Chunking│ │
         │ with Overlap     │ │
         │ (Code Node)      │ │
         └────────┬─────────┘ │
                  │           │
                  ▼           │
         ┌──────────────────┐│
         │ Generate Embedds ││
         │ (Ollama/nomic)   ││
         └────────┬─────────┘│
                  │          │
                  ▼          │
         ┌──────────────────┐
         │ Prepare Qdrant   │
         │ Point (Code)     │
         └────────┬─────────┘
                  │
                  ▼
         ┌──────────────────┐
         │ Store in Qdrant  │
         │ (HTTP Request)   │
         └────────┬─────────┘
                  │
                  ▼
         ┌──────────────────┐
         │ Aggregate Results│
         │ & Summary (Code) │
         └──────────────────┘
```

## Node-by-Node Breakdown

### 1. Chat Trigger - URL/Topic Input
**Type**: `@n8n/n8n-nodes-langchain.chatTrigger` (v1.4)
**Purpose**: Modern AI chat interface for natural language input

**Features**:
- Hosted chat mode with custom branding
- User-friendly input placeholder
- `responseMode: lastNode` - returns final aggregated summary

**Input Examples**:
- `https://example.com/article-about-ai`
- `machine learning` (topic - will be gracefully rejected)
- `What is RAG?` (natural language)

---

### 2. URL Parser & Validator Agent
**Type**: `@n8n/n8n-nodes-langchain.agent` (v1.7)
**Model**: Qwen 2.5 1.5B Instruct (via Ollama)

**System Prompt**:
- Extracts and validates URLs
- Distinguishes between URLs and topics
- Returns structured JSON: `{"type": "url"|"topic", "content": "...", "domain": "...", "validated": true|false}`

**AI Agent Best Practices**:
- Temperature: 0.1 (deterministic)
- Max iterations: 3
- Concise, factual responses
- Structured output for downstream processing

---

### 3. Validate & Extract URL (Code Node)
**Purpose**: Multi-strategy URL extraction with fallbacks

**Extraction Strategies** (in order):
1. Parse JSON from AI agent response
2. Regex extraction: `/(https?:\/\/[^\s]+)/gi`
3. Topic detection (if no URL found)
4. Error handling for malformed inputs

**Output Fields**:
- `type`: "url" | "topic" | "error"
- `url`: Extracted or original input
- `domain`: Hostname (for URLs)
- `validated`: Boolean
- `status`: "ready_for_scraping" | "topic_only" | "validation_failed"

---

### 4. Check: Is Valid URL? (If Node)
**Type**: `n8n-nodes-base.if` (v2.2)

**Conditions** (AND combinator):
- `type === "url"`
- `validated === true`

**Routing**:
- ✅ **TRUE** → Crawl4AI Scrape Website
- ❌ **FALSE** → Handle Validation Error

---

### 5. Crawl4AI - Scrape Website (HTTP Request)
**Endpoint**: `http://crawl4ai:11235/crawl`
**Latest Crawl4AI 2.0.2+ Parameters**:

```json
{
  "bypass_cache": true,
  "extract_markdown": true,           // Prefer markdown for clean text
  "extract_links": true,               // Extract all hyperlinks
  "wait_for": "networkidle",           // Wait for JS to settle
  "screenshot": false,                 // Disable for performance
  "remove_overlay_elements": true,     // NEW: Remove modals, popups
  "process_iframes": false,            // Skip iframes for speed
  "timeout": 45000,                    // 45s timeout
  "word_count_threshold": 100,         // Min content threshold
  "excluded_tags": ["nav", "footer", "header", "aside", "script", "style"],
  "remove_forms": true,                // NEW: Clean up form elements
  "user_agent": "Mozilla/5.0 (compatible; RAG-Bot/1.0)"  // Custom UA
}
```

**Resilience**:
- Retry on fail: 3 attempts
- Wait between retries: 5s
- Follow redirects: max 5
- Total timeout: 60s

---

### 6. Validate & Enrich Metadata (Code Node)
**Purpose**: Validate scrape response and enrich with comprehensive metadata

**Validation Checks**:
1. Check for Crawl4AI errors (`error`, `success === false`)
2. Validate content length (minimum 100 chars)
3. Extract metadata with robust fallbacks

**Metadata Enrichment**:
- **Core**: title, description, language, author, published_date
- **Keywords**: Extract and limit to top 10
- **Statistics**: word count, reading time (200 words/min)
- **Quality metrics**: `content_quality` object with readability scoring

**Content Preference Order**:
1. Markdown (cleanest)
2. HTML (with tags)
3. Text (fallback)

**Quality Scoring**:
- **High**: > 500 words
- **Medium**: 200-500 words
- **Low**: 100-200 words

---

### 7. Advanced Chunking with Overlap (Code Node)
**Purpose**: Multi-strategy chunking optimized for RAG retrieval

**Parameters**:
- **Chunk size**: 1200 chars (optimal for 768-dim embeddings)
- **Overlap**: 200 chars (16.7% - ensures context continuity)
- **Minimum chunk**: 50 chars

**Chunking Strategies** (fallback chain):

#### Strategy 1: Paragraph-Aware (Preferred)
- Splits on `\n\n+` (paragraph boundaries)
- Preserves semantic coherence
- Adds overlap from previous chunk
- Boundary type: `paragraph`

#### Strategy 2: Sentence-Aware (Long Paragraphs)
- Triggered when paragraph > 1.5x chunk size
- Splits on sentence boundaries: `/[^.!?]+[.!?]+/g`
- Maintains readability
- Boundary type: `sentence`

#### Strategy 3: Sliding Window (Fallback)
- Fixed-offset chunking if strategies 1-2 fail
- Stride: `chunkSize - chunkOverlap` (1000 chars)
- Boundary type: `fixed_offset`

**Chunk Metadata**:
- `chunk_index`: Position in sequence
- `total_chunks`: Total from document
- `chunk_size`: Actual char count
- `chunk_method`: Strategy used
- `boundary_type`: Where split occurred
- `chunk_word_count`: Words in chunk
- `chunk_density`: Words/chars ratio

---

### 8. Generate Embeddings (Ollama)
**Endpoint**: `http://ollama:11434/api/embed`
**Model**: `nomic-embed-text` (768 dimensions)

**Request**:
```json
{
  "model": "nomic-embed-text",
  "input": "<chunk text>",
  "options": {
    "temperature": 0  // Deterministic embeddings
  }
}
```

**Why nomic-embed-text?**
- Best open-source embedding model for RAG
- 768 dimensions (optimal for semantic search)
- Outperforms sentence-transformers on MTEB benchmarks
- Fast inference on CPU

**Resilience**:
- Retry: 3 attempts
- Wait: 3s between retries
- Timeout: 30s per request

---

### 9. Prepare Qdrant Point (Code Node)
**Purpose**: Validate embedding and create Qdrant-optimized payload

**Embedding Validation**:
1. Extract from multiple response formats (handles Ollama variations)
2. Validate array type and non-empty
3. Check dimension === 768 (warn if mismatch)
4. Validate no NaN or non-numeric values

**ID Generation** (collision-resistant):
```javascript
`${sanitizedDomain}_${timestamp}_c${chunkIndex}_${randomSuffix}`
// Example: example_com_1734652800000_c0_a3b4c5d
```

**Qdrant Payload Structure** (Best Practices):

```json
{
  // === Core Content (full-text indexed) ===
  "text": "...",
  "title": "...",
  "description": "...",

  // === Source Identification (filterable) ===
  "url": "https://...",
  "domain": "example.com",
  "canonical_url": "https://...",

  // === Document Metadata (filterable) ===
  "language": "en",
  "author": "John Doe",
  "published_date": "2025-01-15",
  "keywords": ["AI", "RAG"],

  // === Chunk Position (filterable for navigation) ===
  "chunk_index": 0,
  "total_chunks": 5,
  "chunk_method": "paragraph_aware",
  "boundary_type": "paragraph",

  // === Content Statistics (filterable for quality) ===
  "chunk_size": 1200,
  "chunk_word_count": 185,
  "chunk_density": 0.1542,
  "word_count": 1500,
  "reading_time_minutes": 8,

  // === Quality Metrics (filterable) ===
  "content_quality": {
    "has_sufficient_text": true,
    "has_metadata": true,
    "has_links": true,
    "readability_score": "high"
  },

  // === Timestamps (filterable for recency) ===
  "scraped_at": "2025-12-20T12:00:00Z",
  "stored_at": "2025-12-20T12:01:00Z",

  // === Technical Metadata ===
  "embedding_model": "nomic-embed-text",
  "embedding_dimension": 768,
  "source_type": "web_scrape",
  "ingestion_method": "n8n_ai_agent",
  "ingestion_version": "2.0",

  // === Additional Context (nested, non-filterable) ===
  "_metadata": {
    "chunk_hash": "a3b4c5d6e7f8",
    "original_content_length": 1500,
    "extraction_confidence": "high"
  }
}
```

**Qdrant Best Practices Applied**:
✅ Flat structure for filterable fields
✅ Nested objects for non-filterable metadata
✅ Consistent data types (no mixed types)
✅ Comprehensive indexable fields for advanced filtering
✅ Unique, deterministic IDs with collision avoidance

---

### 10. Store in Qdrant (HTTP Request)
**Endpoint**: `http://qdrant:6333/collections/web-scrapes/points`
**Method**: `PUT`

**Request Body**:
```json
{
  "points": [{
    "id": "...",
    "vector": [0.123, -0.456, ...],  // 768-dim
    "payload": { /* comprehensive metadata */ }
  }],
  "wait": true  // IMPORTANT: Wait for consistency
}
```

**Why `wait: true`?**
- Ensures point is indexed before response
- Prevents read-after-write issues
- Guarantees consistency for immediate queries

**Resilience**:
- Retry: 3 attempts
- Wait: 2s between retries
- Timeout: 30s per request

---

### 11. Aggregate Results & Summary (Code Node)
**Purpose**: Aggregate all storage results and provide comprehensive summary

**Success Detection**:
- Checks for: `status === "ok"`, `result.status === "ok"`, `json.payload`, or `json.time` (execution time)
- Assumes success if no clear errors

**Aggregate Statistics**:
- Total/successful/failed chunks
- Success rate percentage
- Total embedded words
- Average chunk size
- Unique domains processed

**Response Message** (formatted Markdown):
```
✅ Successfully ingested 5/5 chunks from https://example.com/article into Qdrant!

📊 Content Statistics:
• Source: 1500 words (~8 min read)
• Embedded: 925 words across 5 chunks
• Average chunk: 185 characters

🏷️ Metadata:
• Title: Example Article
• Domain: example.com
• Language: en
• Quality: high

🔧 Technical:
• Embedding Model: nomic-embed-text (768d)
• Chunking: paragraph_aware
• Collection: web-scrapes

🎉 All chunks stored successfully!
```

---

### 12. Handle Validation Error (Code Node)
**Purpose**: Graceful error handling with helpful messages

**Error Types**:
1. **Topic-only input**: Explains workflow is for URLs, suggests alternatives
2. **Invalid URL**: Shows format requirements with examples
3. **Generic error**: Provides troubleshooting guidance

**Response Format**:
```
❌ URL Validation Failed

Input: "invalid-url"
Error: Invalid URL format

💡 Valid URL format:
• Must start with http:// or https://
• Example: https://example.com/page
• Ensure URL is properly formatted
```

---

## Key Features

### 1. AI-Powered Natural Language Interface
- Users can input URLs in natural language
- AI agent handles URL extraction and validation
- Graceful handling of non-URL inputs (topics, questions)

### 2. Latest Crawl4AI 2.0.2+ Parameters
- `remove_overlay_elements`: Removes popups, modals, cookie banners
- `remove_forms`: Cleans form elements for better content
- `excluded_tags`: Removes navigation, footers, scripts
- Custom user agent for bot detection avoidance
- Network idle waiting for JavaScript-heavy sites

### 3. Advanced Multi-Strategy Chunking
- **Paragraph-aware**: Preserves semantic boundaries
- **Sentence-aware**: Handles long paragraphs intelligently
- **Sliding window**: Fallback for edge cases
- **200-char overlap**: Ensures context continuity across chunks
- **1200-char chunks**: Optimal for 768-dim embeddings

### 4. Qdrant Best Practices
- Flat structure for all filterable fields
- Comprehensive metadata enrichment (25+ fields)
- Nested `_metadata` for non-filterable context
- Unique, collision-resistant IDs
- `wait: true` for consistency guarantees

### 5. Validation at Every Step
- **URL validation**: Format, protocol, domain extraction
- **Scrape validation**: Content length, error detection
- **Embedding validation**: Dimension check, NaN detection
- **Storage validation**: Success/failure tracking
- **Comprehensive error handling**: Graceful degradation

### 6. Production-Ready Resilience
- **Retry logic**: 3 attempts for all HTTP requests
- **Exponential backoff**: 2-5s wait between retries
- **Timeout management**: Appropriate timeouts per step
- **Error propagation**: Clear error messages at each stage
- **Progress tracking**: Chunk-level success/failure reporting

---

## Usage Examples

### Example 1: Scrape a Blog Post
**Input**: `https://example.com/blog/introduction-to-rag`

**Workflow Execution**:
1. AI agent validates URL ✅
2. Crawl4AI scrapes content (2500 words)
3. Chunks into 3 pieces (paragraph-aware)
4. Generates 3x 768-dim embeddings
5. Stores 3 points in Qdrant

**Result**:
```
✅ Successfully ingested 3/3 chunks from https://example.com/blog/introduction-to-rag
📊 Source: 2500 words (~13 min read)
🏷️ Title: Introduction to RAG
```

### Example 2: Invalid Input (Topic)
**Input**: `machine learning`

**Workflow Execution**:
1. AI agent detects topic (not URL)
2. Routes to error handler
3. Returns helpful message

**Result**:
```
ℹ️ Topic-only input detected: "machine learning"

This workflow is designed to scrape and store web content.
💡 Provide a URL to scrape content
```

### Example 3: Malformed URL
**Input**: `not-a-valid-url`

**Workflow Execution**:
1. AI agent attempts parsing
2. URL validation fails
3. Error handler provides guidance

**Result**:
```
❌ URL Validation Failed
💡 Must start with http:// or https://
Example: https://example.com/page
```

---

## Qdrant Collection Setup

Before using this workflow, ensure the `web-scrapes` collection exists:

```python
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

client = QdrantClient(url="http://qdrant:6333")

client.create_collection(
    collection_name="web-scrapes",
    vectors_config=VectorParams(
        size=768,  # nomic-embed-text dimension
        distance=Distance.COSINE
    )
)
```

**Recommended Indexes** (for filtering):
```python
from qdrant_client.models import PayloadSchemaType

# Index frequently filtered fields
client.create_payload_index(
    collection_name="web-scrapes",
    field_name="domain",
    field_schema=PayloadSchemaType.KEYWORD
)

client.create_payload_index(
    collection_name="web-scrapes",
    field_name="language",
    field_schema=PayloadSchemaType.KEYWORD
)

client.create_payload_index(
    collection_name="web-scrapes",
    field_name="scraped_at",
    field_schema=PayloadSchemaType.DATETIME
)
```

---

## Query Examples

### Example 1: Semantic Search
```python
results = client.search(
    collection_name="web-scrapes",
    query_vector=embedding,  # From your query
    limit=5
)
```

### Example 2: Filtered Search (by Domain)
```python
from qdrant_client.models import Filter, FieldCondition, MatchValue

results = client.search(
    collection_name="web-scrapes",
    query_vector=embedding,
    query_filter=Filter(
        must=[
            FieldCondition(
                key="domain",
                match=MatchValue(value="example.com")
            )
        ]
    ),
    limit=5
)
```

### Example 3: Filtered Search (by Quality)
```python
results = client.search(
    collection_name="web-scrapes",
    query_vector=embedding,
    query_filter=Filter(
        must=[
            FieldCondition(
                key="content_quality.readability_score",
                match=MatchValue(value="high")
            ),
            FieldCondition(
                key="word_count",
                range={"gte": 500}  # Minimum 500 words
            )
        ]
    ),
    limit=5
)
```

### Example 4: Recency Filter (Last 7 Days)
```python
from datetime import datetime, timedelta

week_ago = (datetime.now() - timedelta(days=7)).isoformat()

results = client.search(
    collection_name="web-scrapes",
    query_vector=embedding,
    query_filter=Filter(
        must=[
            FieldCondition(
                key="scraped_at",
                range={"gte": week_ago}
            )
        ]
    ),
    limit=5
)
```

---

## Performance Considerations

### Throughput
- **Single URL**: 30-60 seconds (depending on page size)
- **Bottlenecks**: Crawl4AI scraping, embedding generation
- **Optimization**: Use batch embedding for multiple chunks

### Scaling
- **Horizontal**: Run multiple n8n instances
- **Vertical**: Increase Ollama CPU/GPU resources
- **Queue-based**: Use n8n queue mode for high volume

### Cost Optimization
- **Crawl4AI**: Self-hosted, free (CPU/RAM cost)
- **Ollama**: Self-hosted, free (CPU/GPU cost)
- **Qdrant**: Self-hosted, free (disk/RAM cost)
- **n8n**: Self-hosted, free (minimal overhead)

**Total Cost**: $0 (infrastructure only)

---

## Troubleshooting

### Issue: Crawl4AI Returns Empty Content
**Causes**:
- JavaScript-heavy site (wait_for not sufficient)
- Bot detection (IP blocked)
- Authentication required

**Solutions**:
1. Increase `timeout` to 60000ms
2. Change `user_agent` to different browser
3. Add custom headers (cookies, auth tokens)
4. Use proxy/VPN

### Issue: Embeddings Dimension Mismatch
**Causes**:
- Wrong Ollama model
- Model not pulled

**Solutions**:
```bash
ollama pull nomic-embed-text
ollama list  # Verify model exists
```

### Issue: Qdrant Storage Fails
**Causes**:
- Collection doesn't exist
- Dimension mismatch (768 expected)
- Qdrant out of disk space

**Solutions**:
1. Create collection (see setup above)
2. Verify vector config matches 768
3. Check Qdrant disk usage: `df -h`

### Issue: Chunking Produces Too Many Chunks
**Causes**:
- Very long document (10,000+ words)
- Chunk size too small

**Solutions**:
1. Increase `chunkSize` to 1500 or 2000
2. Pre-filter content (remove boilerplate)
3. Adjust `chunkOverlap` to reduce redundancy

---

## Future Enhancements

### Planned Features
1. **Batch Processing**: Upload CSV of URLs for batch scraping
2. **Scheduled Refresh**: Periodic re-scraping for content updates
3. **Deduplication**: Check if URL already exists before scraping
4. **Multi-Language**: Automatic language detection and translation
5. **PDF Support**: Extract and chunk PDF documents
6. **Image OCR**: Extract text from embedded images
7. **Custom Chunking Strategies**: Regex-based, topic-based
8. **Webhook Integration**: Trigger scraping from external systems

### Advanced Configurations
- **Custom embedding models**: Support for OpenAI, Cohere
- **Custom chunking logic**: Semantic chunking with LLMs
- **Metadata extraction**: LLM-powered entity extraction
- **Quality filtering**: Auto-reject low-quality content

---

## Version History

### v2.0 (Current)
- ✅ AI agent-powered chat interface
- ✅ Latest Crawl4AI 2.0.2+ parameters
- ✅ Advanced multi-strategy chunking
- ✅ Qdrant best practices implementation
- ✅ Comprehensive validation at every step
- ✅ Production-ready error handling
- ✅ Detailed summary reporting

### v1.0 (Legacy)
- Basic URL scraping
- Simple fixed-size chunking
- Minimal metadata

---

## License

MIT License - Free to use and modify

## Support

For issues or questions:
- GeuseMaker GitHub: https://github.com/yourusername/geusemaker
- n8n Community: https://community.n8n.io
- Qdrant Discord: https://discord.gg/qdrant
