# E2E 테스트 & 정적 전환(P1) 검증 시나리오

Doseph 프론트엔드의 Playwright E2E 테스트와, **로컬 서버 기동부터** 정적 export 전환(P1)을
직접 눈으로 확인하는 절차를 정리한다.

> 📐 **테스트를 쓰기 전에 `docs/TESTING_SAFETY_NET_RULES.md` 를 먼저 읽을 것.**
> 무엇을 단언하고 무엇을 단언하지 않는지, 층을 어떻게 나누는지의 **규칙 정본**이다.
> 이 문서는 그 규칙을 전제로 한 **실행 절차**만 다룬다.

> 핵심 전제(로컬): 백엔드는 `localhost:3000` 을 **CORS(allow_credentials) 허용**한다.
> 그래서 정적 산출물 `out/` 을 **:3000** 으로 서빙하면 rewrites 없이도 로그인·데이터·상호작용까지
> 로컬에서 정상 동작한다. (배포 cross-site CORS 는 P2 범위.)

---

## 0. 사전 준비 (최초 1회)

```bash
# 1) 프론트 의존성 + Playwright 브라우저 설치
cd medication-frontend
npm install
npx playwright install chromium

# 2) 환경변수 (루트에서, 최초 1회) — 환경 전환 스크립트는 폐지됨
cd ..
cp .env.example .env      # 이후 SECRET_KEY / DB_PASSWORD / KAKAO_* 를 실제 값으로 채움
```

확인: 루트 `.env` 에 `ENV=local`, `NEXT_PUBLIC_ENV=local`.
`NEXT_PUBLIC_API_BASE_URL` 은 **로컬에서 설정하지 않는다** — 미설정 시 `src/config/env.js` 의
기본값(local = `http://localhost:8000`)이 적용된다(설정하면 그 값이 기본값을 덮어써 드리프트 원인이 됨).

---

## 1. 로컬 백엔드 기동 (docker)

```bash
# 루트에서
docker compose up -d          # postgres:5432 / redis:6379 / fastapi:8000 / ai-worker
                              # (nginx 는 로컬 독립 API 전환으로 제거됨)

# 상태 확인
docker compose ps
docker compose logs fastapi --tail=30

# 헬스 체크 (200 이면 정상)
curl -i http://localhost:8000/api/v1/health   # 엔드포인트가 다르면 /docs 로 확인
```

> 백엔드가 안 뜨면 개발자 로그인이 실패하고 인증 테스트가 전부 skip/실패한다. 먼저 `fastapi` 컨테이너가
> `healthy` 인지 확인할 것.

---

## 2. "변화" 직접 확인 — Before / After

### 2-A. Before (현행 · 전환 전)

```bash
cd medication-frontend
npm run dev            # next dev, http://localhost:3000
```

브라우저에서 확인:
- `/medication` → 처방전 카드 클릭 → 주소가 **`/medication/groups/{id}`** (경로 세그먼트) 로 이동.
- 그룹 상세에서 약품 클릭(모바일 폭) → **`/medication/{id}`** 로 이동.
- F12 → Network: `/api/*` 요청이 **동일 출처(:3000)** 로 나가고 rewrites 프록시가 :8000 으로 전달.
- F12 → Application → Cookies: 로그인 후 `access_token`/`refresh_token` 이 `HttpOnly` 로 찍히는지 관찰.

### 2-B. After (P1 전환 후)

```bash
cd medication-frontend
npm run build          # output:'export' → out/ 생성 (Step 3 이후 성공)
npm run serve:static   # serve out -l 3000, http://localhost:3000
```

브라우저에서 확인:
- `/medication` → 카드 클릭 → 주소가 **`/medication/group?group_id={id}`** (쿼리) 로 이동.
- 약품 클릭 → **`/medication/detail?id={id}`** 로 이동.
- 구 경로 직접 진입 `/medication/1`, `/medication/groups/1` → **404**.
- 딥링크 `/medication/detail?id=1` 직접 진입 → 정상 렌더.
- F12 → Network: `/api/*` 가 **크로스오리진(:8000)** 으로 직접 나가고, 응답에
  `Access-Control-Allow-Origin: http://localhost:3000` + `Access-Control-Allow-Credentials: true` 가 붙는지 관찰.
- F12 → Application → Cookies: `:8000` 도메인 쿠키가 그대로 전송되어 로그인 유지되는지 확인.

> 이 Before/After 대비가 "P1이 실제로 무엇을 바꿨는가"를 눈으로 보는 지점이다.

---

## 3. 자동화 E2E 실행

### 3-A. 전환 후(static) 타겟 — P1 Green 기준

```bash
cd medication-frontend
npm run build                    # out/ 먼저 생성 (필수)
npm run test:e2e                 # E2E_TARGET=static(기본): out/ 을 :3000 서빙 후 실행
npm run test:e2e:report          # 실패 시 HTML 리포트 열기
```

기대: 라우팅 계약 · 네비게이션 · 전 페이지 스모크 **모두 통과(Green)**.

### 3-B. 전환 전(dev) 타겟 — Red 캡처용

```bash
cd medication-frontend
# next dev 를 대상으로 라우팅 계약만 돌려 "왜 Red 인지" 확인
E2E_TARGET=dev npx playwright test e2e/p1-routing.spec.js --project=authed
# PowerShell:  $env:E2E_TARGET='dev'; npx playwright test e2e/p1-routing.spec.js --project=authed
```

기대(전환 전): 신규 라우트 200 단언 실패(현재 404), 구 라우트 404 단언 실패(현재 200) → **Red**.
이 실패 로그가 "무엇을 고쳐야 Green 인지"의 스펙이다.

---

## 4. 테스트 구성

프로젝트 실행 순서: `setup`(세션) → `seed`(데이터) → `authed`(본 스펙).

| 파일 | 역할 | 데이터 의존 |
|---|---|---|
| `auth.setup.js` | **mock IdP + 진짜 콜백**으로 로그인 → 세션(storageState) 저장 | 백엔드 필요 |
| `seed.setup.js` | 복약 2종 · 활성 챌린지 2건을 앱의 실제 API 로 **멱등** 시드 | 백엔드 필요 |
| `p1-routing.spec.js` | 신규 쿼리 라우트 200 / 구 동적 라우트 404 / 딥링크 파라미터 | 무 |
| `navigation.spec.js` | 카드→group, 약품→detail 클릭 이동 계약 | 시드 복약 |
| `smoke.spec.js` | 전 페이지 렌더 · 미처리 예외 0 · 404 아님 | 백엔드 필요 |
| `hooks-url-params.spec.js` | `?showSurvey=true`(B1) · `?tab=family`(E3) 진입 계약 | 무 |
| `hooks-auth-gate.spec.js` | 미인증 보호 경로 차단(F1) | 무 |
| `hooks-medication-flow.spec.js` | 복약 목록·상세·검색 버퍼 흐름(C1·C2·D1) | 시드 복약 |
| `hooks-lifestyle-flow.spec.js` | 생활가이드 선택·탭·증상 갱신·챌린지 페이지(A1~A6) — LLM 은 `page.route()` 고정 | 시드 |
| `hooks-chat-flow.spec.js` | 챗 세션 생성·전환·삭제·발신자 구분(G1~G3) — LLM 고정 | 무 |
| `hooks-challenge-card.spec.js` | main 활성 챌린지 카드의 구조적 계약(B2) | 시드 챌린지 |
| `hooks-mypage-stats.spec.js` | 마이페이지 통계 3종 렌더 + 진행 챌린지 수 일치(E1·E2) | 시드 챌린지 |

> `navigation.spec.js` 는 `data-testid="prescription-card"`, `data-testid="medication-item"` 를
> 선택자로 사용한다(테스트가 먼저 참조하는 인터페이스).

---

## 5. 문제 해결

- ⚠️ **`auth.setup.js` 실패** → mock IdP 는 **`ENV=local` 에서만 등록**된다. 루트 `.env` 의 `ENV`
  확인 후 `docker compose up -d` 재기동. 전략 배경: `docs/tech-debt/e2e-auth-strategy.md`
- **인증 테스트가 401/redirect** → 백엔드 미기동 또는 세션 만료. `docker compose ps` 확인 후 재실행.
- **static 타겟에서 즉시 실패** → `out/` 미생성, 또는 **소스 수정 후 빌드를 건너뜀**(옛 코드 검증).
  `npm run build` 를 먼저 실행.
- **데이터 의존 스펙 실패** → `seed.setup.js` 가 먼저 돌았는지 확인. 시드는 멱등이므로 재실행해도 안전하다.
  ⚠️ **skip 으로 넘기지 말 것** — 전제는 단언으로 지킨다(`docs/TESTING_SAFETY_NET_RULES.md` R1).
- **전체 스위트에서만 실패(단독 실행은 통과)** → 레이트 리밋(429) 의심.
  `docker compose logs fastapi --tail=50` 으로 확인. 로컬 compose 만 한도가 완화돼 있다.
