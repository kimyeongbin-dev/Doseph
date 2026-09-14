// ── URL 쿼리 파라미터 진입 특성화 (6C-B 안전망) ──────────────────────
// 흐름: 쿼리를 단 URL 로 진입 -> effect 가 상태를 반영 -> router.replace 로 쿼리 정리
// 잠그는 동작:
//   B1 (main/page.jsx)  : /main?showSurvey=true  -> 설문 모달 open + URL 이 /main 으로 정리
//   E3 (mypage/page.jsx): /mypage?tab=family     -> 가족관리 탭 활성 + URL 이 /mypage 로 정리
// 리팩터(이벤트/초기상태 계산으로 이동) 전후로 이 계약이 불변이어야 한다.
// 전제: docker fastapi(:8000) 기동 + auth.setup 세션(storageState).

import { test, expect } from '@playwright/test'

test.describe('?showSurvey=true 진입 (B1)', () => {
  test('설문 모달이 열리고 쿼리가 URL 에서 제거된다', async ({ page }) => {
    await page.goto('/main?showSurvey=true')

    // 모달 제목 — main 이 HealthSurveyModal 에 title="건강 정보 입력" 로 전달
    await expect(
      page.getByText('건강 정보 입력'),
      'showSurvey=true 진입 시 건강 설문 모달이 떠야 한다',
    ).toBeVisible()

    // router.replace('/main') 으로 쿼리가 정리된다(뒤로가기 오염 방지)
    await expect(page).toHaveURL(/\/main(\/)?$/)
  })

  test('쿼리 없이 진입하면 설문 모달이 뜨지 않는다', async ({ page }) => {
    await page.goto('/main')

    await expect(page.getByText('건강 정보 입력')).toHaveCount(0)
  })
})

test.describe('?tab=family 진입 (E3)', () => {
  test('가족관리 탭이 활성화되고 쿼리가 URL 에서 제거된다', async ({ page }) => {
    await page.goto('/mypage?tab=family')

    // 가족관리 탭 본문(activeMenu === '가족관리' 일 때만 렌더)
    await expect(
      page.getByRole('heading', { name: '함께 관리하는 가족' }),
      'tab=family 진입 시 가족관리 탭이 활성화돼야 한다',
    ).toBeVisible()

    await expect(page).toHaveURL(/\/mypage(\/)?$/)
  })

  test('쿼리 없이 진입하면 기본 탭(기본정보)이 유지된다', async ({ page }) => {
    await page.goto('/mypage')

    await expect(page.getByRole('heading', { name: '함께 관리하는 가족' })).toHaveCount(0)
  })
})
