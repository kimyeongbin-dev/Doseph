// ── 호출부 네비게이션 계약 (Red-first, 데이터 의존) ─────────────────
// 흐름: 실제 클릭 상호작용이 "전환 후 쿼리 라우트"로 이동하는지 검증한다.
//       처방전 카드 클릭 -> /medication/group?group_id=  (구: /medication/groups/{id})
//       약품 항목 클릭   -> /medication/detail?id=        (구: /medication/{id})
// 전제: docker fastapi(:8000) 기동 + seed.setup(authed 프로젝트의 선행 의존)이
//       처방전 1건 이상을 보장한다 -> 데이터 존재는 단언 대상이지 skip 조건이 아니다.
//       ⚠️ 과거엔 networkidle 직후 count() 로 판정 + waitFor 타임아웃을 삼켜서,
//       전체 스위트 부하 시 무음 skip 이 발생했다(실측: 매 실행 1~2건).
//       skip 은 '조용히 통과'라 회귀를 덮는다 -> 전부 단언으로 바꿨다.
// 선택자: Step 3 구현에서 아래 data-testid 를 부여한다(테스트가 먼저 참조하는 인터페이스).
//   - 처방전 카드:  data-testid="prescription-card"
//   - 약품 항목:    data-testid="medication-item"

import { test, expect } from '@playwright/test'

test.describe('처방전 카드 -> 그룹 상세 쿼리 라우트', () => {
  test('카드 클릭 시 /medication/group?group_id= 로 이동', async ({ page }) => {
    await page.goto('/medication')
    await page.waitForLoadState('networkidle')

    const cards = page.getByTestId('prescription-card')
    await expect(
      cards.first(),
      '시드 처방전 카드가 렌더돼야 한다(안 보이면 목록 조회 회귀 또는 seed.setup 실패)',
    ).toBeVisible({ timeout: 15_000 })

    await cards.first().click()
    await page.waitForURL(/\/medication\/group\?group_id=/, { timeout: 10_000 })
    expect(new URL(page.url()).searchParams.get('group_id')).toBeTruthy()
  })
})

test.describe('약품 항목 -> 약품 상세 쿼리 라우트 (모바일 뷰포트)', () => {
  test.use({ viewport: { width: 390, height: 844 } })

  test('약품 클릭 시 /medication/detail?id= 로 이동', async ({ page }) => {
    // 카드 -> 그룹 상세 진입
    await page.goto('/medication')
    await page.waitForLoadState('networkidle')
    const cards = page.getByTestId('prescription-card')
    await expect(cards.first(), '시드 처방전 카드가 렌더돼야 한다').toBeVisible({ timeout: 15_000 })

    await cards.first().click()
    await page.waitForURL(/\/medication\/group\?group_id=/, { timeout: 10_000 })

    // 시드 처방전에는 약품이 반드시 있으므로 skip 이 아니라 단언한다.
    // (예전엔 8초 대기 후 skip 이라, 전체 스위트 부하 시 타임아웃이 무음 skip 으로 둔갑했다.)
    const medItems = page.getByTestId('medication-item')
    await expect(
      medItems.first(),
      '시드 처방전의 약품 항목이 렌더돼야 한다(안 보이면 상세 조회 회귀)',
    ).toBeVisible({ timeout: 15_000 })

    await medItems.first().click()
    await page.waitForURL(/\/medication\/detail\?id=/, { timeout: 10_000 })
    expect(new URL(page.url()).searchParams.get('id')).toBeTruthy()
  })
})
