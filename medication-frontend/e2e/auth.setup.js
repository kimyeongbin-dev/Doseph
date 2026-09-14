// ── 로그인 세션 확보 (global setup) ─────────────────────────────────
// 흐름: /login 진입 -> "카카오로 로그인" 클릭 -> BE /auth/kakao/config 가 내려준
//       authorize_url(로컬=mock IdP)로 이동 -> mock 이 code+state 를 붙여 콜백으로 리다이렉트
//       -> FE 콜백 페이지가 BE 콜백 호출 -> BE 가 HttpOnly 세션 쿠키 발급 -> /main 도달
//       -> storageState(쿠키 포함)를 파일로 저장
//
// 왜 이 방식인가: 가짜로 바꾸는 지점을 "남의 시스템(카카오)" 경계까지로 최소화한다.
// 콜백·토큰교환·userinfo 매핑·가입·세션발급·쿠키속성은 전부 실제 코드 경로를 탄다.
// (JWT 를 테스트에서 직접 만들어 주입하면 이 경로를 통째로 건너뛰게 된다.)
//
// 전제: docker fastapi(:8000) 기동 + ENV=local (mock IdP 는 로컬에서만 등록된다).
// 참고: 개발자 로그인 백도어는 보안 하드닝으로 제거됐다. docs/tech-debt/e2e-auth-strategy.md

import { test as setup, expect } from '@playwright/test'

const AUTH_FILE = 'e2e/.auth/user.json'

setup('mock IdP 로그인으로 세션 저장', async ({ page }) => {
  await page.goto('/login')

  const kakaoLoginButton = page.getByRole('button', { name: /카카오로 로그인/ })
  await expect(
    kakaoLoginButton,
    '로그인 화면에 카카오 로그인 버튼이 보여야 한다(백엔드 기동 확인)',
  ).toBeVisible()

  await kakaoLoginButton.click()

  // 로그인 성공 시 /main 으로 이동 (mock authorize -> 콜백 -> 세션 발급)
  await page.waitForURL(/\/main/, { timeout: 20_000 })

  // 세션 쿠키가 실제로 발급됐는지 확인 — storageState 저장의 전제
  const cookies = await page.context().cookies()
  const names = cookies.map((c) => c.name)
  expect(
    names,
    `세션 쿠키가 없다(발급 실패). 수집된 쿠키: ${names.join(', ') || '없음'}`,
  ).toContain('access_token')

  await page.context().storageState({ path: AUTH_FILE })
})
