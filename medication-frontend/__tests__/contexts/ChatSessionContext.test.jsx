// ── ChatSessionContext 특성화 테스트 (6C-B Phase 0 안전망) ────────────
// 흐름: 현재 동작을 계약으로 못 박는다 -> 리팩터(M1) 전후 불변 증명.
// 잠그는 동작(warning M1 @ ChatSessionContext.jsx:39, set-state-in-effect):
//   선택 프로필(selectedProfileId)이 바뀌면 activeSessionId 를 null 로 reset.
// useProfile 은 mock(반환값 교체) + QueryClientProvider + api mock 으로 격리.

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { ChatSessionProvider, useChatSession } from '@/contexts/ChatSessionContext'
import { useProfile } from '@/contexts/ProfileContext'
import api from '@/lib/api'

vi.mock('@/lib/api', () => ({ default: { get: vi.fn(() => Promise.resolve({ data: [] })) } }))
vi.mock('@/contexts/ProfileContext', () => ({ useProfile: vi.fn() }))

function Consumer() {
  const { activeSessionId, setActiveSessionId } = useChatSession()
  return (
    <div>
      <span data-testid="active">{activeSessionId ?? 'none'}</span>
      <button type="button" onClick={() => setActiveSessionId('s1')}>
        set-active
      </button>
    </div>
  )
}

function tree() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return (
    <QueryClientProvider client={qc}>
      <ChatSessionProvider>
        <Consumer />
      </ChatSessionProvider>
    </QueryClientProvider>
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  api.get.mockResolvedValue({ data: [] })
})

describe('ChatSessionContext activeSession reset', () => {
  it('프로필이 바뀌면 activeSessionId 를 null 로 리셋한다 (M1)', async () => {
    useProfile.mockReturnValue({ selectedProfileId: 'prof-A' })
    const user = userEvent.setup()
    const { rerender } = render(tree())

    // 사용자가 세션 선택
    await user.click(screen.getByRole('button', { name: 'set-active' }))
    expect(screen.getByTestId('active')).toHaveTextContent('s1')

    // 프로필 전환 -> effect 가 active reset
    useProfile.mockReturnValue({ selectedProfileId: 'prof-B' })
    rerender(tree())

    expect(screen.getByTestId('active')).toHaveTextContent('none')
  })
})
