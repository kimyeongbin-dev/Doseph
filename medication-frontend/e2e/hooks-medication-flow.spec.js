// ── 복약 흐름 특성화 (6C-B 안전망) ───────────────────────────────────
// 흐름: /medication 진입(목록 로드) -> 처방전 카드 클릭 -> /medication/group?group_id=
//       -> groupId 로 상세 조회 -> 약품 목록 렌더
// 잠그는 동작:
//   D1 (medication/page.jsx)          : 컨텍스트의 확정 검색어 -> 로컬 입력 버퍼 동기화
//                                       (+ 진입 시 목록 refetch 로 카드가 보인다)
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

  // 검색어는 컨텍스트(확정값)와 페이지(입력 버퍼) 두 곳에 나뉘어 산다.
  // 페이지를 떠났다 돌아오면 페이지 state 만 초기화되므로, 입력 버퍼가 확정
  // 검색어로 다시 채워지는지를 잠근다 — 이게 D1 effect 가 하던 일이다.
  test('검색어 적용 후 재진입하면 입력 버퍼가 복원된다 (D1)', async ({ page }) => {
    await page.goto('/medication')
    await expect(page.getByTestId('prescription-card').first()).toBeVisible()

    await page.getByRole('button', { name: '약품 검색' }).click()
    const searchInput = page.getByPlaceholder('약품 이름으로 검색')
    await searchInput.fill('타이레놀')
    await searchInput.press('Enter')

    // 확정 검색어 안내 문구 + 필터된 목록
    await expect(page.getByText(/약품을 포함하는 처방전을 보여드려요/)).toBeVisible()
    await expect(page.getByTestId('prescription-card').first()).toBeVisible()

    // 클라이언트 이동 -> 뒤로가기(컨텍스트 유지, 페이지만 재마운트)
    await page.getByTestId('prescription-card').first().click()
    await page.waitForURL(/\/medication\/group\?group_id=/, { timeout: 15_000 })
    await page.goBack()
    await expect(page.getByTestId('prescription-card').first()).toBeVisible({ timeout: 15_000 })

    // 검색창을 다시 열면 확정 검색어가 입력 버퍼에 들어 있어야 한다
    await page.getByRole('button', { name: '약품 검색' }).click()
    await expect(
      page.getByPlaceholder('약품 이름으로 검색'),
      '재진입 시 확정 검색어가 입력 버퍼로 복원돼야 한다',
    ).toHaveValue('타이레놀')

    // 뒷 테스트에 검색 상태가 새지 않도록 정리
    await page.getByRole('button', { name: '검색 지우기' }).click()
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

  // 데스크탑(lg+)에선 약품 클릭이 페이지 이동이 아니라 우측 패널 선택이다.
  // 선택 state 의 유효성 보정(C2)이 걸린 지점이라 선택 전/후를 함께 잠근다.
  test('데스크탑에선 약품 선택이 우측 패널에 반영된다 (C2)', async ({ page }) => {
    await page.goto('/medication')
    const cards = page.getByTestId('prescription-card')
    await expect(cards.first()).toBeVisible()
    await cards.first().click()
    await page.waitForURL(/\/medication\/group\?group_id=/, { timeout: 15_000 })

    const items = page.getByTestId('medication-item')
    await expect(items.first()).toBeVisible({ timeout: 15_000 })

    // 선택 전 — 패널은 안내 문구
    await expect(page.getByText('약을 선택하면 상세 정보가 표시됩니다.')).toBeVisible()

    await items.first().click()

    // 모바일과 달리 라우트 이동 없이 패널만 바뀐다
    await expect(page).toHaveURL(/\/medication\/group\?group_id=/)
    await expect(
      page.getByRole('button', { name: '약품 정보 수정' }),
      '선택한 약품의 상세가 우측 패널에 렌더돼야 한다',
    ).toBeVisible({ timeout: 15_000 })
    await expect(page.getByText('약을 선택하면 상세 정보가 표시됩니다.')).toBeHidden()
  })

  test('존재하지 않는 group_id 로 진입하면 에러 문구를 보여준다 (C1 에러 경로)', async ({ page }) => {
    const pageErrors = []
    page.on('pageerror', (err) => pageErrors.push(err.message))

    await page.goto('/medication/group?group_id=00000000-0000-0000-0000-000000000000')

    await expect(page.locator('body')).toBeVisible()
    // 404 는 전용 문구로 구분한다(일반 실패 문구와 다름)
    await expect(page.getByText('처방전을 찾을 수 없어요.')).toBeVisible({ timeout: 15_000 })
    expect(pageErrors, `미처리 예외 발생: ${pageErrors.join(' | ')}`).toEqual([])
  })
})

test.describe('메인 오늘의 복약', () => {
  // ⚠️ 이전 버전은 `page.getByText('타이레놀정500mg').first()` 하나였다. 약품명은 어느
  //    블록에 들어가도 화면 어딘가에서는 보이므로, 분류 로직(getBlockKey)이 통째로
  //    깨져도 통과한다 — 테스트 이름이 말하는 "시간대 블록에 분류"를 전혀 잠그지
  //    못했다. 블록 경계(data-testid) 안에서만 단언하도록 교정(규칙 R10).
  test('시드된 복약이 시간대 블록에 분류되어 보인다', async ({ page }) => {
    await page.goto('/main')

    await expect(page.getByRole('heading', { name: '오늘의 복약' })).toBeVisible({
      timeout: 15_000,
    })

    // 시드: 타이레놀정500mg = 08:00(아침) + 19:00(저녁) / 오메프라졸캡슐 = 13:00(점심)
    const morning = page.getByTestId('time-block-morning')
    const afternoon = page.getByTestId('time-block-afternoon')
    const evening = page.getByTestId('time-block-evening')

    await expect(morning.getByText('타이레놀정500mg'), '08:00 은 아침 블록이다').toBeVisible()
    await expect(evening.getByText('타이레놀정500mg'), '19:00 은 저녁 블록이다').toBeVisible()
    await expect(afternoon.getByText('오메프라졸캡슐'), '13:00 은 점심 블록이다').toBeVisible()

    // 분류가 무너져 한 블록에 몰리면(예: 전부 morning) 아래가 깨진다.
    await expect(
      morning.getByText('오메프라졸캡슐'),
      '13:00 약이 아침 블록에 있으면 분류가 깨진 것이다',
    ).toHaveCount(0)
    await expect(
      afternoon.getByText('타이레놀정500mg'),
      '08:00/19:00 약이 점심 블록에 있으면 분류가 깨진 것이다',
    ).toHaveCount(0)
  })
})
