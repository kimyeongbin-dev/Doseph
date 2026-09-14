// ── 무음으로 렌더되던 실패 (후속 큐 1-e) ──────────────────────────────
// 흐름: 통계·챗 세션 API 에 429 주입 -> 화면이 숫자를 지어내거나 조용히 넘어가지 않는다
// 잠그는 동작:
//   (1) 마이페이지 통계는 실패 시 '0일째' 를 지어내지 않고 에러 상태를 그린다
//   (2) 챗 초기화 실패 시 '다시 연결하기' 버튼이 실제로 렌더된다
//
// (2)가 왜 안전망인가: `refetchQueries` 는 실패해도 resolve 하고, 관찰자가 붙기 전
// 호출이면 아무것도 기다리지 않는다. 그래서 ChatModal 의 재시도 UI 는 2026-09-14 까지
// **렌더될 수 없는 죽은 코드**였다. 다시 죽으면 이 테스트가 빨개진다.
//
// ⚠️ 의도적으로 단언하지 않는 것: 스트릭·오늘 복약의 구체적 수치(다른 스펙이 복약
//    체크를 수행하면 달라진다), 에러 문구의 정확한 문장.
// 전제: docker fastapi(:8000) 기동 + auth.setup 세션.

import { test, expect } from '@playwright/test'

import { API, errorState, inject429, recoverAndRetry } from './helpers/query-failure'

test.describe('무음 실패 표면화 (1-e)', () => {
  test('마이페이지 통계: 실패 시 "0일째" 를 지어내지 않는다', async ({ page }) => {
    const glob = `${API}/intake-logs/streak**`
    const injected = await inject429(page, glob)
    await page.goto('/mypage')

    await expect(errorState(page), '통계 조회 실패는 통계 자리에 드러나야 한다').toBeVisible({
      timeout: 15_000,
    })
    await expect(
      page.getByText(/^\d+일째 🔥$/),
      '조회하지 못한 값을 0 으로 그리면 진짜 0 과 구분되지 않고 사용자 의욕만 꺾는다',
    ).toHaveCount(0)

    await recoverAndRetry(page, glob, injected)

    await expect(
      page.getByText(/^\d+일째 🔥$/),
      '복구되면 실제 수치가 다시 렌더돼야 한다',
    ).toBeVisible({ timeout: 15_000 })
  })

  test('챗 모달: 초기화 실패 시 재시도 버튼이 실제로 보인다', async ({ page }) => {
    await inject429(page, `${API}/chat-sessions**`)
    await page.goto('/main')
    await page.getByRole('button', { name: /AI 상담하기/ }).click()

    await expect(
      page.getByRole('button', { name: /다시 연결하기/ }),
      '이 버튼은 2026-09-14 까지 렌더될 수 없는 죽은 코드였다 — 다시 죽지 않도록 잠근다',
    ).toBeVisible({ timeout: 15_000 })
  })
})
