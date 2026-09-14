// ── 조회 실패 주입 헬퍼 (E2E 공용) ────────────────────────────────────
// 흐름: 특정 API 경로에 429 를 주입 -> 화면의 실패 표면화를 관측 -> 해제 후 재시도
//
// 왜 429 인가: QueryProvider 가 4xx 는 재시도 없이 즉시 실패시키므로 결정적이고 빠르다
//   (5xx 는 2회 재시도 + backoff 라 타이밍 의존이 생긴다 — 안전망 규칙 R7).
//   429 는 2026-09-14 E2E 에서 실제로 겪은 상태코드이기도 하다.

import { expect } from '@playwright/test'

export const API = 'http://localhost:8000/api/v1'

// 주입한 실패임을 본문에 남긴다 — 서버 로그에서 진짜 레이트리밋과 혼동하지 않도록.
export async function inject429(page, glob) {
  await page.route(glob, (route) =>
    route.fulfill({
      status: 429,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'e2e-injected rate limit' }),
    }),
  )
}

export const errorState = (page) => page.getByTestId('error-state')
export const retryButton = (page) => page.getByRole('button', { name: '다시 시도' })

// 주입 해제 -> 재시도 클릭 -> 에러 화면이 사라지는 것까지 한 흐름으로 확인한다.
export async function recoverAndRetry(page, glob) {
  await page.unroute(glob)
  await retryButton(page).click()
  await expect(errorState(page), '복구되면 에러 화면은 사라져야 한다').toHaveCount(0, {
    timeout: 15_000,
  })
}
