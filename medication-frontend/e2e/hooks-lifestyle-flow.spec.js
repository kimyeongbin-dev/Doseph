// ── 생활 가이드 흐름 특성화 (6C-B 안전망) ────────────────────────────
// 흐름: 가이드 목록 로드 -> selectedGuide 자동 보정 -> 탭 전환 -> 증상 조회
//       -> 가이드 칩으로 다른 가이드 선택 -> 챌린지 페이지 리셋
// 잠그는 동작:
//   A1 (page.jsx:263): 마운트 시 오늘 증상 조회
//   A3 (page.jsx:269): 증상 탭 진입 시 재조회
//   A5 (page.jsx:275): selectedGuide.id 변경 -> 챌린지 페이지 0으로 리셋
//   A6 (page.jsx:302): userPickedGuide / latestGuide 기준 selectedGuide 자동 보정
//
// ⚠️ 가이드 생성은 LLM + SSE 비동기라 E2E 에서 결정적으로 만들 수 없다.
// 그래서 **"남의 시스템" 경계에서만 가짜로 바꾼다** — 가이드/챌린지 조회 응답을
// route 인터셉트로 고정하고, 그 뒤의 선택·탭·페이지네이션 로직은 실제 코드가 돈다.
// (mock IdP 와 같은 원칙: 대역은 외부 경계에, 우리 코드는 진짜로)

import { test, expect } from '@playwright/test'

const API = 'http://localhost:8000/api/v1'

const GUIDE_NEW = '11111111-1111-4111-8111-111111111111'
const GUIDE_OLD = '22222222-2222-4222-8222-222222222222'

function makeGuide(id, label, createdAt = '2026-09-14T00:00:00Z') {
  return {
    id,
    profile_id: '33333333-3333-4333-8333-333333333333',
    status: 'ready',
    content: {
      interaction: `${label} 상호작용 안내`,
      sleep: `${label} 수면 안내`,
      diet: `${label} 식단 안내`,
      exercise: `${label} 운동 안내`,
      symptom: `${label} 증상 안내`,
    },
    medication_snapshot: [],
    revealed_challenge_count: 5,
    created_at: createdAt,
    processed_at: createdAt,
  }
}

// 칩 라벨은 생성일(M/D) 기반이라 두 가이드의 날짜를 다르게 둬야 칩을 구별해 클릭할 수 있다.
const GUIDE_OLD_CREATED_AT = '2026-09-10T00:00:00Z'

// 가이드별 챌린지 — 가이드를 바꾸면 목록도 바뀌는 것을 관측하기 위해 제목을 구분한다.
function makeChallenges(guideId, label) {
  return Array.from({ length: 6 }, (_, i) => ({
    id: `${guideId.slice(0, 8)}-0000-4000-8000-00000000000${i}`,
    profile_id: '33333333-3333-4333-8333-333333333333',
    guide_id: guideId,
    category: 'diet',
    title: `${label} 챌린지 ${i + 1}`,
    target_days: i + 1,
    is_active: false,
    status: 'NOT_STARTED',
  }))
}

/** 가이드/챌린지/증상 조회 응답만 고정한다(생성 경로는 건드리지 않음).
 *  `symptoms` 는 배열 또는 "호출 시점의 배열을 돌려주는 함수" 를 받는다
 *  (저장 후 갱신을 관측하려면 응답이 시점에 따라 달라져야 하기 때문). */
async function stubGuideApis(page, { symptoms }) {
  const currentSymptoms = () => (typeof symptoms === 'function' ? symptoms() : symptoms)

  await page.route(`${API}/lifestyle-guides**`, async (route) => {
    if (route.request().method() !== 'GET') return route.fallback()
    // newest-first — 앱은 list[0] 을 latestGuide 로 파생한다
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        makeGuide(GUIDE_NEW, '최신'),
        makeGuide(GUIDE_OLD, '이전', GUIDE_OLD_CREATED_AT),
      ]),
    })
  })

  await page.route(`${API}/challenges**`, async (route) => {
    if (route.request().method() !== 'GET') return route.fallback()
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([
        ...makeChallenges(GUIDE_NEW, '최신'),
        ...makeChallenges(GUIDE_OLD, '이전'),
      ]),
    })
  })

  await page.route(`${API}/daily-logs**`, async (route) => {
    if (route.request().method() !== 'GET') return route.fallback()
    const today = new Date().toISOString().split('T')[0]
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([{ log_date: today, symptoms: currentSymptoms(), note: '오늘 메모' }]),
    })
  })
}

test.describe('생활 가이드 — 가이드 선택·탭·증상', () => {
  test('최신 ready 가이드가 자동 선택되어 내용이 렌더된다 (A6)', async ({ page }) => {
    await stubGuideApis(page, { symptoms: ['두통'] })
    await page.goto('/lifestyle-guide')

    // latestGuide(list[0]) 가 자동 선택되고 기본 탭(interaction) 내용이 보인다
    await expect(page.getByText('최신 상호작용 안내')).toBeVisible({ timeout: 15_000 })
    await expect(page.getByText('이전 상호작용 안내')).toHaveCount(0)
  })

  test('증상 탭 진입 시 오늘 증상이 조회되어 표시된다 (A1·A3)', async ({ page }) => {
    await stubGuideApis(page, { symptoms: ['두통', '어지러움'] })
    await page.goto('/lifestyle-guide')

    await page.getByRole('button', { name: /증상/ }).first().click()

    await expect(page.getByText('두통').first()).toBeVisible({ timeout: 15_000 })
    await expect(page.getByText('어지러움').first()).toBeVisible()
  })

  test('가이드 목록 조회가 실제로 발생한다 (마운트 시 로드)', async ({ page }) => {
    const calls = []
    page.on('request', (req) => {
      if (req.url().includes('/lifestyle-guides')) calls.push(req.url())
    })

    await stubGuideApis(page, { symptoms: [] })
    await page.goto('/lifestyle-guide')
    await expect(page.getByText('최신 상호작용 안내')).toBeVisible({ timeout: 15_000 })

    expect(calls.length, '마운트 시 가이드 목록을 조회해야 한다').toBeGreaterThan(0)
  })

  test('칩으로 이전 가이드를 고르면 그 선택이 유지된다 (A6)', async ({ page }) => {
    await stubGuideApis(page, { symptoms: [] })
    await page.goto('/lifestyle-guide')
    await expect(page.getByText('최신 상호작용 안내')).toBeVisible({ timeout: 15_000 })

    // 칩 라벨 = 생성일 M/D (최신 가이드에만 ' 최신' 이 붙는다)
    await page.getByRole('button', { name: '9/10' }).click()

    await expect(
      page.getByText('이전 상호작용 안내'),
      '사용자가 고른 가이드는 자동 보정에 덮이지 않고 유지돼야 한다',
    ).toBeVisible()
    await expect(page.getByText('최신 상호작용 안내')).toHaveCount(0)
  })

  test('가이드를 바꾸면 챌린지 페이지가 1쪽으로 리셋된다 (A5)', async ({ page }) => {
    await stubGuideApis(page, { symptoms: [] })
    await page.goto('/lifestyle-guide')
    await expect(page.getByText('최신 상호작용 안내')).toBeVisible({ timeout: 15_000 })

    // 가이드당 챌린지 6개 = 5개씩 2쪽
    await expect(page.getByText('1 / 2')).toBeVisible()
    await page.getByRole('button', { name: '다음 페이지' }).click()
    await expect(page.getByText('2 / 2'), '다음 페이지로 넘어가야 한다').toBeVisible()

    // 다른 가이드로 전환하면 페이지가 1쪽으로 돌아간다
    await page.getByRole('button', { name: '9/10' }).click()

    await expect(
      page.getByText('1 / 2'),
      '가이드를 바꾸면 챌린지 페이지는 1쪽부터 보여야 한다',
    ).toBeVisible()
    await expect(page.getByText('이전 챌린지 1')).toBeVisible()
  })

  test('증상을 저장하면 카드가 최신 기록으로 갱신된다 (A1·A3)', async ({ page }) => {
    // 저장 전/후로 서버 응답이 달라지게 해서 "재조회가 실제로 일어났는가"를 관측한다.
    let stored = ['두통']
    await stubGuideApis(page, { symptoms: () => stored })
    // POST 는 stubGuideApis 의 GET 핸들러보다 나중에 등록해야 우선 적용된다.
    await page.route(`${API}/daily-logs`, async (route) => {
      if (route.request().method() !== 'POST') return route.fallback()
      stored = ['두통', '복통']
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' })
    })

    await page.goto('/lifestyle-guide')
    await page.getByRole('button', { name: /증상/ }).first().click()

    // ⚠️ 폼의 프리셋 칩에도 같은 증상명이 있으므로, 반드시 요약 카드 안에서만 단언한다
    // (그러지 않으면 재조회가 없어도 통과하는 헛된 초록이 된다 — 규칙 R3)
    const summary = page.getByTestId('today-symptom-summary')
    await expect(summary.getByText('두통')).toBeVisible({ timeout: 15_000 })
    await expect(summary.getByText('복통'), '저장 전에는 없어야 한다').toHaveCount(0)

    await page.getByRole('button', { name: '복통', exact: true }).click()
    await page.getByRole('button', { name: '오늘 증상 기록하기' }).click()

    await expect(
      summary.getByText('복통'),
      '저장 후에는 오늘 증상 카드가 최신 기록으로 다시 조회돼야 한다',
    ).toBeVisible()
  })

  test('가이드 조회가 비어 있어도 크래시하지 않는다 (빈 상태)', async ({ page }) => {
    const pageErrors = []
    page.on('pageerror', (err) => pageErrors.push(err.message))

    await page.route(`${API}/lifestyle-guides**`, (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }),
    )
    await page.goto('/lifestyle-guide')

    await expect(page.locator('body')).toBeVisible()
    expect(pageErrors, `미처리 예외: ${pageErrors.join(' | ')}`).toEqual([])
  })
})
