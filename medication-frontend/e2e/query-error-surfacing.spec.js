// ── 목록 조회 실패 표면화 (후속 큐 1-d) ───────────────────────────────
// 흐름: 목록 API 에 429 주입 -> 화면이 '빈 상태'가 아니라 '에러 상태'를 그린다
//       -> 주입 해제 후 '다시 시도' -> 정상 화면으로 복구
// 잠그는 동작:
//   (1) 조회 실패 시 error-state 가 보인다
//   (2) **같은 화면에서 EmptyState 문구는 보이지 않는다** — 실패와 '데이터 없음'의 구분
//   (3) 재시도가 실제로 복구시킨다(에러 화면이 사라지고 데이터/빈 상태가 나타난다)
//
// ⚠️ 의도적으로 단언하지 않는 것: 에러 문구의 정확한 문장(ErrorState 단위 테스트의 몫),
//    5xx/네트워크 단절 경로(Vitest 층에서 커버), 재시도 횟수·backoff 정책.
// 전제: docker fastapi(:8000) 기동 + auth.setup 세션 + seed.setup 의 처방전/챌린지.

import { test, expect } from '@playwright/test'

import { API, errorState, inject429, recoverAndRetry } from './helpers/query-failure'

test.describe('목록 조회 실패 표면화 (1-d)', () => {
  test('처방전 목록: 실패가 "등록된 처방전이 없어요" 로 렌더되지 않는다', async ({ page }) => {
    await inject429(page, `${API}/prescription-groups**`)
    await page.goto('/medication')

    await expect(
      errorState(page),
      '조회 실패는 에러 상태로 보여야 한다(빈 상태로 뭉개면 "내 처방전이 사라졌다"로 읽힌다)',
    ).toBeVisible({ timeout: 15_000 })
    await expect(
      page.getByText('등록된 처방전이 없어요'),
      '실패했는데 "없어요" 가 함께 뜨면 두 상태를 구분하지 못한다',
    ).toHaveCount(0)
  })

  test('처방전 목록: 재시도가 실제로 목록을 복구시킨다', async ({ page }) => {
    const glob = `${API}/prescription-groups**`
    const injected = await inject429(page, glob)
    await page.goto('/medication')
    await expect(errorState(page)).toBeVisible({ timeout: 15_000 })

    await recoverAndRetry(page, glob, injected)

    await expect(
      page.getByTestId('prescription-card').first(),
      '시드가 보장한 처방전 카드가 렌더돼야 한다(재시도가 빈 화면으로 끝나면 안 된다)',
    ).toBeVisible()
  })

  test('챌린지: 실패가 "아직 AI 추천 챌린지가 없어요" 로 렌더되지 않는다', async ({ page }) => {
    const glob = `${API}/challenges**`
    const injected = await inject429(page, glob)
    await page.goto('/challenge')

    await expect(
      errorState(page),
      '세 탭이 모두 이 한 쿼리에서 파생되므로 페이지 단위로 표면화한다',
    ).toBeVisible({ timeout: 15_000 })
    await expect(page.getByText('아직 AI 추천 챌린지가 없어요')).toHaveCount(0)

    await recoverAndRetry(page, glob, injected)

    await expect(
      page.getByRole('button', { name: '진행중' }),
      '복구되면 탭 UI 로 돌아와야 한다',
    ).toBeVisible()
  })

  // 가이드는 시드가 없어 평소에도 0건이라, 실패가 빈 상태와 가장 잘 뭉개지던 자리다.
  // 그래서 "실패 -> 에러", "복구 -> 빈 상태" 두 화면이 **서로 다르게** 나오는지를 잠근다.
  test('생활습관 가이드: 실패와 "가이드 0건" 이 서로 다른 화면이다', async ({ page }) => {
    const glob = `${API}/lifestyle-guides**`
    const injected = await inject429(page, glob)
    await page.goto('/lifestyle-guide')

    await expect(errorState(page)).toBeVisible({ timeout: 15_000 })
    await expect(
      page.getByText('아직 생활습관 가이드가 없어요'),
      '실패를 "아직 안 만들었나 보다" 로 읽게 만들면 사용자는 영영 원인을 모른다',
    ).toHaveCount(0)

    await recoverAndRetry(page, glob, injected)

    await expect(
      page.getByText('아직 생활습관 가이드가 없어요'),
      '복구 후 진짜 0건이면 그때는 빈 상태가 맞다',
    ).toBeVisible()
  })
})
