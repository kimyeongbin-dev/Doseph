// ── 마이페이지 통계 카드 특성화 (6C-B 안전망 · E1·E2) ─────────────────
// 흐름: /mypage 진입 -> 프로필 요약 카드에 통계 3종(연속 복약 / 오늘 복약 / 진행 챌린지) 렌더
// 잠그는 동작(warning E1·E2 @ app/mypage/page.jsx, immutability + exhaustive-deps):
//   (1) 통계 3종의 라벨과 값이 모두 렌더된다(조회가 실제로 일어나 값이 채워진다)
//   (2) '진행 챌린지' 값은 **시드가 보장하는 활성 챌린지 수와 정확히 일치**한다
//       -> 페이지가 자체 GET 하든 ChallengeContext 를 재사용하든 같은 수여야 한다
//   (3) '연속 복약'은 `N일째` 형식의 수치다(값 자체는 이력에 따라 달라짐)
// 리팩터(fetchData + useState -> 쿼리 계층 이관) 전후로 이 계약이 불변이어야 한다.
//
// ⚠️ 의도적으로 단언하지 않는 것: 스트릭·오늘 복약의 **구체적 수치**.
//    다른 스펙이 복약 체크를 수행하면 달라지는 값이라, 고정하면 실행 순서에 종속된다.
//    (형식과 존재는 단언하되 값은 단언하지 않는다 — 결정적 실패 유지)
// ⚠️ 단, 단언 대상은 라벨이 아니라 **값 노드(data-testid)** 여야 한다. 라벨만 보면
//    값이 비거나 형식이 깨져도 통과한다(2026-09-15 헛된 초록 교정 V6).
// 전제: docker fastapi(:8000) 기동 + auth.setup 세션 + seed.setup 의 활성 챌린지 2건.

import { test, expect } from '@playwright/test'

// seed.setup.js 가 보장하는 활성 챌린지 수와 같아야 한다.
const SEEDED_ACTIVE_CHALLENGES = 2

test.describe('마이페이지 통계 카드 (E1·E2)', () => {
  test('통계 3종이 렌더되고 진행 챌린지 수가 시드와 일치한다', async ({ page }) => {
    await page.goto('/mypage')

    // (1) 라벨 3종
    await expect(page.getByText('연속 복약')).toBeVisible()
    await expect(page.getByText('오늘 복약')).toBeVisible()
    await expect(page.getByText('진행 챌린지')).toBeVisible()

    // (2) 진행 챌린지 = 시드 활성 챌린지 수
    await expect(
      page.getByTestId('stat-ongoing-challenges'),
      '진행 챌린지 수는 시드가 보장한 활성 챌린지 수와 일치해야 한다',
    ).toHaveText(`${SEEDED_ACTIVE_CHALLENGES}개 🏆`)

    // (3) 연속 복약은 수치 형식 (값 자체는 단언하지 않음)
    await expect(
      page.getByTestId('stat-streak'),
      '연속 복약은 조회된 수치로 채워져야 한다(미조회 시 렌더 자체가 없거나 형식이 깨진다)',
    ).toHaveText(/^\d+일째 🔥$/)

    // (4) '오늘 복약'도 **값 노드**를 본다. 라벨만 보면 값이 비어도 통과한다.
    //     구체적 수치는 실행 순서에 종속되므로 형식만 단언한다(정상 렌더 = '-' 또는 'N종 완료').
    //     통계 조회가 실패하면 이 카드 자체가 ErrorState 로 대체되므로, 형식 단언만으로도
    //     "조회가 끝났고 실패하지 않았다"가 잠긴다.
    await expect(
      page.getByTestId('stat-today-taken'),
      "오늘 복약 값은 '-' 또는 'N종 완료' 형식이어야 한다(조회 실패면 카드가 ErrorState 로 대체된다)",
    ).toHaveText(/^(-|\d+종 완료)$/)
  })

  test('프로필 요약이 활성 프로필 기준으로 렌더된다', async ({ page }) => {
    await page.goto('/mypage')

    // 통계 카드와 같은 요약 블록 — 프로필이 확정돼야 스켈레톤을 벗어난다
    await expect(page.getByRole('heading', { name: /님$/ })).toBeVisible()
  })
})
