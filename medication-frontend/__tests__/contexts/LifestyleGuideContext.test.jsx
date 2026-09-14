// ── LifestyleGuideContext 특성화 테스트 (6C-B Phase 0 안전망) ─────────
// 흐름: 현재 동작을 계약으로 못 박는다 -> 리팩터(N1, exhaustive-deps) 전후 불변 증명.
// 잠그는 동작: 마운트 시 선택 프로필로 가이드 목록 조회 -> newest-first 라 latestGuide = guides[0].
// TanStack Query 기반이라 QueryClientProvider + api/useProfile/sseClient mock 으로 격리.

import { useState } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { LifestyleGuideProvider, useLifestyleGuide } from '@/contexts/LifestyleGuideContext'
import api from '@/lib/api'

vi.mock('@/lib/api', () => ({ default: { get: vi.fn() } }))
vi.mock('@/contexts/ProfileContext', () => ({ useProfile: () => ({ selectedProfileId: 'prof-1' }) }))
vi.mock('@/lib/sseClient', () => ({ streamSSE: vi.fn() }))

// 컨슈머가 렌더될 때마다 guides 참조를 기록한다(참조 안정성 관찰용).
const renderedRefs = []

function Consumer() {
  const { guides, latestGuide, isError } = useLifestyleGuide()
  renderedRefs.push(guides)
  return (
    <div>
      <span data-testid="count">{guides.length}</span>
      <span data-testid="latest">{latestGuide?.id ?? 'none'}</span>
      <span data-testid="error">{String(isError)}</span>
    </div>
  )
}

// 프로바이더 바깥의 state 를 바꿔 **프로바이더 자체의 리렌더**를 강제하는 하네스.
function Harness() {
  const [tick, setTick] = useState(0)
  return (
    <>
      <button onClick={() => setTick(tick + 1)}>리렌더</button>
      <LifestyleGuideProvider>
        <Consumer />
      </LifestyleGuideProvider>
    </>
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

beforeEach(() => {
  vi.clearAllMocks()
  renderedRefs.length = 0
})

describe('LifestyleGuideContext 특성화', () => {
  it('마운트 시 가이드 목록을 조회하고 latestGuide = guides[0] 으로 파생한다', async () => {
    api.get.mockResolvedValueOnce({ data: [{ id: 'g-new' }, { id: 'g-old' }] })
    renderProvider()

    expect(await screen.findByText('2')).toBeInTheDocument()
    expect(screen.getByTestId('latest')).toHaveTextContent('g-new') // newest-first [0]
    expect(api.get).toHaveBeenCalledWith('/api/v1/lifestyle-guides?profile_id=prof-1')
  })

  // `listQuery.data || []` 는 데이터가 있을 때는 TanStack 이 쥔 같은 배열이라 이미
  // 안정적이다. 매 렌더 새 배열이 생기는 구간은 data 가 undefined 일 때(로딩·에러)뿐이고,
  // 그때 컨텍스트 value 의 useMemo 가 통째로 재계산돼 **모든 소비자가 리렌더**된다.
  it('조회 결과가 없는 상태에서 리렌더돼도 guides 참조가 유지된다', async () => {
    api.get.mockRejectedValue(new Error('조회 실패'))

    const user = userEvent.setup()
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={qc}>
        <Harness />
      </QueryClientProvider>,
    )
    await screen.findByText('0')

    const before = renderedRefs.at(-1)
    await user.click(screen.getByRole('button', { name: '리렌더' }))
    const after = renderedRefs.at(-1)

    expect(renderedRefs.length, '리렌더가 실제로 일어나야 비교가 성립한다').toBeGreaterThan(1)
    expect(
      after,
      'guides 가 매 렌더 새 배열이면 컨텍스트 value 메모가 깨져 모든 소비자가 리렌더된다',
    ).toBe(before)
  })

  // 1-d: 가이드는 시드가 없어 평소에도 0건일 수 있는 도메인이라, 실패가 빈 상태와
  // 가장 잘 뭉개지는 자리다. isError 없이는 둘을 영원히 구분할 수 없다.
  it('조회에 실패하면 isError 로 실패를 전파한다', async () => {
    api.get.mockRejectedValue({ response: { status: 429 } })

    renderProvider()

    // 에러 span 안에서만 단언한다 — 페이지 전체 텍스트 검색은 이웃 요소에 걸려
    // 깨져도 통과할 수 있다(대장 D19).
    await waitFor(() =>
      expect(
        screen.getByTestId('error'),
        '가이드 0건과 조회 실패가 같은 화면이면 사용자는 영영 원인을 알 수 없다',
      ).toHaveTextContent('true'),
    )
    expect(screen.getByTestId('count'), '실패해도 빈 배열 계약은 유지한다').toHaveTextContent('0')
  })
})
