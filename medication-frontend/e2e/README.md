# E2E 테스트 & 정적 전환(P1) 검증 시나리오

Doseph 프론트엔드의 Playwright E2E 테스트와, **로컬 서버 기동부터** 정적 export 전환(P1)을
직접 눈으로 확인하는 절차를 정리한다.

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
docker compose up -d          # postgres:5432 / redis:6379 / fastapi:8000 / nginx:80

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

| 파일 | 역할 | 데이터 의존 | P1 성격 |
|---|---|---|---|
| `auth.setup.js` | dev 로그인 → 세션(storageState) 저장 | 백엔드 필요 | 공통 setup |
| `p1-routing.spec.js` | 신규 쿼리 라우트 200 / 구 동적 라우트 404 / 딥링크 파라미터 | 무 | **Red-first 핵심** |
| `navigation.spec.js` | 카드→group, 약품→detail 클릭 이동 계약 | 처방전 1건+ | Red-first (데이터 시 검증) |
| `smoke.spec.js` | 전 페이지 렌더 · 미처리 예외 0 · 404 아님 | 백엔드 필요 | 회귀 방지 그물 |

> `navigation.spec.js` 는 Step 3 에서 부여할 `data-testid="prescription-card"`,
> `data-testid="medication-item"` 를 선택자로 사용한다(테스트가 먼저 참조하는 인터페이스).

---

## 5. 문제 해결

- ⚠️ **`auth.setup.js` 실패("개발자로 로그인" 버튼 없음)** → 정상이다. **개발자 로그인 백도어는
  보안 하드닝으로 제거됐다**(FE·BE 모두). 이 setup 은 제거된 기능에 의존하는 **낡은 하네스**이며,
  인증이 필요한 E2E 는 다른 인증 전략(예: 테스트에서 직접 세션 쿠키 주입)이 필요하다.
  → 미해결 부채: `docs/tech-debt/e2e-auth-strategy.md`
- **인증 테스트가 401/redirect** → 백엔드 미기동 또는 세션 만료. `docker compose ps` 확인 후 재실행.
- **static 타겟에서 즉시 실패** → `out/` 미생성. `npm run build` 를 먼저 실행.
- **네비게이션 테스트 skip** → 개발자 계정에 처방전 데이터 없음. 앱에서 처방전 1건 등록 후 재실행.
