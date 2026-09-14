# ROADMAP — Doseph v2.x

> 팀 프로젝트 [`v1.0.0-team-final`](https://github.com/kimyeongbin-dev/Doseph/releases/tag/v1.0.0-team-final) (2026-05-05 종료) 이후
> 개인 포트폴리오로서의 개선 계획. 팀 시점 회고와 정량/정성 기여는 [README.md](./README.md) §5, §7 참조.

본 문서는 v2.x 시리즈의 **단일 source-of-truth**다. 진행 상태는 아래 체크박스로 추적하고, 각 버전 시작 전에는 별도 `PLAN_v2_X.md`를 작성한 뒤 작업한다 ([CLAUDE.md §1.1](./CLAUDE.md)).

---

## 한눈에 보기

| 버전     | 테마                                | 크기  | 상태          | 종료 기준 (요약)                                         |
| ------ | --------------------------------- | --- | ----------- | -------------------------------------------------- |
| v2.0   | 무료 스택 재배포                          | 중-대 | **✅ 완료**    | 외부 URL 한 줄로 full flow 동작 + 인프라 비용 0               |
| v2.1   | Quick wins — 루트/문서/AI 지침 정리       | 소   | 🔄 부분 진행    | 루트 트래킹 항목 ≤ 20개 + 잔재 파일 0개                        |
| v2.2   | 모노레포 구조 재설계 + 마이그레이션              | 중-대 | 대기          | best example 비교 + 새 구조 적용 + CI/E2E green          |
| v2.3   | 정상 동작 재확인 및 테스트 (회귀 안전망)          | 중   | **🔄 진행 중** | 핵심 user flow 5종 E2E green + coverage ≥ 60%        |
| v2.4   | 백엔드 성능 — 측정 + RAG/DB 핫스팟 개선       | 중   | 대기 (v2.3)   | 단계별 p50/p95 측정 + 핫스팟 1~3개 개선 수치 기록                |
| v2.5   | 클린 코드 — Ruff ignore 해제 + 분할       | 소-중 | 대기 (v2.4)   | Ruff ignore ≥ 3개 해제 + 300줄 초과 파일 0개               |
| v2.6   | FE UX 개선 — streaming / 모바일 / 접근성  | 중   | 대기 (v2.4)*  | Lighthouse mobile ≥ 90 + axe-core CI 통합           |

*v2.6은 v2.4 완료 후 v2.5와 병렬 진행 가능.

```mermaid
flowchart LR
    v20[v2.0<br/>재배포] --> v21[v2.1<br/>루트 정리]
    v21 --> v22[v2.2<br/>모노레포 재설계]
    v22 --> v23[v2.3<br/>회귀 안전망]
    v23 --> v24[v2.4<br/>BE 성능]
    v24 --> v25[v2.5<br/>클린 코드]
    v24 --> v26[v2.6<br/>FE UX]
```

---

## v2.0 — 무료 스택 재배포

### 배경
팀 시점 AWS EC2가 종료되어 라이브 데모 부재. 개인 포트폴리오 + 장기 운영을 가정해 **인프라 비용 0원** 스택으로 재배포한다. README §1 "서비스 화면"이 비어있는 상태도 본 단계에서 해소.

### 목표
- 외부 URL 한 줄로 데모 가능 (카카오 로그인 → OCR → 챗봇 응답)
- 월 인프라 비용 = 0원 (LLM/OCR API 사용량분만 본인 부담)
- 1~2년 단위로 만료/이주 부담 없는 always-free 스택

### 채택 스택 (실제 결과)

> 계획 단계의 후보는 Oracle ARM + Vercel + Upstash 였다. 조사·실측 과정에서 아래로 바뀌었다.
> 당시 후보표 원본은 `docs-private/_legacy/2026-09-14_ROADMAP.snapshot.md` 에 보존.

| 레이어             | 채택                                              | 후보와 달라진 이유                                        |
| --------------- | ----------------------------------------------- | ------------------------------------------------- |
| FE              | **Cloudflare Pages** (정적 export)                 | Vercel → CF. 정적 export 라 Node 런타임 불필요, 같은 엣지에서 WAF·CSP 까지 일관 관리 |
| BE / Worker     | **GCP Compute Engine e2-micro** (Always Free)     | Oracle 한국 리전 가입 불가. 대신 GCP 무료는 US 전용이라 리전 제약을 감수 |
| DB              | **Neon** (PostgreSQL + pgvector, `us-west-2`)     | 후보 그대로. 단 **VM 리전과 co-location** 이 지연에 크게 작용      |
| Redis / Queue   | **미사용**                                          | 배포 범위를 "로그인 경로"로 한정 → RQ 불필요(APScheduler 인프로세스). Upstash 검증은 보류 |
| LLM / OCR       | OpenAI · CLOVA OCR (기존)                          | 변동 없음                                             |
| Reverse Proxy   | **없음 — Cloudflare Tunnel**                       | Caddy/Nginx 불필요. 아웃바운드 터널이라 **인바운드 포트 0개**, 인증서 갱신(certbot)도 불필요 |
| Domain          | **Cloudflare** (`doseph.com` / `api.doseph.com`)  | DuckDNS 대신 자체 도메인                                 |

### 작업 단계
- [x] GCP Always Free 인스턴스 프로비저닝 (`us-west1-b`)
- [x] Neon Postgres + `pgvector` / `pg_trgm` 활성화 검증
- [x] 배포용 compose 작성 (`docker-compose.gcp-login.yml` — DB 외부화, 인바운드 포트 0)
- [x] GitHub Actions ghcr namespace 이전 (`kimyeongbin-dev`)
- [x] SSH deploy 교체 — **WIF(keyless) + IAP 터널**, VM 은 pull 만(빌드 없음)
- [x] Cloudflare Pages 에 `medication-frontend` 배포 + API 도메인 연결
- [x] aerich 마이그레이션 Neon 적용 (배포마다 원샷 `migrate` 로 상시화)
- [x] HTTPS 검증 (Cloudflare 종단) + 공개 health 200
- [ ] SSE long-poll 패스스루 검증 (로그인 경로만 배포 중이라 미검증)
- [ ] drug data seed (배포 범위 확대 시)
- [ ] README §1 "서비스 화면" 섹션 채우기 (GIF + 데모 URL)

### Definition of Done
- [x] 외부 URL 한 줄로 로그인 flow 동작
- [x] 월 청구액 = LLM / OCR 사용량분만 (인프라 0원 — 예산 초과 시 VM 자동중지 킬스위치 구성)
- [ ] README §1 서비스 화면 + 데모 URL 갱신

### 배우고 넘어간 것
- **Oracle 한국 리전 가입 불가**, GCP 무료는 US 전용 — "always free"라도 리전 제약이 설계를 바꾼다.
- **VM↔DB co-location** 은 개선됐지만, 사용자·카카오가 한국이라 **체감 지연은 라우팅이 지배**한다.
  (VM 을 아시아로 옮기거나 관리형 런타임으로 가는 선택지가 남아 있음)
- **nginx 를 걷어낸 전환의 뒷정리를 빠뜨려** env 템플릿·문서가 낡은 채 남았고, 한참 뒤
  로컬이 죽은 포트를 가리키는 형태로 터졌다 → 전환의 완료 기준을 코드가 아니라 설정·문서까지로.

### 리스크 / 미해결
- e2-micro 1GB 메모리: uvicorn 워커 2개는 OOM crashloop → 단일 워커로 운영 중. 트래픽 증가 시 재검토.
- 재배포 시 컨테이너 교체로 **약 40초 다운타임**. 무의미한 재배포는 CD 경로 필터로 제거했으나
  무중단 배포(blue-green / rolling / 관리형 런타임)는 미해결.
- Neon free tier 용량으로 `medicine_chunk` + halfvec(3072d) 산정 — RAG 배포 확대 시 재검토.

---

## v2.1 — Quick wins · 루트/문서/AI 지침 정리

### 배경
큰 구조 개편(v2.2) 전, **빠르게 해소 가능한 정리**부터 먼저. 후속 PR이 진단/탐색에 쓸 시간을 줄여준다.

### 목표
- 루트 진입점 정리 (현재 40+ 항목 → 20개 이하)
- 팀 시점 운영 잔재 0개 (`.sql` dump, `.pem`, `.log`, `nul`)
- AI 에이전트 지침 (CLAUDE/AGENTS/GEMINI × 4세트 = 12개) 단일 source 검토

### 작업 단계
- [ ] `PLAN_*.md` (5개) → `docs/plans/archive/` 이동 또는 `.gitignore` 추가
- [ ] `aerich_prod.sql` · `final_utf8_dump.sql` · `doseph-key.pem` · `*.log` · `nul` → tracked 여부 확인 후 `git rm` (gitignore에 일부 등록되어 있으나 이미 트래킹된 경우 명시 제거 필요)
- [ ] `테스트 계획.md` → 영문 파일명 + `docs/` 이동
- [ ] AI 지침 통합 정책 결정
  - 옵션 A: 루트 1세트만 유지 + 하위 디렉토리는 짧은 reference로 축약
  - 옵션 B: 단일 source(`docs/ai_guidelines.md`) + generator로 CLAUDE.md / AGENTS.md / GEMINI.md 생성
- [ ] README 링크 dead link 검사 (이미 ROADMAP.md 추가로 해소됨)

### Definition of Done
- 루트 트래킹 항목 ≤ 20개
- 운영 잔재 파일 트래킹 0개
- AI 지침 정책 적용 (지침 파일 ≤ 4개)

### 리스크 / 미해결
- `aerich_prod.sql`은 운영 dump일 가능성 — `git rm` 전에 민감 정보(이메일/토큰 등) 흔적 검사 필요
- 이미 push된 민감 파일(`*.pem`)은 history에서도 제거해야 안전 — git filter-repo 사용 여부는 별도 결정

---

## v2.2 — 모노레포 구조 재설계 + 마이그레이션

### 배경
v2.1로 잔재가 정리된 뒤, **2026 기준 best example을 참조해 본격 구조 개편**. 큰 `git mv`는 차후 PR 충돌 비용이 크므로 v2.3(테스트) 시작 전에 매듭짓는다.

### 목표
- 2026 기준 FastAPI + Next.js 모노레포 best example 적용
- 도구 chain 통합 (Ruff 단일 source, pre-commit, uv workspace 등)
- 공통 모듈 중복 제거 (`app/core` ↔ `ai_worker/core`)

### 조사 대상 (Research Checklist [§10](./CLAUDE.md))
- FastAPI: `tiangolo/full-stack-fastapi-template` (2025-2026 active), `zhanymkanov/fastapi-best-practices`
- Python 모노레포: `uv` workspace 기능 (uv 0.5+), `python-monorepo-template`
- Next.js 15 App Router: `vercel/next.js/examples/with-docker`, Server Actions 패턴
- 모노레포 도구: Turborepo / Nx / Moon — 본 프로젝트 규모에 over-engineering 여부 판단

### 작업 단계
- [ ] 외부 best example 3종 이상 조사 + 비교표 (`docs/2026_structure_research.md`, 출처 + 연도 명시)
- [ ] 모노레포 구조 결정 (옵션 비교 → `PLAN_v2_2.md`)
  - 옵션 A: 현 평면 유지 (`app/`, `ai_worker/`, `medication-frontend/`)
  - 옵션 B: `services/{api,worker}` + `apps/web`
  - 옵션 C: `uv` workspace + Turborepo
- [ ] `app/` 내부 layer 경계 강화 (Router → Service → Repository → Model 누수 제거)
- [ ] `app/core` ↔ `ai_worker/core` 중복 제거 (`packages/shared` 또는 uv workspace dep)
- [ ] `git mv`로 history 보존
- [ ] CI 그대로 통과 + 데모 URL full flow 회귀 없음
- [ ] `ARCHITECTURE.md` · `SYSTEM_DESIGN.md` 갱신

### Definition of Done
- best example 비교 문서 + 새 구조 적용
- 공통 모듈 중복 ≤ 1곳
- CI/CD green + 라이브 데모 회귀 없음
- 설계 문서 갱신

### 리스크 / 미해결
- 큰 `git mv` 후 IDE / Docker volume / aerich migration path가 깨질 수 있음 — `PLAN_v2_2.md`에 사전 영향도 명시

---

## v2.3 — 정상 동작 재확인 및 테스트 (회귀 안전망)

### 배경
v2.0(인프라 교체) + v2.1/v2.2(구조 개편) 직후 회귀 위험이 가장 큰 구간. 팀 시점 마지막 주에 회귀 fix를 몰아 처리했던 경험 ([README §7](./README.md#7-느낀점)) 재발 차단.

### 목표
- 핵심 user flow 5종 자동화 검증
  1. 카카오 로그인 + 첫 설문 분기
  2. 처방전 OCR → 약 등록
  3. 챗봇 RAG 응답 (Structured Output)
  4. 회수약품 알림 (`recall_check`)
  5. 가족 프로필 전환 + context 격리
- 백엔드 단위 테스트 coverage baseline 측정 + 점진 개선
- mypy strict 통과 영역 확대 (현재 `app.models.*`, `tests.*` 등 override 中)

### 작업 단계
- [x] **MyPy baseline 게이트 도입** — 기존 오류를 고정하고 **신규 타입오류만 CI/로컬에서 차단**
      (출혈 정지). 기존 오류는 파일을 건드릴 때마다 그 자리에서 소각(보이스카웃).
      도입 초기 수치 919는 `python_executable` 오설정으로 부풀려진 허수였고, 정정 후 실제 379에서 출발.
- [x] **프론트 컴포넌트 테스트 레이어 도입** — Vitest + React Testing Library(CI 연결).
      페이지 흐름은 Playwright, 컴포넌트·컨텍스트 세부는 Vitest 로 층 분리.
- [x] **Playwright 인증 E2E 복구** — 개발자 로그인 백도어 제거로 죽어 있던 setup 을
      **mock IdP 로 실제 로그인 흐름을 태우는 방식**으로 재작성(콜백·세션발급·쿠키는 진짜 경로).
- [x] 리팩터 안전망으로 컴포넌트/컨텍스트 특성화 테스트 24종 확보
- [ ] 현 시점 coverage 측정 + baseline 기록
- [ ] 핵심 user flow 5종 E2E 확대 (현재 인증·라우팅·스모크까지)
- [ ] 백엔드 비즈니스 로직 단위 테스트 보강 (intent / RAG / OCR 파이프라인 우선)
- [ ] CI에 coverage threshold gate 추가 (60% → 점진 ↑)
- [ ] aerich downgrade / upgrade 양방향 smoke test (CI)
- [ ] LLM 응답 schema validation 회귀 테스트 (Structured Output 깨짐 즉시 감지)
- [ ] `pyproject.toml` mypy override 1~2개 해제 검토

### Definition of Done
- 5종 user flow E2E green
- 백엔드 coverage ≥ 60% (baseline 대비 명시적 ↑ 폭 기록)
- CI 평균 시간 ≤ 5분 유지
- mypy override 최소 1개 해제

---

## v2.4 — 백엔드 성능 (측정 + 핫스팟 개선)

### 배경
v2.3까지 안전망(테스트 + coverage gate)이 깔린 상태에서 **측정 → 개선 → 검증** 사이클로 진행. 정량 수치로 회귀 여부 판정.

### 목표
- RAG 파이프라인 단계별 p50 / p95 측정 인프라 구축
- 측정 결과 기반으로 핫스팟 1~3개 선정 + 개선
- DB 쿼리 N+1 / index miss 제거

### 작업 단계
- [ ] 관측성 baseline — 단계별 latency 로깅 (Query Rewriter / Retriever / Composer / OCR)
- [ ] RAG 파이프라인 p50 / p95 측정 (실 사용자 트래픽 또는 reproducible scenario)
- [ ] N+1 쿼리 감지 (Tortoise `prefetch_related` 갭) + 수정
- [ ] OpenAI 호출 cache 영역 식별 (Structured Output schema, persona prompt)
- [ ] halfvec HNSW 파라미터 (`m`, `ef_search`) 튜닝 + 전후 recall@k 측정
- [ ] 정량 결과 → `docs/v2.4_performance_report.md` + README §5 수치 보강

### Definition of Done
- 단계별 p50 / p95 측정값 문서화
- 핫스팟 ≥ 1개 개선 + 전후 수치 명시
- recall@k 회귀 없음 (개선이면 더 좋음)

### 리스크 / 미해결
- 무료 스택(Neon free tier) 환경에서 측정한 값은 production 절대치로 보기 어려움 — **상대 개선폭**으로 해석한다는 점을 문서에 명시

---

## v2.5 — 클린 코드 (Ruff ignore 해제 + 분할)

### 배경
v2.4로 핫스팟이 정리된 뒤, **코드 자체의 부채를 정리**. 작은 PR 단위로 누적.

### 목표
- 현재 `pyproject.toml` 의 ignore 룰 중 ≥ 3개 해제
- 300줄 초과 파일 분할 ([CLAUDE.md §4.2](./CLAUDE.md))
- per-file ignore 해소 (특히 `app/services/ocr_service.py`)

### 작업 단계
- [ ] 현재 ignore 룰 영향도 측정 (해제 시 발생 violation 수)
- [ ] 우선순위 해제 — `TC001` / `TC002` / `TC003` (type-checking), `RUF012` (mutable class default), `EM101` / `EM102` (exception message)
- [ ] 300줄 초과 파일 검사 + 분할 PR
- [ ] 중복 코드 / `SLF001` 우회 패턴 정리
- [ ] `app/services/ocr_service.py` per-file ignore (F811, ASYNC230, PTH123, E501) 해소
- [ ] `app/repositories/medication_repository.py` · `app/workers/intake_log_worker.py` `DTZ011` (aware datetime) 해소

### Definition of Done
- Ruff ignore 룰 ≥ 3개 해제
- 300줄 초과 파일 0개
- per-file ignore ≥ 2개 해소

---

## v2.6 — FE UX 개선 (streaming · 모바일 · 접근성)

### 배경
v2.4 완료 후 **v2.5와 병렬 진행 가능** — 백엔드 안 건드림. FE 마이크로 개선 + 모바일 + 접근성.

### 목표
- 챗봇 응답 SSE streaming UX 가시화
- 모바일 반응형 점검 (가족 관리 / 처방전 카드 우선)
- 접근성 baseline (axe-core CI 통합)
- Lighthouse mobile ≥ 90

### 작업 단계
- [ ] 챗봇 응답 streaming UI 인디케이터 (SSE 진행 상태 + 부분 응답 점진 표시)
- [ ] OCR 업로드 progress + 실패 retry UX
- [ ] 에러 경계 (React Error Boundary) 도입 — 챗 / OCR / 가족 관리 화면
- [ ] 키보드 nav 점검 (Tab order, focus trap on modal)
- [ ] 모바일 반응형 점검 (가족 관리 / 처방전 카드 → 다른 페이지)
- [ ] axe-core 자동 검사 CI 통합
- [ ] Lighthouse 측정 → 90 미만 항목 우선순위화

### Definition of Done
- Lighthouse mobile ≥ 90
- axe-core CI green
- 핵심 화면 5종 모바일 회귀 없음

---

## 버전별 운영 규칙

- **PLAN 우선**: 각 버전 시작 전 `PLAN_v2_X.md` 작성 + 사용자 승인 후 작업 ([CLAUDE.md §1.1](./CLAUDE.md))
- **태그 + Release**: 각 버전 종료 시 `v2.0.0`, `v2.1.0` annotated tag + GitHub Release 등록
- **회귀 가드**: v2.2(구조 재설계) 전후로 functional snapshot 보조 태그 부착 (`v2.1.0-cleanup` 등)
- **단일 source-of-truth**: 진행 상태는 본 ROADMAP.md 체크박스 — Issues / Projects 미사용
- **병렬 허용**: v2.5와 v2.6은 v2.4 완료 후 병렬 가능 (백엔드 vs 프론트엔드)

---

## 동기화 항목

- [x] [README.md §6](./README.md#6-개선-로드맵-v2x) — v2.0~v2.6 (7개) 라인업으로 정렬 완료 (`docs: v2.x ROADMAP 작성 및 README v2.x 라인업 동기화`)
- [x] [README.md §7](./README.md#7-느낀점) — "관측성·메트릭부터 깔고 갈 계획" → "v2.4 단계에서 측정 인프라부터 깔고 핫스팟 잡을 계획"으로 정렬
