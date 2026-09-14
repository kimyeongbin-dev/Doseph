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
//    -> 후속 과제로 추적 중(로드맵 후속 큐 1-c).

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

  test('세션이 있으면 그 세션의 메시지를 자동 로드한다 (G2·G3)', async ({ page }) => {
    await stubChatApis(page, {
      sessions: [{ id: SESSION_ID, title: '테스트 세션', created_at: '2026-09-14T00:00:00Z' }],
      messages: [
        { id: 'm1', role: 'user', content: '이 약 같이 먹어도 되나요', created_at: '2026-09-14T00:00:01Z' },
        { id: 'm2', role: 'assistant', content: '고정된 mock 답변입니다', created_at: '2026-09-14T00:00:02Z' },
      ],
    })
    await openChat(page)

    await expect(page.getByText('이 약 같이 먹어도 되나요')).toBeVisible({ timeout: 15_000 })
    await expect(page.getByText('고정된 mock 답변입니다')).toBeVisible()
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
