// ── main 챌린지 카드 특성화 (6C-B 안전망 · B2) ────────────────────────
// 흐름: 활성 챌린지 시드 -> /main 진입 -> 카드가 활성 챌린지 중 "하나"를 골라 렌더
// 잠그는 동작(warning B2 @ app/main/page.jsx, set-state-in-effect):
//   (1) 활성 챌린지가 있으면 시드 2건 중 **정확히 1건**의 제목이 카드 heading 으로 뜬다
//   (2) 화면에 뜬 제목과 **같은 항목의 설명**이 함께 뜬다(제목/설명이 따로 파생되지 않음)
//   (3) 활성 분기 CTA 는 '진행 상황 보기' 이고 /challenge 로 이동한다
//   (4) 빈 상태 문구는 동시에 뜨지 않는다(두 분기는 배타적)
// 리팩터(effect 제거 -> 렌더 중 파생) 전후로 이 계약이 불변이어야 한다.
//
// ⚠️ 의도적으로 단언하지 않는 것: 어떤 챌린지가 뽑히는지(랜덤), 난이도·목표일수 등
//    비즈니스 규칙. 챌린지 도메인은 세부 동작이 바뀔 예정이라 구조적 계약만 잠근다.
// 전제: docker fastapi(:8000) 기동 + auth.setup 세션 + seed.setup 의 활성 챌린지 2건.

import { test, expect } from '@playwright/test'

// seed.setup.js 의 SEED_CHALLENGES 와 같은 값 — 시드가 바뀌면 여기도 함께 바꾼다.
const SEED_CHALLENGES = [
  { title: 'E2E 물 2L 마시기', description: '하루 2L 물 마시기' },
  { title: 'E2E 가볍게 걷기', description: '하루 20분 걷기' },
]

test.describe('활성 챌린지 카드 (B2)', () => {
  test('활성 챌린지 중 정확히 하나를 제목·설명 쌍으로 렌더한다', async ({ page }) => {
    await page.goto('/main')

    // 카드 자체가 렌더될 때까지 기다린다(라벨은 활성/빈 상태 공통)
    await expect(page.getByText('Active Challenge')).toBeVisible()

    // (1) 시드 2건 중 정확히 1건만 화면에 있다
    const seededTitles = page.getByRole('heading', {
      name: new RegExp(SEED_CHALLENGES.map((c) => c.title).join('|')),
    })
    await expect(
      seededTitles,
      '활성 챌린지가 2건이므로 카드에는 그중 정확히 1건만 떠야 한다',
    ).toHaveCount(1)

    // (2) 뜬 제목과 짝이 맞는 설명이 함께 보인다
    const shownTitle = await seededTitles.innerText()
    const shown = SEED_CHALLENGES.find((c) => c.title === shownTitle.trim())
    expect(shown, `예상 밖의 제목이 렌더됨: ${shownTitle}`).toBeTruthy()
    await expect(
      page.getByText(shown.description),
      '제목과 설명은 같은 챌린지에서 파생돼야 한다',
    ).toBeVisible()

    // (4) 빈 상태 분기와 동시에 뜨지 않는다
    await expect(page.getByText('새로운 도전을')).toHaveCount(0)
  })

  test('활성 분기 CTA 는 진행 상황 보기이며 /challenge 로 이동한다', async ({ page }) => {
    await page.goto('/main')

    const cta = page.getByRole('button', { name: '진행 상황 보기' })
    await expect(cta, '활성 챌린지가 있으면 CTA 는 진행 상황 보기여야 한다').toBeVisible()

    await cta.click()
    await expect(page).toHaveURL(/\/challenge(\/)?$/)
  })
})
