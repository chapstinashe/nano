# Flask RAG System

A modular Retrieval-Augmented Generation (RAG) backend built with Flask, Azure Cosmos DB (vectors + metadata), sentence-transformers, and Azure OpenAI.

## Architecture

```
Upload / DB → Parser → Chunking → Embeddings → Cosmos DB (rag_chunks)
User Query → Embed → Vector search (Cosmos) → Prompt Builder → Azure OpenAI (SSE)
```

Components are decoupled: ingestion, retrieval, embeddings, LLM calls, and storage are independent modules.

## Quick Start

### 1. Setup

```bash
cd rag-system
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
copy .env.example .env        # then fill in Azure OpenAI credentials
```

### 2. Run

```bash
python run.py
```

Server starts at `http://localhost:5000`.

### 3. Docker

See **[deploy/DOCKER.md](deploy/DOCKER.md)** for full setup from scratch (install Docker, `.env`, build, run, troubleshoot).

```bash
docker compose build
docker compose up -d
```

Uses `requirements-docker.txt` (not `requirements.txt`) so the image builds without local-only packages.

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Health check |
| POST | `/api/ingest/files` | Upload and ingest a file |
| POST | `/api/ingest/database` | Ingest database tables |
| POST | `/api/search` | Semantic search |
| POST | `/api/chat/stream` | RAG chat with SSE streaming |
| GET | `/api/documents` | List ingested documents |
| DELETE | `/api/documents/<id>` | Delete a document |

## Usage Examples

### Upload a file

```bash
curl -X POST http://localhost:5000/api/ingest/files \
  -F "file=@document.pdf"
```

### Search

```bash
curl -X POST http://localhost:5000/api/search \
  -H "Content-Type: application/json" \
  -d "{\"query\": \"What is the refund policy?\", \"top_k\": 5}"
```

### Stream chat

```bash
curl -X POST http://localhost:5000/api/chat/stream \
  -H "Content-Type: application/json" \
  -d "{\"query\": \"Summarize the document\"}"
```

### Ingest database

```bash
curl -X POST http://localhost:5000/api/ingest/database \
  -H "Content-Type: application/json" \
  -d "{
    \"db_type\": \"sqlite\",
    \"connection_string\": \"sqlite:///./data.db\",
    \"tables\": [\"products\"]
  }"
```

## Environment Variables

See `.env.example` for all required variables.

**Required for vectors + auth:** Cosmos DB (`COSMOS_ENDPOINT`, `COSMOS_KEY`) and vector container (`COSMOS_VECTORS_CONTAINER=rag_chunks`).

**Azure setup (one-time):**

1. In the Cosmos account → **Features** → enable **Vector Search for NoSQL API** (or CLI: `EnableNoSQLVectorSearch`).
2. On first app start, the `rag_chunks` container is created with a 384-dimension cosine index (matches `all-MiniLM-L6-v2`).
3. **Re-upload documents** after migrating from Chroma — old local Chroma data is not migrated automatically.

```
COSMOS_ENDPOINT=
COSMOS_KEY=
COSMOS_VECTORS_CONTAINER=rag_chunks
EMBEDDING_DIMENSIONS=384
AZURE_OPENAI_API_KEY=
AZURE_OPENAI_ENDPOINT=
AZURE_OPENAI_DEPLOYMENT=
AZURE_OPENAI_API_VERSION=
```

## Supported Formats

- **Files:** PDF, DOCX, TXT, CSV, XLSX
- **Databases:** PostgreSQL, MySQL, MSSQL, SQLite

## Tests

```bash
pip install pytest
pytest tests/ -v
```

## Project Structure

```
app/
├── api/           # Flask route blueprints
├── core/          # Config, logging, security
├── rag/           # Embeddings, Cosmos vector search, retriever, LLM
├── repositories/  # Cosmos vector + document repositories
├── ingestion/     # File & database ingestors, parsers, connectors
├── services/      # Business logic layer
├── storage/       # Local uploads + extracted text (vectors live in Cosmos)
├── models/        # Data schemas
└── utils/         # Helpers
```
