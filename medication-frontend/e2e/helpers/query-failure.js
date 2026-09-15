// ── 조회 실패 주입 헬퍼 (E2E 공용) ────────────────────────────────────
// 흐름: 특정 API 경로에 429 를 주입 -> 실패 상태가 안정될 때까지 대기
//       -> 주입 해제 + '다시 시도' 클릭 -> 복구 관측
//
// 왜 429 인가: QueryProvider 가 4xx 는 재시도 없이 즉시 실패시키므로 결정적이고 빠르다
//   (5xx 는 2회 재시도 + backoff 라 타이밍 의존이 생긴다 — 안전망 규칙 R7).
//   429 는 2026-09-14 E2E 에서 실제로 겪은 상태코드이기도 하다.
//
// ⚠️ 왜 "안정될 때까지" 가 필요한가 (2026-09-15 실측):
//   진입 직후 화면이 **스스로 한 번 더 조회**하는 경우가 있다. 예) /medication 은
//   medications 가 도착하면 activeCount 가 0->N 으로 바뀌며 prescription-groups 를
//   invalidate 한다(PrescriptionGroupContext.jsx:116). 이 2차 조회가 주입 해제 뒤에
//   도착하면 **버튼을 누르지도 않았는데 화면이 복구**돼 재시도 테스트가 흔들린다.
//   그래서 주입 해제 전에 "더 이상 자동 재조회가 오지 않는다"를 먼저 확인한다.
//   (자동 재조회 자체는 별건 부채 — **QA-03**, docs/tech-debt/test-followup-queue.md)

import { expect } from '@playwright/test'

export const API = 'http://localhost:8000/api/v1'

// 주입한 실패임을 본문에 남긴다 — 서버 로그에서 진짜 레이트리밋과 혼동하지 않도록.
// 반환값으로 "주입 횟수"와 "안정 대기"를 넘겨 호출부가 경쟁 상태를 없앨 수 있게 한다.
export async function inject429(page, glob) {
  let served = 0
  await page.route(glob, (route) => {
    served += 1
    return route.fulfill({
      status: 429,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'e2e-injected rate limit' }),
    })
  })
  return {
    servedCount: () => served,
    settle: () => waitUntilQuiet(() => served),
  }
}

// 주입 횟수가 quietMs 동안 변하지 않으면 "자동 재조회가 끝났다"로 본다.
// 요청 개수를 상수로 못 박지 않는 이유: 자동 재조회가 나중에 제거되면 개수 단언은
// 영원히 대기하게 된다. 관측 대상은 "조용해졌는가"이지 "몇 번 왔는가"가 아니다.
async function waitUntilQuiet(getCount, { quietMs = 700, timeoutMs = 10_000 } = {}) {
  const deadline = Date.now() + timeoutMs
  let last = getCount()
  let lastChangedAt = Date.now()
  while (Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, 100))
    const now = getCount()
    if (now !== last) {
      last = now
      lastChangedAt = Date.now()
      continue
    }
    if (now > 0 && Date.now() - lastChangedAt >= quietMs) return
  }
  throw new Error(
    `주입한 실패가 ${timeoutMs}ms 안에 안정되지 않았다(마지막 주입 횟수=${getCount()}). ` +
      '자동 재조회가 계속되고 있다면 재시도 테스트는 결정적일 수 없다.',
  )
}

export const errorState = (page) => page.getByTestId('error-state')
export const retryButton = (page) => page.getByRole('button', { name: '다시 시도' })

// 실패 안정 -> 주입 해제 -> 재시도 클릭 -> 에러 화면이 사라지는 것까지 한 흐름으로 확인한다.
// `injected` 는 inject429 의 반환값(없으면 안정 대기를 건너뛴다 — 자동 재조회가 없는 화면).
export async function recoverAndRetry(page, glob, injected) {
  if (injected) await injected.settle()
  // 버튼은 주입 해제 **전에** 확인한다 — 해제 후에 찾으면 자동 복구와 경쟁한다.
  const button = retryButton(page)
  await expect(button, '실패 화면에는 재시도 수단이 있어야 한다').toBeVisible()

  await page.unroute(glob)
  await button.click()
  await expect(errorState(page), '복구되면 에러 화면은 사라져야 한다').toHaveCount(0, {
    timeout: 15_000,
  })
}
