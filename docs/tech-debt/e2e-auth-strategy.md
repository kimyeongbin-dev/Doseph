# [TECH DEBT] E2E 인증 전략 부재 — dev 로그인 백도어 제거로 `auth.setup.js` 무효화

> 🗓️ 발견: 2026-09-14 (6C 안전망 준비 중 Playwright setup 실행에서 드러남)
> 📌 상태: **미해결** — 인증이 필요한 Playwright 스펙 전부 실행 불가
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

## 선택지

| 안 | 내용 | 평가 |
|---|---|---|
| **A. 프로그래매틱 로그인(권장)** | 테스트 setup 이 앱과 동일한 `SECRET_KEY`/알고리즘으로 유효 JWT 를 만들어 `context.addCookies()` 로 주입 | 프로덕션 표면 추가 **없음**. 업계 표준(programmatic login). 토큰 스펙(클레임·쿠키명·만료)을 BE 와 맞춰야 함 |
| B. 실제 카카오 OAuth 자동화 | 실제 계정으로 로그인 흐름 수행 | 외부 의존·취약(flaky)·자격증명 관리 부담 |
| C. local 전용 테스트 인증 엔드포인트 재도입 | 백도어 부활 | ❌ 제거한 보안 결정을 되돌림. 실수로 prod 노출 위험 |
| D. 인증 E2E 포기 | 해당 흐름을 컴포넌트 테스트로 대체 | 커버리지 손실. 단 일부 흐름은 이미 컴포넌트 층에서 커버됨 |

## 처리 조건

1. A 안 채택 시 **앱 코드 변경 없이 테스트 하네스만** 수정(백도어 재도입 금지).
2. 토큰 생성은 테스트 전용 유틸로 격리하고, 쿠키 속성(HttpOnly·SameSite·domain)을 실제 로그인과 동일하게 맞춘다.
3. 완료 후 `e2e/README.md` 의 문제 해결 항목과 본 문서를 갱신한다.

## 연결
- 6C(react-hooks effect 리팩터)의 **Playwright 흐름 층 선결 조건**.
  컴포넌트/컨텍스트 층 안전망은 이미 확보됨(`medication-frontend/__tests__/`).
  계획: `docs-private/PLAN_FE_HOOKS_EFFECT.md`
