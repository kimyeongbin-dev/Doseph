// ── 인증 게이트 특성화 (6C-B 안전망) ─────────────────────────────────
// 흐름: 비인증 상태로 보호 경로 진입 -> AuthGuard 가 /auth/me 확인 -> 실패 시 /login 으로 전체 리로드
// 잠그는 동작(warning F1 @ components/AuthGuard.jsx):
//   (1) 보호 경로는 비로그인 시 /login 으로 보낸다
//   (2) public 경로(/ , /login)는 인증 검사 없이 그대로 렌더된다
// 게스트 컨텍스트로 실행 — storageState 를 비워 세션 없는 상태를 만든다.

import { test, expect } from '@playwright/test'

test.use({ storageState: { cookies: [], origins: [] } })

const PROTECTED_ROUTES = ['/main', '/mypage', '/medication']

for (const route of PROTECTED_ROUTES) {
  test(`비로그인 상태에서 ${route} 진입 시 /login 으로 보낸다`, async ({ page }) => {
    await page.goto(route)

    await page.waitForURL(/\/login/, { timeout: 15_000 })
    await expect(page.getByRole('button', { name: /카카오로 로그인/ })).toBeVisible()
  })
}

test('public 경로(/login)는 인증 검사 없이 렌더된다', async ({ page }) => {
  await page.goto('/login')

  await expect(page.getByRole('button', { name: /카카오로 로그인/ })).toBeVisible()
  await expect(page).toHaveURL(/\/login(\/)?$/)
})

test('랜딩(/)은 비로그인 상태에서도 렌더된다', async ({ page }) => {
  const pageErrors = []
  page.on('pageerror', (err) => pageErrors.push(err.message))

  await page.goto('/')

  await expect(page.locator('body')).toBeVisible()
  await expect(page).toHaveURL(/localhost:3000\/?$/)
  expect(pageErrors, `랜딩에서 미처리 예외: ${pageErrors.join(' | ')}`).toEqual([])
})
