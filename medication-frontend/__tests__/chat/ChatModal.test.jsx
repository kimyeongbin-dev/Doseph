// ── ChatModal 초기화 실패 표면화 (1-e) ────────────────────────────────
// 흐름: 모달 열림 -> refetchSessions() -> 세션 목록 조회 실패 -> 재시도 UI 등장
// 잠그는 동작:
//   (1) **세션 목록 조회가 실패하면 '다시 연결하기' 버튼이 보인다**
//   (2) 조회에 성공하면 그 버튼이 **없고** 입력창이 살아 있다(변화 전 부재 — 대장 D19)
//
// (1)이 왜 안전망인가: `refetchQueries` 는 쿼리가 실패해도 resolve 하므로
// ChatModal 의 `.catch` 가 돌지 않는다 -> `initError` 가 영원히 false ->
// ChatModal.jsx 의 재시도 버튼은 **렌더될 수 없는 죽은 코드**였다(2026-09-14 실증).
// 이 테스트는 그 죽은 분기가 다시 죽지 않도록 잠근다.
//
// ⚠️ 의도적으로 단언하지 않는 것: 메시지 전송·GPS 토글·세션 편집 흐름(다른 스펙의 몫).
// 전제: 없음(api / ProfileContext mock 으로 격리, 백엔드 불필요).

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'

import ChatModal from '@/components/chat/ChatModal'
import { ChatSessionProvider } from '@/contexts/ChatSessionContext'
import api from '@/lib/api'

vi.mock('@/lib/api', () => ({
  default: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  showError: vi.fn(),
}))
vi.mock('@/contexts/ProfileContext', () => ({
  useProfile: () => ({ selectedProfileId: 'prof-1' }),
}))

function renderModal() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <ChatSessionProvider>
        <ChatModal onClose={() => {}} profileId="prof-1" />
      </ChatSessionProvider>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('ChatModal 초기화 실패', () => {
  it('세션 목록 조회가 실패하면 재시도 버튼이 보인다', async () => {
    api.get.mockRejectedValue({ response: { status: 500 } })

    renderModal()

    expect(
      await screen.findByRole('button', { name: /다시 연결하기/ }),
      '실패가 전파되지 않으면 이 버튼은 렌더될 수 없는 죽은 코드가 된다',
    ).toBeInTheDocument()
  })

  it('조회에 성공하면 재시도 버튼 없이 입력창이 살아 있다', async () => {
    api.get.mockResolvedValue({ data: [] })

    renderModal()

    expect(
      await screen.findByPlaceholderText('메시지를 입력하세요'),
      '성공 시에는 평소 입력 경로로 들어가야 한다',
    ).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: /다시 연결하기/ }),
      '성공했는데도 재시도 버튼이 보이면 위 테스트는 아무것도 증명하지 못한다',
    ).not.toBeInTheDocument()
  })
})
