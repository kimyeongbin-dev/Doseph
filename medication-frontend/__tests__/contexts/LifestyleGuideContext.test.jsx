// ── LifestyleGuideContext 특성화 테스트 (6C-B Phase 0 안전망) ─────────
// 흐름: 현재 동작을 계약으로 못 박는다 -> 리팩터(N1, exhaustive-deps) 전후 불변 증명.
// 잠그는 동작: 마운트 시 선택 프로필로 가이드 목록 조회 -> newest-first 라 latestGuide = guides[0].
// TanStack Query 기반이라 QueryClientProvider + api/useProfile/sseClient mock 으로 격리.

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'

import { LifestyleGuideProvider, useLifestyleGuide } from '@/contexts/LifestyleGuideContext'
import api from '@/lib/api'

vi.mock('@/lib/api', () => ({ default: { get: vi.fn() } }))
vi.mock('@/contexts/ProfileContext', () => ({ useProfile: () => ({ selectedProfileId: 'prof-1' }) }))
vi.mock('@/lib/sseClient', () => ({ streamSSE: vi.fn() }))

function Consumer() {
  const { guides, latestGuide } = useLifestyleGuide()
  return (
    <div>
      <span data-testid="count">{guides.length}</span>
      <span data-testid="latest">{latestGuide?.id ?? 'none'}</span>
    </div>
  )
}

function renderProvider() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <LifestyleGuideProvider>
        <Consumer />
      </LifestyleGuideProvider>
    </QueryClientProvider>,
  )
}

beforeEach(() => vi.clearAllMocks())

describe('LifestyleGuideContext 특성화', () => {
  it('마운트 시 가이드 목록을 조회하고 latestGuide = guides[0] 으로 파생한다', async () => {
    api.get.mockResolvedValueOnce({ data: [{ id: 'g-new' }, { id: 'g-old' }] })
    renderProvider()

    expect(await screen.findByText('2')).toBeInTheDocument()
    expect(screen.getByTestId('latest')).toHaveTextContent('g-new') // newest-first [0]
    expect(api.get).toHaveBeenCalledWith('/api/v1/lifestyle-guides?profile_id=prof-1')
  })
})
