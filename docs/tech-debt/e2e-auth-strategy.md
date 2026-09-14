# [TECH DEBT] E2E 인증 전략 부재 — dev 로그인 백도어 제거로 `auth.setup.js` 무효화

> 🗓️ 발견: 2026-09-14 (6C 안전망 준비 중 Playwright setup 실행에서 드러남)
> ✅ 상태: **해결 (2026-09-14)** — 채택안 A(mock IdP + 진짜 콜백)로 `auth.setup.js` 재작성(`067c25e`).
> 인증이 필요한 Playwright 스펙이 정상 실행된다(현재 **55 passed · 0 skipped**).
> 이 문서는 선택 근거·대안 비교의 이력 보존용이다.
> 🎯 목표: 앱에 백도어를 되살리지 않으면서 E2E 가 인증 세션을 얻는 방법 확립

---

## 무엇이 깨졌나

`medication-frontend/e2e/auth.setup.js` 는 로그인 화면의 **"개발자로 로그인" 버튼**을 클릭해
HttpOnly 쿠키 세션을 얻고 `storageState` 로 저장하는 구조다. 그런데 그 버튼은 **보안 하드닝 과정에서
FE·BE 양쪽에서 제거**됐다(dev 로그인 백도어 제거).

```
Error: ENV=local 이어야 개발자 로그인 버튼이 보인다
expect(locator).toBeVisible() failed
Locator: getByRole('button', { name: /개발자로 로그인/ })  -> element(s) not found
```

실측(2026-09-14): 로그인 페이지 렌더 = "카카오로 로그인" / "네이버로 로그인" 뿐.
`medication-frontend/src/` 에 개발자 로그인 흔적 0건, BE 소스에도 라우트 없음(잔존 매치는
stale `__pycache__` 바이너리와 docstring 문구뿐).

**영향**: `setup` 프로젝트가 실패하므로 그것에 의존하는 `authed` 프로젝트 스펙(smoke·navigation 등
로그인 필요 테스트)이 전부 막힌다. 이는 env 설정과 **무관**하며, 백도어 제거 시점부터 계속 깨져 있었다.

## 왜 방치됐나

백도어 제거 후 E2E 하네스를 함께 갱신하지 않았다. 이후 인증 E2E 를 돌린 적이 없어 표면화되지 않음
("게이트가 있다 ≠ 게이트가 돈다"의 다른 형태).

## 선택지 (2026-09-14 재평가 — 채택안 변경)

> ⚠️ 최초엔 "JWT 직접 생성 후 쿠키 주입(프로그래매틱 로그인)"을 권장했으나, 조사 중
> **이미 존재하는 mock IdP**(`app/apis/v1/mock_oauth_routers.py`)를 발견해 채택안을 바꿨다.

| 안 | 실제로 검증되는 범위 | 평가 |
|---|---|---|
| **A. mock IdP + 진짜 콜백 (채택)** | **우리 코드 전 경로** — 콜백·code 교환·userinfo 매핑·가입·세션 발급·쿠키 속성 | ✅ 가짜로 바꾸는 지점이 "남의 시스템(카카오)" 경계뿐. 테스트 대역의 올바른 위치 |
| B. JWT 직접 생성 후 쿠키 주입 | 쿠키 주입 **이후만** | 콜백·세션 발급 로직을 통째로 건너뜀. 토큰 스펙을 테스트가 중복 구현해야 함 |
| C. 실제 카카오 OAuth 자동화 | 전부 | 외부 의존·2FA·자격증명으로 취약(flaky) |
| D. local 전용 인증 백도어 재도입 | — | ❌ 제거한 보안 결정을 되돌림 |
| E. 인증 E2E 포기 | — | 커버리지 손실(일부는 컴포넌트 층에서 이미 커버) |

### 채택안 A 가 가능해진 배경 (선결 수정 완료)

mock IdP 는 있었지만 두 가지가 막고 있었고, 2026-09-14 에 해소했다.

1. **`authorize_url` 드리프트** — `FRONTEND_URL + /api/v1/...` 로 Next.js rewrites 프록시를
   전제했으나 정적 export 전환으로 프록시가 사라져 404. → `API_BASE_URL` 기준으로 정정(`d8524b8`).
2. **mock 라우터가 prod 에도 노출** — ENV 게이팅 없이 등록돼 있었음(실측 400=존재).
   세션 위조로 이어지진 않으나(prod 는 실제 카카오로 교환, 이미지에 mock 데이터 없음)
   불필요한 표면이라 **local 전용 게이팅**(`a05b67c`).

> 개념 정리(IdP/RP, OAuth vs OIDC, 대역 위치 선정 근거): `docs-private/study/idp-oauth-oidc.md`

## 처리 조건 (전부 충족)

1. ✅ **앱 코드 변경 없이 테스트 하네스만** 수정 — 백도어를 되살리지 않았다.
2. ✅ 쿠키 속성은 실제 로그인과 동일하다 — **토큰을 위조하지 않고** mock IdP 의 code 를 진짜 콜백에
   넘겨 BE 가 세션을 발급하게 했기 때문이다(콜백·토큰교환·userinfo 매핑·가입·쿠키 발급이 전부 실코드).
3. ✅ `e2e/README.md` 의 문제 해결 항목과 본 문서를 갱신했다.

## 연결
- 6C(react-hooks effect 리팩터)의 **Playwright 흐름 층 선결 조건이었고, 해소되어 6C 가 완주했다**
  (32건 전건 해소 + 3규칙 error 승격). 원장: `docs/tech-debt/frontend-react-hooks-effect-refactor.md`
- 안전망 작성 규칙 정본: `docs/TESTING_SAFETY_NET_RULES.md` (§5 = 대역을 어디에 둘 것인가)
