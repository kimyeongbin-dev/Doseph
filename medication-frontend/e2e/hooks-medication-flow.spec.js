// ── 복약 흐름 특성화 (6C-B 안전망) ───────────────────────────────────
// 흐름: /medication 진입(목록 로드) -> 처방전 카드 클릭 -> /medication/group?group_id=
//       -> groupId 로 상세 조회 -> 약품 목록 렌더
// 잠그는 동작:
//   D1 (medication/page.jsx:185)      : 진입 시 목록 refetch -> 처방전 카드가 보인다
//   C1 (medication/group/page.jsx:171): groupId 변경 -> 로딩/에러 상태 + 상세 fetch
//   C2 (medication/group/page.jsx:270): 선택/초기화 동기화
// 전제: auth.setup(세션) + seed.setup(복약 2건) 선행. 시드가 있으므로 skip 되지 않는다.

import { test, expect } from '@playwright/test'

test.describe('복약 목록 -> 그룹 상세', () => {
  test('진입 시 처방전 카드가 로드된다 (D1)', async ({ page }) => {
    await page.goto('/medication')

    const cards = page.getByTestId('prescription-card')
    await expect(
      cards.first(),
      '시드된 처방전이 있으므로 카드가 렌더돼야 한다',
    ).toBeVisible()
    expect(await cards.count()).toBeGreaterThan(0)
  })

  test('카드 클릭 시 group_id 쿼리로 이동하고 상세가 로드된다 (C1·C2)', async ({ page }) => {
    await page.goto('/medication')

    const cards = page.getByTestId('prescription-card')
    await expect(cards.first()).toBeVisible()
    await cards.first().click()

    // 쿼리 라우트로 이동 + group_id 보존
    await page.waitForURL(/\/medication\/group\?group_id=/, { timeout: 15_000 })
    expect(new URL(page.url()).searchParams.get('group_id')).toBeTruthy()

    // groupId 기반 상세 fetch 결과가 렌더된다(약품 항목)
    await expect(
      page.getByTestId('medication-item').first(),
      'group_id 로 상세를 조회해 약품 항목이 렌더돼야 한다',
    ).toBeVisible({ timeout: 15_000 })
  })

  test('존재하지 않는 group_id 로 진입해도 앱이 크래시하지 않는다 (C1 에러 경로)', async ({ page }) => {
    const pageErrors = []
    page.on('pageerror', (err) => pageErrors.push(err.message))

    await page.goto('/medication/group?group_id=00000000-0000-0000-0000-000000000000')

    await expect(page.locator('body')).toBeVisible()
    expect(pageErrors, `미처리 예외 발생: ${pageErrors.join(' | ')}`).toEqual([])
  })
})

test.describe('메인 오늘의 복약', () => {
  test('시드된 복약이 시간대 블록에 분류되어 보인다', async ({ page }) => {
    await page.goto('/main')

    await expect(page.getByRole('heading', { name: '오늘의 복약' })).toBeVisible({
      timeout: 15_000,
    })
    // 시드 약품(08:00 / 13:00 / 19:00)이 블록 안에 렌더된다
    await expect(page.getByText('타이레놀정500mg').first()).toBeVisible()
  })
})
