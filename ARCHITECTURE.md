# AI Healthcare System Architecture

## Overall System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                AI Healthcare System                                 │
└─────────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────┐    ┌─────────────────┐    ┌─────────────────────────────────────┐
│   User Browser  │────│  Vercel (CDN)   │────│        ai-02-06.duckdns.org        │
│                 │    │   Next.js 15    │    │         + Let's Encrypt SSL         │
└─────────────────┘    │   React 19      │    └─────────────────────────────────────┘
                       │   TypeScript    │                        │
                       └─────────────────┘                        │
                                                                  │
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                            AWS EC2 (t3.medium)                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                          Docker Network                                    │   │
│  │                                                                             │   │
│  │  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                    │   │
│  │  │    Nginx    │────│   FastAPI   │────│ PostgreSQL  │                    │   │
│  │  │ :80, :443   │    │    :8000    │    │    :5432    │                    │   │
│  │  │ Reverse     │    │ Python 3.13 │    │ Primary DB  │                    │   │
│  │  │ Proxy       │    │ Uvicorn     │    │ Tortoise    │                    │   │
│  │  │ HTTPS       │    │ ASGI        │    │ ORM         │                    │   │
│  │  └─────────────┘    └─────────────┘    └─────────────┘                    │   │
│  │                              │                                             │   │
│  │                              │         ┌─────────────┐                    │   │
│  │                              └─────────│    Redis    │                    │   │
│  │                                        │    :6379    │                    │   │
│  │                                        │ Message     │                    │   │
│  │                                        │ Broker      │                    │   │
│  │                                        │ Cache       │                    │   │
│  │                                        └─────────────┘                    │   │
│  │                                                │                           │   │
│  │                                        ┌─────────────┐                    │   │
│  │                                        │ AI Worker   │                    │   │
│  │                                        │ OCR + RAG   │                    │   │
│  │                                        │ Pipeline    │                    │   │
│  │                                        │ Background  │                    │   │
│  │                                        │ Jobs        │                    │   │
│  │                                        └─────────────┘                    │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                        │
                    ┌───────────────────┼───────────────────┐
                    │                   │                   │
          ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
          │ NAVER CLOVA OCR │  │  OpenAI GPT-4o  │  │ Kakao OAuth 2.0 │
          │ Prescription    │  │ Medication      │  │   Social        │
          │ Text Extraction │  │ Guide Generator │  │   Authentication│
          └─────────────────┘  └─────────────────┘  └─────────────────┘
```

---

## Deployment Environment Configuration

### Frontend (Vercel)
- **Platform**: Vercel (Next.js optimized)
- **Framework**: Next.js 15 + React 19 + TypeScript
- **Deployment**: Automatic deployment on Git push
- **Domain**: Vercel-provided domain + custom domain integration

### Backend (AWS EC2)
- **Instance**: t3.medium (2 vCPU, 4GB RAM, 30GB EBS)
- **OS**: Ubuntu 22.04 LTS
- **Domain**: `ai-02-06.duckdns.org` (DuckDNS free domain)
- **SSL**: Let's Encrypt automatic renewal
- **Deployment**: GitHub Actions CI/CD

---

## Docker Container Configuration

### Production Stack (`docker-compose.prod.yml`)

| Service | Image | Port | Role | Resource Limit |
|---------|-------|------|------|----------------|
| **nginx** | nginx:alpine | 80, 443 | Reverse proxy, HTTPS termination | 64MB |
| **fastapi** | custom | 8000 | REST API server | 300MB |
| **ai-worker** | custom | - | AI inference background processing | 300MB |
| **postgres** | postgres:15-alpine | 5432 | Primary database | 256MB |
| **redis** | redis:alpine | 6379 | Message broker, cache | 128MB |

### Network Configuration
- **frontend**: nginx ↔ fastapi, ai-worker (external API access)
- **backend**: fastapi ↔ postgres, redis ↔ ai-worker (internal communication)

---

## FastAPI Backend Architecture

### Directory Structure
```
app/
├── apis/v1/              # API routers (RESTful endpoints)
│   ├── health_routers.py     # Health check
│   ├── oauth_routers.py      # Kakao OAuth authentication
│   ├── profile_routers.py    # User profile management
│   ├── medication_routers.py # Medication management
│   ├── intake_log_routers.py # Medication intake logs
│   ├── ocr_routers.py        # Prescription OCR
│   ├── chat_session_routers.py # Chat sessions
│   ├── message_routers.py    # Message management
│   └── challenge_routers.py  # Medication adherence challenges
├── core/                 # Core configuration
│   ├── config.py            # Pydantic Settings
│   └── logger.py            # Structured logging
├── middlewares/          # Middleware
│   ├── security.py          # Security (XSS, Path Traversal protection)
│   └── rate_limit.py        # IP-based request limiting
├── models/               # Tortoise ORM models
├── dtos/                 # Pydantic schemas (request/response)
├── services/             # Business logic
│   └── rag/                 # RAG pipeline (intent → rewrite → retrieval → generation)
├── repositories/         # Data access layer
├── dependencies/         # FastAPI dependency injection
├── utils/                # Utilities (JWT, security)
├── validators/           # Input validation
└── db/                   # DB initialization, migrations
    └── migrations/          # Aerich migration files
```

### Request Processing Flow
```
Client Request
    ↓
Nginx (HTTPS, Rate Limiting)
    ↓
FastAPI Middlewares
    ├── SecurityMiddleware (Attack pattern detection)
    ├── RateLimitMiddleware (IP-based request limiting)
    └── CORSMiddleware (CORS policy)
    ↓
API Router (v1)
    ↓
Service Layer (Business logic)
    ↓
Repository Layer (DB abstraction)
    ↓
Tortoise ORM
    ↓
PostgreSQL Database
```

---

## RAG Layer (app/services/rag/)

### Pipeline Flow
```
ChatModal
   │ POST /api/v1/messages/ask
   ▼
MessageService.ask_and_reply_with_owner_check
   │
   ▼
RAGPipeline.ask
   │
   ├─(1) IntentClassifier       키워드·규칙 기반 (LLM 미사용)
   │
   ├─(2) RAGGenerator.rewrite_query   history 포함, self-contained 쿼리 생성
   │                                    (OK / UNRESOLVABLE / FALLBACK)
   │
   ├─(3) EmbeddingProvider      SentenceTransformer (768d, ko-sroberta-multitask)
   │
   ├─(4) HybridRetriever        pgvector cosine 0.7 + 키워드 0.3
   │        │                   (검색 대상: medicine_chunk, medicine_info FK join)
   │        ▼
   │    medicine_chunk          HNSW(vector_cosine_ops, m=16, ef_construction=64)
   │
   └─(5) RAGGenerator.generate_chat_response
          OpenAI GPT-4o-mini (최근 3턴 history + 검색 context) → 응답
```

### Components

| File | Role |
|---|---|
| `pipeline.py` | 5-stage orchestration (intent → rewrite → embed → retrieve → generate) |
| `config.py` | `EMBEDDING_MODEL_NAME`, `EMBEDDING_DIMENSIONS` single source constants |
| `intent/classifier.py` | Keyword-rule based IntentType classification |
| `providers/sentence_transformer.py` | Local Korean embedding (L2 normalized) |
| `retrievers/hybrid.py` | pgvector + keyword hybrid search |
| `tools/` | Intent-specific tool routing (DB lookup / external API) |

### Medicine Data Schema

- `medicine_info`: Base drug data sourced from public API (DrugPrdtPrmsnInfoService07).
  Monthly incremental sync keyed by `item_seq` (UPSERT key).
- `medicine_chunk`: Section-level embedding chunks (13-value section enum).
  `embedding vector(768)` with HNSW cosine index.
- `medicine_ingredient`: Active-ingredient 1:N detail (public ingredient API).
- `data_sync_log`: Sync history tracking (full/incremental, success/failure).

### Data Ingestion Scripts (scripts/crawling/)

| Script | Purpose |
|---|---|
| `sync_medicine_data.py` | Production full/incremental sync (all ~43k rows). Runs via CLI `--full` or monthly cron. |
| `fetch_sample.py` | Local/CI sample loader. `--limit N` (default 50) caps the fetch, generates `medicine_chunk` rows, embeds with SentenceTransformer. `--skip-embed` keeps DB structure only. |
| `dump_medicine_data.sh` | DB dump helper for backup/share. |

Operational rule: `fetch_sample.py` is **local/CI only** and MUST NOT run on
production EC2. Production data is populated via `sync_medicine_data.py`.

### Model/Dimension Swap Procedure

1. Update both constants in `app/services/rag/config.py`
2. Add an Aerich migration altering `medicine_chunk.embedding` to the new `vector(N)`
3. Re-ingest:
   - Production: `sync_medicine_data.py --full` + re-embed chunks
   - Local: `fetch_sample.py --limit N`

---

## AI Worker Architecture

### Structure
```
ai_worker/
├── core/                 # Configuration and logging
├── tasks/                # Background task definitions
│   ├── ocr_tasks.py         # OCR processing tasks
│   └── embedding_tasks.py   # Embedding generation tasks
├── utils/                # AI utilities
│   ├── ocr.py              # CLOVA OCR integration
│   ├── chunker.py          # Data chunking
│   └── rag.py              # RAG pipeline
├── data/                 # Static data
│   └── medicines.json      # Medication information database
└── main.py               # Worker entry point
```

### RAG Pipeline
```
RAG Pipeline Processing Flow:

User        FastAPI      Redis       AI Worker    CLOVA OCR    OpenAI GPT-4o
 │             │           │             │             │             │
 │─────────────│──────────▶│             │             │             │
 │ Prescription│           │             │             │             │
 │ Image Upload│           │             │             │             │
 │             │───────────│────────────▶│             │             │
 │             │ OCR Task  │             │             │             │
 │             │ Queue Add │             │             │             │
 │             │           │─────────────│────────────▶│             │
 │             │           │ Task Receive│             │             │
 │             │           │             │─────────────│────────────▶│
 │             │           │             │ Image →     │             │
 │             │           │             │ Text Convert│             │
 │             │           │             │◀────────────│─────────────│
 │             │           │             │ Extracted   │             │
 │             │           │             │ Medicine    │             │
 │             │           │             │ Names       │             │
 │             │           │             │─────────────│────────────▶│
 │             │           │             │ medicines.  │             │
 │             │           │             │ json Match  │             │
 │             │           │             │─────────────│────────────▶│
 │             │           │             │ Text        │             │
 │             │           │             │ Chunking    │             │
 │             │           │             │─────────────│────────────▶│
 │             │           │             │ Medication  │             │
 │             │           │             │ Guide       │             │
 │             │           │             │ Request     │             │
 │             │           │             │◀────────────│─────────────│
 │             │           │             │ Personalized│             │
 │             │           │             │ Medication  │             │
 │             │           │             │ Guide       │             │
 │◀────────────│───────────│◀────────────│─────────────│─────────────│
 │ Medication  │           │ Result      │             │             │
 │ Guide       │           │ Return      │             │             │
 │ Response    │           │             │             │             │
```

---

## Security Architecture

### Authentication & Authorization
```
Kakao OAuth 2.0 Authentication Flow:

Client          FastAPI         Kakao OAuth      PostgreSQL
 │                 │                 │               │
 │─────────────────│────────────────▶│               │
 │ Kakao Login     │                 │               │
 │ Request         │                 │               │
 │                 │─────────────────│──────────────▶│
 │                 │ OAuth Auth Code │               │
 │                 │ Exchange        │               │
 │                 │◀────────────────│───────────────│
 │                 │ User Info       │               │
 │                 │ Return          │               │
 │                 │─────────────────│──────────────▶│
 │                 │ User Info       │ Store/Update  │
 │                 │ Store/Update    │               │
 │◀────────────────│─────────────────│───────────────│
 │ JWT Access      │                 │               │
 │ Token (60min) + │                 │               │
 │ Refresh Token   │                 │               │
 │ (14 days)       │                 │               │
 │                 │                 │               │
 │ ─ ─ ─ ─ ─ ─ ─ ─ Subsequent API Requests ─ ─ ─ ─ ─ ─ ─ ─ │
 │                 │                 │               │
 │─────────────────│────────────────▶│               │
 │ Authorization:  │                 │               │
 │ Bearer <token>  │                 │               │
 │                 │─────────────────│──────────────▶│
 │                 │ JWT Validation  │               │
 │                 │ & User Identity │               │
 │◀────────────────│─────────────────│───────────────│
 │ API Response    │                 │               │
```

### Security Layers
1. **Nginx**: HTTPS enforcement, request size limiting (10MB)
2. **SecurityMiddleware**:
   - Path Traversal attack prevention
   - XSS pattern detection and logging
   - Security header injection
3. **RateLimitMiddleware**:
   - GET: 200 req/60s per IP
   - POST/PATCH/DELETE: 30 req/60s per IP
   - Auth endpoints: 10 req/60s per IP
4. **JWT**: Short-lived Access Token + HttpOnly Refresh Token

---

## CI/CD Pipeline

### GitHub Actions Workflow
```yaml
# .github/workflows/deploy.yml
1. Test Phase:
   - Python 3.13 + PostgreSQL 15 environment
   - Dependency installation with uv
   - pytest test execution

2. Deploy Phase:
   - EC2 SSH connection
   - Git pull (latest main)
   - Docker Compose rebuild
   - Automatic migration execution
   - Health check verification

3. Health Check Phase:
   - API endpoint status verification
   - Nginx proxy status verification
```

### Deployment Automation
- `.github/workflows/deploy.yml` (CD): on `main` push — test gate → build & push image to ghcr
  (`:latest` + `:sha`) → keyless auth (WIF) + IAP SSH → VM pulls and restarts via compose →
  health check. The VM never builds images.
- `.github/workflows/checks.yml` (CI): Ruff / MyPy baseline gate / Bandit / pytest /
  frontend (ESLint · Vitest · npm audit · static build).
- TLS is terminated by Cloudflare (Tunnel) — there is no certbot/Let's Encrypt renewal step.

---

## Development Environment Setup

### Local Development
```bash
# Install dependencies
uv sync

# Run local stack
docker-compose up -d

# Run development server
uv run uvicorn app.main:app --reload
```

### Environment Variable Management
- `.env.example` (tracked): the single local template. Copy to `.env` and fill in real values.
- `.env` (untracked): local real values. Environment is selected by the `ENV` line, not by
  per-environment config bundles (the old `envs/` switch script was removed).
- Production: values live on the deploy target (VM-side `.env`) and in GitHub Actions secrets —
  never in the repository. Key reference: `envs/example.gcp-login.env`.

---

## Monitoring & Logging

### Logging Strategy
- **Structured Logging**: JSON format output
- **Level Classification**: DEBUG → INFO → WARNING → ERROR → CRITICAL
- **Security Considerations**: Personal information masking, token exclusion
- **Docker Logs**: Size limitations (50MB, 5 files)

### Health Checks
- **API**: `/api/v1/health` (includes DB connection status)
- **Nginx**: `/health` (proxy status)
- **Docker**: Health check configuration for each container

---

## Scalability Considerations

### Current Constraints (t3.medium)
- **CPU**: 2 vCPU (burstable)
- **Memory**: 4GB (container-level limits configured)
- **Storage**: 30GB EBS

### Scaling Strategies
1. **Vertical Scaling**: Larger EC2 instance types
2. **Horizontal Scaling**:
   - Application Load Balancer + multiple EC2 instances
   - RDS PostgreSQL (managed DB)
   - ElastiCache Redis (managed cache)
3. **Microservices**: Separate AI Worker as independent service

---

## Technology Stack Summary

| Layer | Technology | Version | Role |
|-------|------------|---------|------|
| **Frontend** | Next.js | 15 | React-based SPA |
| **Backend** | FastAPI | 0.128+ | Python async API server |
| **Database** | PostgreSQL | 15 | Relational database |
| **Cache/Queue** | Redis | Alpine | Message broker, cache |
| **ORM** | Tortoise ORM | 0.25+ | Async Python ORM |
| **Web Server** | Nginx | Alpine | Reverse proxy, HTTPS |
| **Container** | Docker | - | Containerization |
| **Orchestration** | Docker Compose | - | Multi-container management |
| **CI/CD** | GitHub Actions | - | Automated deployment |
| **Monitoring** | Docker Logs | - | Log collection |
| **SSL** | Let's Encrypt | - | Free SSL certificates |
| **DNS** | DuckDNS | - | Free dynamic DNS |

---

## Additional Documentation

- [README.md](./README.md): Project overview and execution guide
- [SYSTEM_DESIGN.md](docs/SYSTEM_DESIGN_KR.md): Technical design specifications
- [docs/01_DB_MIGRATION_GUIDE.md](./docs/01_DB_MIGRATION_GUIDE.md): Database migration guide
- [docs/02_ENV_AND_CICD_GUIDE.md](./docs/02_ENV_AND_CICD_GUIDE.md): Environment setup and CI/CD
- [docs/OCR_FLOW.md](docs/OCR_FLOW.md): OCR processing flow
- [PLAN.md](./PLAN.md): Development planning and architecture design
