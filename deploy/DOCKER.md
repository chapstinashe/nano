# Docker setup from scratch

Run these steps on the machine where Docker Desktop is installed (Windows, macOS, or Linux).

## 1. Install Docker

1. Download and install [Docker Desktop](https://www.docker.com/products/docker-desktop/).
2. Start Docker Desktop and wait until it shows **Running**.
3. Verify:

```powershell
docker --version
docker compose version
```

## 2. Configure environment

From the project root (`rag-system`):

```powershell
cd c:\Users\tinas\projects\AI\nano\rag-system
Copy-Item .env.example .env
```

Edit `.env` and set at minimum:

| Variable | Purpose |
|----------|---------|
| `AZURE_OPENAI_API_KEY` | Chat completions |
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI endpoint URL |
| `AZURE_OPENAI_DEPLOYMENT` | Model deployment name |
| `COSMOS_ENDPOINT` | Cosmos DB account |
| `COSMOS_KEY` | Cosmos DB key |
| `AZURE_STORAGE_CONNECTION_STRING` | Blob storage for uploads/text |
| `JWT_SECRET_KEY` | Strong random secret (auth) |

**Docker-specific:** You do not need to set `RATE_LIMIT_STORAGE_URI` in `.env` — Compose sets `redis://redis:6379/0` automatically.

**Cosmos:** Enable **Vector Search for NoSQL API** on your Cosmos account before first run.

## 3. Prepare storage folders (first time)

```powershell
New-Item -ItemType Directory -Force -Path app\storage\uploads, app\storage\metadata, app\storage\texts, app\storage\chroma | Out-Null
```

## 4. Build images

```powershell
docker compose build
```

The first build downloads Python packages and may take several minutes (PyTorch + sentence-transformers).

> **Note:** Docker uses `requirements-docker.txt`, not `requirements.txt`. The local freeze file includes a Windows-only editable install that breaks Linux container builds.

## 5. Start services

Foreground (logs in terminal):

```powershell
docker compose up
```

Detached (background):

```powershell
docker compose up -d
```

Services:

| Service | Role | URL |
|---------|------|-----|
| `redis` | Rate limiting | internal only |
| `rag-api` | Flask API (gunicorn) | http://localhost:5000 |

## 6. Verify

```powershell
curl http://localhost:5000/api/health
```

Or open http://localhost:5000 in a browser.

View logs:

```powershell
docker compose logs -f rag-api
```

## 7. Stop / reset

Stop containers:

```powershell
docker compose down
```

Stop and remove volumes (Redis data + Hugging Face model cache):

```powershell
docker compose down -v
```

## 8. Rebuild after code changes

```powershell
docker compose up --build -d
```

## Troubleshooting

**Build fails on `pip install`**

- Ensure you are in `rag-system` (folder with `Dockerfile` and `docker-compose.yml`).
- Check network access for PyPI and Hugging Face.

**Container exits immediately**

```powershell
docker compose logs rag-api
```

Common causes: missing Cosmos/Azure env vars, Cosmos vector search not enabled, invalid `JWT_SECRET_KEY` when `AUTH_ENABLED=1`.

**Slow first request**

The embedding model downloads on first use into the `huggingface_cache` volume; later starts are faster.

**Port 5000 in use**

Change the host port in `docker-compose.yml`:

```yaml
ports:
  - "8080:5000"
```

Then use http://localhost:8080.
