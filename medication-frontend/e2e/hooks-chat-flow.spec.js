// ── 챗 모달 흐름 특성화 (6C-B 안전망) ────────────────────────────────
// 흐름: 모달 open -> 세션 초기화 -> activeSessionId 보정 -> 메시지 로드 -> 스크롤 하단 고정
// 잠그는 동작:
//   G1 (ChatModal.jsx:130): 모달 mount 시 세션 초기화
//   G2 (ChatModal.jsx:138): sessions 변동 시 activeSessionId 보정(빈 목록이면 인사말)
//   G3 (ChatModal.jsx:153): activeSessionId 변경 시 메시지 자동 로드
//   G4 (ChatModal.jsx:166): 세션 변경 시 GPS 토글 상태 리셋
//
// ⚠️ 이 스펙이 검증하지 "않는" 것 — LLM 과의 실제 계약
//    메시지 응답(/messages/ask)은 OpenAI 호출이라 결정적일 수 없어 route 로 고정한다.
//    따라서 **모델 교체·응답 스키마 드리프트는 이 테스트로 잡히지 않는다.**
//    그쪽은 (a) 응답 Pydantic 스키마 강제 (b) 실 provider 계약 테스트(스케줄 실행)
//    (c) 경계 계측·에러율 알림이 담당해야 한다. mock 은 우리 코드를 지킬 뿐이다.
//    -> 후속 과제로 추적 중: **QA-07** (docs-private/FOLLOWUP_QUEUE.md).
//       같은 문서 §D 에 "의도적으로 검증하지 않는 것"으로도 등재돼 있다.

import { test, expect } from '@playwright/test'

const API = 'http://localhost:8000/api/v1'
const SESSION_ID = '44444444-4444-4444-8444-444444444444'

/** 챗 조회 경로만 고정한다(세션 목록 / 메시지). 생성·전송 경로는 아래 테스트에서 개별 처리. */
async function stubChatApis(page, { sessions, messages }) {
  await page.route(`${API}/chat-sessions**`, async (route) => {
    if (route.request().method() !== 'GET') return route.fallback()
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(sessions),
    })
  })

  await page.route(`${API}/messages/session/**`, async (route) => {
    if (route.request().method() !== 'GET') return route.fallback()
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(messages),
    })
  })
}

async function openChat(page) {
  await page.goto('/main')
  await page.getByRole('button', { name: /AI 상담하기/ }).click()
}

test.describe('챗 모달 — 세션 초기화 / 메시지 로드', () => {
  test('세션이 없으면 인사말이 표시된다 (G1·G2)', async ({ page }) => {
    await stubChatApis(page, { sessions: [], messages: [] })
    await openChat(page)

    await expect(
      page.getByText(/궁금한 것을 물어보세요/),
      '세션이 비어 있으면 기본 인사말이 떠야 한다',
    ).toBeVisible({ timeout: 15_000 })
  })

  // ⚠️ 발신자 구분은 BE 의 `sender_type`(USER|ASSISTANT)으로 판정한다.
  //    과거 이 mock 은 `role` 을 보내 모든 메시지가 assistant 로 렌더됐는데,
  //    텍스트 존재만 단언해서 통과했다 — 매핑이 깨져도 초록인 구멍이었다.
  //    관측 가능한 차이로 잠근다: user 는 원문 그대로, assistant 는 Markdown 렌더.
  test('세션이 있으면 그 세션의 메시지를 발신자 구분대로 로드한다 (G2·G3)', async ({ page }) => {
    await stubChatApis(page, {
      sessions: [{ id: SESSION_ID, title: '테스트 세션', created_at: '2026-09-14T00:00:00Z' }],
      messages: [
        {
          id: 'm1',
          sender_type: 'USER',
          content: '이 약 **같이** 먹어도 되나요',
          created_at: '2026-09-14T00:00:01Z',
        },
        {
          id: 'm2',
          sender_type: 'ASSISTANT',
          content: '고정된 **mock 답변**입니다',
          created_at: '2026-09-14T00:00:02Z',
        },
      ],
    })
    await openChat(page)

    // USER 메시지는 Markdown 을 거치지 않으므로 ** 가 그대로 보인다
    await expect(page.getByText('이 약 **같이** 먹어도 되나요')).toBeVisible({ timeout: 15_000 })
    // ASSISTANT 메시지는 Markdown 렌더 -> strong 엘리먼트가 생긴다
    await expect(
      page.locator('strong', { hasText: 'mock 답변' }),
      'ASSISTANT 메시지는 Markdown 으로 렌더돼야 한다(발신자 매핑 확인)',
    ).toBeVisible()
  })

  // 세션 전환은 activeSessionId 보정(G2)과 메시지 재로드(G3)가 함께 도는 경로다.
  test('세션을 전환하면 그 세션의 메시지로 교체된다 (G2·G3)', async ({ page }) => {
    const SECOND_ID = '55555555-5555-4555-8555-555555555555'
    await page.route(`${API}/chat-sessions**`, async (route) => {
      if (route.request().method() !== 'GET') return route.fallback()
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          { id: SESSION_ID, title: '첫 번째 세션', created_at: '2026-09-14T00:00:00Z' },
          { id: SECOND_ID, title: '두 번째 세션', created_at: '2026-09-13T00:00:00Z' },
        ]),
      })
    })
    // 세션별로 다른 메시지를 돌려줘 "어느 세션의 메시지인지"가 관측 가능하게 한다
    await page.route(`${API}/messages/session/**`, async (route) => {
      if (route.request().method() !== 'GET') return route.fallback()
      const isSecond = route.request().url().includes(SECOND_ID)
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            id: isSecond ? 'b1' : 'a1',
            sender_type: 'USER',
            content: isSecond ? '두 번째 세션 메시지' : '첫 번째 세션 메시지',
            created_at: '2026-09-14T00:00:01Z',
          },
        ]),
      })
    })

    await openChat(page)

    // 목록 첫 항목이 기본 활성 세션
    await expect(page.getByText('첫 번째 세션 메시지')).toBeVisible({ timeout: 15_000 })

    await page.getByText('두 번째 세션', { exact: true }).click()

    await expect(page.getByText('두 번째 세션 메시지')).toBeVisible({ timeout: 15_000 })
    await expect(page.getByText('첫 번째 세션 메시지')).toBeHidden()
  })

  // G4 — 세션을 바꾸면 GPS 토글이 초기 상태(숨김·OFF)로 돌아가야 한다.
  // 관측 방법: /messages/ask 가 202 + action=request_geolocation 을 주면 토글이 등장한다.
  // (실제 위치 권한은 쓰지 않는다 — 토글 등장까지만 필요하고 navigator.geolocation 은
  //  토글을 ON 할 때서야 호출되므로 이 스펙은 브라우저 권한과 무관하다)
  test('세션을 전환하면 GPS 토글이 초기 상태로 리셋된다 (G4)', async ({ page }) => {
    const SECOND_ID = '55555555-5555-4555-8555-555555555555'
    await stubChatApis(page, {
      sessions: [
        { id: SESSION_ID, title: '첫 번째 세션', created_at: '2026-09-14T00:00:00Z' },
        { id: SECOND_ID, title: '두 번째 세션', created_at: '2026-09-13T00:00:00Z' },
      ],
      messages: [],
    })
    await page.route(`${API}/messages/ask`, async (route) => {
      if (route.request().method() !== 'POST') return route.fallback()
      await route.fulfill({
        status: 202,
        contentType: 'application/json',
        body: JSON.stringify({ action: 'request_geolocation', turn_id: 'turn-1' }),
      })
    })

    await openChat(page)
    await expect(page.getByPlaceholder('메시지를 입력하세요')).toBeEnabled({ timeout: 15_000 })

    await page.getByPlaceholder('메시지를 입력하세요').fill('근처 약국 알려줘')
    await page.keyboard.press('Enter')

    // 토글 등장 + 기본 OFF
    await expect(
      page.getByText('위치 정보 사용 꺼짐'),
      '위치 기반 응답이 오면 GPS 토글이 OFF 상태로 등장해야 한다',
    ).toBeVisible({ timeout: 15_000 })

    await page.getByText('두 번째 세션', { exact: true }).click()

    await expect(
      page.getByText(/위치 정보 사용/),
      '세션을 바꾸면 GPS 토글은 다시 숨겨져야 한다(이전 세션의 pending 이 새 세션으로 새지 않게)',
    ).toHaveCount(0)
  })

  test('메시지 조회가 실패해도 모달이 크래시하지 않는다', async ({ page }) => {
    const pageErrors = []
    page.on('pageerror', (err) => pageErrors.push(err.message))

    await page.route(`${API}/chat-sessions**`, (route) =>
      route.request().method() === 'GET'
        ? route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify([{ id: SESSION_ID, title: 'x', created_at: '2026-09-14T00:00:00Z' }]),
          })
        : route.fallback(),
    )
    await page.route(`${API}/messages/session/**`, (route) =>
      route.fulfill({ status: 500, contentType: 'application/json', body: '{"detail":"boom"}' }),
    )

    await openChat(page)

    await expect(page.locator('body')).toBeVisible()
    expect(pageErrors, `미처리 예외: ${pageErrors.join(' | ')}`).toEqual([])
  })
})
