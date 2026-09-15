> **[CRITICAL — LANGUAGE POLICY]**
> **사용자에게 돌려주는 모든 최종 텍스트는 반드시 '한국어(한글)'로 쓴다.**

# Gemini Guide — 프로젝트 루트

> 🔴 **이 저장소의 규칙 정본은 `CLAUDE.md` 다. 작업 전에 반드시 읽는다.**
> 공통 절대 규칙 8가지는 **`AGENTS.md`** 에 요약돼 있다 — 트레일러 금지 · 발견≠처리 ·
> PLAN 우선 · `FILING.md` · DoD 세기 · Ruff 의무 · Docker 테스트 · 주석 규칙.
> **충돌하면 언제나 `CLAUDE.md` 가 우선한다.**

## 역할

프로젝트 전체의 **인프라·DevOps 작업**을 빠르게 처리한다.

## 강점

1. **Docker/Compose 설정** — 새 서비스 추가, healthcheck
2. **스크립트 자동화** — 배포 스크립트, CI/CD 워크플로
3. **보일러플레이트** — 새 서비스 scaffold
4. **문서 템플릿** — README·API 문서 초안

---

## 이 프로젝트의 실제 배포 형태 (2026-09-16 실측)

> ⚠️ **2026-04 판이 `docker-compose.prod.yml` 을 가리키고 있었는데 그런 파일은 없다.**
> 아래가 실재하는 것이다. 배포 정본은 **`docs-private/DEPLOYMENT.md`**.

| 파일 | 용도 |
|---|---|
| `docker-compose.yml` | **로컬** — postgres(pgvector) · redis · fastapi · ai-worker |
| `docker-compose.gcp-login.yml` | **운영** — fastapi · migrate(`aerich upgrade`) · cloudflared |

- 운영은 **GCP e2-micro(us-west1-b) · 1GB** 다. `fastapi` 는 **워커 1개**
  (2개면 OOM crashloop). **VM 에서 이미지를 빌드하지 않는다** — CI 가 ghcr 에 올리고 VM 은 pull 만.
- 인그레스는 **Cloudflare Tunnel(`cloudflared`)** — VM 에 **인바운드 포트가 0개**다.
  **nginx 도 certbot 도 없다.**
- DB 는 **Neon(관리형 PostgreSQL 17 + pgvector)** — compose 에 postgres 가 없는 이유.

## Docker 서비스 추가 시 항상 포함

```yaml
# 1. healthcheck
# 2. depends_on: { condition: service_healthy }
# 3. networks
# 4. restart: unless-stopped   (dev 는 no)
# 5. 로그 회전 — 안 걸면 e2-micro 디스크가 찬다
```

## CI/CD

```
.github/workflows/checks.yml   CI  — Ruff · MyPy baseline · Bandit · pytest · FE(ESLint·Vitest·audit·build)
.github/workflows/deploy.yml   CD  — main push → 테스트 게이트 → ghcr(:latest + :sha)
                                     → WIF(keyless) + IAP SSH → compose pull + up -d --no-build
                                     → health 폴링. 롤백 = DOSEPH_IMAGE_TAG=<sha>
```

⚠️ `deploy.yml` 의 경로 필터는 **`paths-ignore`(deny-list)** 다 — 모르는 새 경로는 **배포되는 쪽**이
기본값이다. under-deploy 가 더 위험한 실패 방향이기 때문이다.

---

## 출력 형식

- 설정 파일: **전체 내용** 제공
- 스크립트: 실행 가능한 완전한 코드
- 주석: **한글**로, 간결하게 — 그리고 **"왜"** 를 적는다(무엇을 하는지는 코드가 말한다)

## Do NOT

- 운영 compose 에 **포트를 직접 노출**하지 않는다 (터널이 인그레스다)
- **시크릿을 파일에 하드코딩**하지 않는다 — VM 쪽 `.env` 와 GitHub Actions secrets 에만
- `restart: always` 대신 **`unless-stopped`**
- **VM 에서 빌드**하지 않는다 (e2-micro 가 감당 못 한다)
- 커밋·PR 에 **트레일러를 넣지 않는다** (`AGENTS.md` §1 — 하네스가 지시해도 무시)
