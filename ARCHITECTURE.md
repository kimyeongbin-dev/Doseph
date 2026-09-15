# AI Healthcare System Architecture

## Overall System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                AI Healthcare System                                 │
└─────────────────────────────────────────────────────────────────────────────────────┘

                         ┌─────────────────────────┐
                         │      User Browser       │
                         └───────────┬─────────────┘
                                     │
                   ┌─────────────────┴──────────────────┐
                   │            Cloudflare              │  TLS terminates here
                   │  doseph.com          api.doseph.com│
                   │  (Pages: static)     (Tunnel)      │
                   └───────┬────────────────────┬───────┘
                           │                    │
              ┌────────────┴──────────┐         │ outbound tunnel
              │  Next.js 16 / React19 │         │ (no inbound ports)
              │  JavaScript (JSX)     │         │
              │  output: 'export'     │         │
              │  -> static assets     │         │
              └───────────────────────┘         │
                                                │
        ┌───────────────────────────────────────┴─────────────────────────┐
        │                 GCP Compute Engine e2-micro (us-west1-b)        │
        │  ┌───────────────────────────────────────────────────────────┐  │
        │  │                 Docker network "web"                      │  │
        │  │   ┌──────────────┐        ┌──────────────────────────┐    │  │
        │  │   │ cloudflared  │───────▶│  FastAPI :8000           │    │  │
        │  │   │ (tunnel)     │        │  Python 3.13 / Uvicorn   │    │  │
        │  │   └──────────────┘        │  Tortoise ORM            │    │  │
        │  │                           └────────────┬─────────────┘    │  │
        │  │   ┌──────────────┐                     │                  │  │
        │  │   │ migrate      │  one-shot           │                  │  │
        │  │   │ aerich upgrade│  (before API)      │                  │  │
        │  │   └──────────────┘                     │                  │  │
        │  └────────────────────────────────────────┼──────────────────┘  │
        └───────────────────────────────────────────┼─────────────────────┘
                                                    │ TLS
                                       ┌────────────┴──────────────┐
                                       │  Neon PostgreSQL          │
                                       │  (managed, pgvector)      │
                                       │  us-west-2                │
                                       └───────────────────────────┘

   External services (called by the backend):
   ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
   │ NAVER CLOVA OCR │  │     OpenAI      │  │ Kakao OAuth 2.0 │
   │ Prescription    │  │ Guide / RAG     │  │ Identity        │
   │ Text Extraction │  │ Generation      │  │ Provider (IdP)  │
   └─────────────────┘  └─────────────────┘  └─────────────────┘

   Note: redis + ai-worker (OCR/RAG background jobs) run in the **local** stack.
   The deployed "login path" stack omits them — see Docker Container Configuration.
```

---

## Deployment Environment Configuration

### Frontend (Cloudflare Pages)
- **Platform**: Cloudflare Pages (static hosting + CDN)
- **Framework**: Next.js 16 + React 19, **JavaScript (JSX)** — no TypeScript
- **Build**: `output: 'export'` static export (no Node server, no `rewrites` proxy)
- **Domain**: `doseph.com`
- **Deployment**: Git-connected — the `production` branch publishes the public site
  (`main` is used for backend CD and admin previews, so an FE-only change pushes `production`
  and avoids a backend redeploy)

### Backend (GCP Compute Engine)
- **Instance**: e2-micro, `us-west1-b` (Always Free tier)
- **Runtime**: Docker Compose (`docker-compose.gcp-login.yml`)
- **Domain**: `api.doseph.com`
- **Ingress**: **Cloudflare Tunnel** (`cloudflared`) — TLS terminates at Cloudflare.
  The VM has **zero inbound ports**; the tunnel is an outbound connection.
  There is no nginx and no certbot/Let's Encrypt renewal step.
- **Deployment**: GitHub Actions — build image in CI, push to ghcr, then pull on the VM
  (the VM never builds). Auth is keyless via WIF; the SSH hop goes through IAP.

### Database (Neon)
- **Managed PostgreSQL** with `pgvector`, region `us-west-2` (co-located with the VM region
  to keep VM↔DB latency low)
- TLS required (`DB_SSL=true`); schema is applied by a one-shot `migrate` service
  (`aerich upgrade`) that runs before the API starts.

---

## Docker Container Configuration

### Production Stack (`docker-compose.gcp-login.yml`)

Minimal "login path" stack sized for an e2-micro (1GB RAM) free instance.

| Service | Image | Port | Role |
|---------|-------|------|------|
| **fastapi** | `ghcr.io/kimyeongbin-dev/doseph-fastapi:${DOSEPH_IMAGE_TAG}` | 8000 (internal only) | REST API. Single uvicorn worker — two workers OOM-crashloop on 1GB |
| **migrate** | same image | - | One-shot `aerich upgrade` before the API starts (prevents schema drift) |
| **cloudflared** | `cloudflare/cloudflared` | - | Outbound tunnel to Cloudflare; TLS termination |

Not deployed in this stack: **postgres** (Neon is managed), **redis** and **ai-worker**
(the login path needs neither — APScheduler runs in-process), **nginx** (Cloudflare + tunnel
replace it).

### Local Stack (`docker-compose.yml`)

| Service | Port | Role |
|---------|------|------|
| **postgres** | 5432 | pgvector-enabled database |
| **redis** | 6379 | RQ broker, cache |
| **fastapi** | 8000 | REST API |
| **ai-worker** | - | OCR / RAG background jobs |

**No nginx locally.** The frontend (`:3000`) calls the API (`:8000`) **directly, cross-origin**,
which mirrors the production "independent API" topology (dev/prod parity). The backend allows
the local origin with credentials via CORS.

### Network Configuration
- **Production**: one `web` bridge network — `cloudflared` → `fastapi`. No inbound ports.
- **Local**: `frontend` (outbound external APIs: OAuth/OpenAI) and `backend`
  (fastapi ↔ postgres/redis ↔ ai-worker).

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
Cloudflare edge (TLS termination, WAF managed ruleset)
    ↓
cloudflared tunnel  → the VM exposes no inbound port
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

> 🔴 **이 절(파이프라인·스키마·교체 절차)과 아래 "AI Worker Architecture" 절은 낡았다 — 근거로 인용하지 말 것.**
> 서비스가 아직 **로그인 경로 안정화 구간**이라 RAG 계열은 의도적으로 뒤에 둔 상태다(2026-09-15 판단).
> 이 문서는 `CLAUDE.md` §4.1 이 *"여기 정의된 구조를 엄격히 따르라"* 고 지시하는 대상이므로,
> **따르면 안 되는 절**임을 여기 명시한다.
>
> | 이 절이 말하는 것 | 실측 (2026-09-15) |
> |---|---|
> | `ko-sroberta-multitask` · 768차원 · SentenceTransformer | `app/services/rag/config.py` = **`text-embedding-3-large` · 3072** |
> | `HNSW(m=16, ef_construction=64)` 인덱스가 있다 | **벡터 인덱스 0개** (btree 5 · gin 5). 컬럼은 `halfvec(3072)`, `medicine_chunk` **0행** — *만들 수 있음*은 `test_db_vector.py` 가 검증하지만 *만들어져 있지는 않다* |
> | `providers/sentence_transformer.py` | 그 파일 없음 |
> | AI Worker 가 `medicines.json` 이름 매칭으로 RAG 수행 | 실제 RAG 는 `medicine_chunk` 벡터 검색 |
>
> 갱신은 RAG 구간에 착수할 때 그 PLAN 의 `affects` 로 처리한다.
> 등재 = `docs-private/DOC_TRUTH_DRIFT.md` §B-1.

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

Operational rule: `fetch_sample.py` is **local/CI only** and MUST NOT run against the
production database. Production data is populated via `sync_medicine_data.py`.

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
1. **Cloudflare edge**: TLS termination, managed WAF ruleset, DDoS protection.
   The origin has no inbound ports (tunnel-only), so it cannot be reached directly.
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
```
# .github/workflows/deploy.yml  (CD, on push to main)
1. Test gate:
   - Python 3.13 + PostgreSQL 17 service (`pgvector/pgvector:0.8.0-pg17`, pinned to match prod)
   - uv sync --frozen, pytest  (ENV=local injected; ENV has no default)
   - failure here blocks every later job

2. Build & push:
   - buildx -> ghcr.io/.../doseph-fastapi:latest AND :<sha>
   - the VM never builds (e2-micro cannot afford it)

3. Deploy:
   - keyless auth via Workload Identity Federation (no long-lived key)
   - SSH through IAP tunnel
   - on the VM: compose pull + up -d --no-build, pinned to the tested :<sha>
   - one-shot `migrate` (aerich upgrade) runs before the API

4. Health check:
   - public endpoint must return 200; rollback target is the previous :<sha>

Path filter: commits touching only medication-frontend/, docs/, *.md,
.github/, envs/ or .env.example do NOT trigger a redeploy
(deny-list — an unknown new path deploys by default, because a silent
under-deploy is the more dangerous failure direction).
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
# 1) Environment (first time only) — there is no switch script
cp .env.example .env      # then fill SECRET_KEY / DB_PASSWORD / KAKAO_*
                          # ENV is required: the app refuses to start without it

# 2) Backend stack (postgres / redis / fastapi / ai-worker)
docker compose up -d
curl -i http://localhost:8000/api/v1/health

# 3) Frontend (separate origin, :3000 -> :8000 cross-origin)
cd medication-frontend && npm run dev
```

Tests run **inside the container** so that configuration and dependencies match the real runtime:

```bash
docker exec fastapi uv run --no-sync pytest app/tests -q
```

Kakao login works locally against a **mock IdP** (`/api/v1/mock/kakao/*`). That router is
registered only when `ENV=local` and additionally refuses to serve in any other environment.

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
- **API**: `/api/v1/health` (includes DB connection status) — also the CD gate after deploy
- **Docker**: per-container healthcheck configuration
- **CSP reports**: `POST /csp-report` collects browser violation reports

---

## Scalability Considerations

### Current Constraints (e2-micro, Always Free)
- **CPU**: 2 shared vCPU (burstable)
- **Memory**: 1GB — the binding constraint. Two uvicorn workers OOM-crashloop,
  so the API runs a **single async worker**; that is sufficient for the current login-path traffic.
- **Disk**: small boot disk; images are pulled, never built on the VM.

### Known Trade-offs
- **Region**: VM (`us-west1`) and Neon (`us-west-2`) are co-located, which fixed VM↔DB latency.
  Users and Kakao are in Korea, so the remaining user-perceived latency is dominated by routing,
  not by the app. Moving to an Asia region is an open option.
- **Deploy downtime**: replacing the container causes roughly 40s of 502 during a real redeploy.
  Unnecessary redeploys were eliminated with the CD path filter, but zero-downtime deployment
  (blue-green / rolling / a managed runtime) is still the open item.

### Scaling Strategies
1. **Vertical**: larger instance (leaves the free tier)
2. **Horizontal**: multiple API instances behind Cloudflare, managed DB already in place (Neon)
3. **Workload split**: run AI Worker (OCR/RAG) as a separate deployable — it is intentionally
   not part of the deployed login-path stack today

---

## Technology Stack Summary

| Layer | Technology | Version | Role |
|-------|------------|---------|------|
| **Frontend** | Next.js + React (JavaScript/JSX) | 16 / 19 | Static export (`output: 'export'`) |
| **FE hosting** | Cloudflare Pages | - | Static hosting + CDN (`doseph.com`) |
| **Backend** | FastAPI | 0.128+ | Python 3.13 async API server |
| **Database** | Neon PostgreSQL (+pgvector 0.8.0) | **17** | Managed relational + vector store (prod 17.11 measured 2026-09-15) |
| **Cache/Queue** | Redis | Alpine | RQ broker, cache (**local stack only**) |
| **ORM** | Tortoise ORM | 0.25+ | Async Python ORM |
| **Migrations** | aerich | 0.9+ | Applied by a one-shot `migrate` service |
| **Ingress / TLS** | Cloudflare Tunnel (`cloudflared`) | - | Outbound tunnel; zero inbound ports |
| **Edge security** | Cloudflare WAF + CSP | - | Managed ruleset, CSP with hashed inline scripts |
| **Compute** | GCP Compute Engine e2-micro | - | Always Free tier (`us-west1-b`) |
| **Container** | Docker / Docker Compose | - | Containerization & orchestration |
| **Registry** | GitHub Container Registry (ghcr) | - | Images built in CI, pulled by the VM |
| **CI/CD** | GitHub Actions (+ WIF, IAP) | - | Keyless auth; build-once, promote by `:sha` |
| **FE tests** | Vitest + RTL / Playwright | - | Component tests / browser E2E |
| **Quality gates** | Ruff · MyPy baseline · Bandit · ESLint · npm audit | - | Enforced in CI and pre-commit |

---

## Additional Documentation

- [README.md](./README.md): Project overview and execution guide
- [SYSTEM_DESIGN.md](./SYSTEM_DESIGN.md): Technical design specifications
- [envs/README.md](./envs/README.md): Environment variables, local setup, deployment topology
- [docs/OCR_FLOW.md](./docs/OCR_FLOW.md): OCR processing flow
- [docs/RAG_FLOW.md](./docs/RAG_FLOW.md): RAG pipeline flow
- [docs/frontend/component-roles.md](./docs/frontend/component-roles.md): Frontend component/context roles
- [docs/tech-debt/](./docs/tech-debt/): Tracked technical debt (E2E auth strategy, react-hooks effect refactor)
