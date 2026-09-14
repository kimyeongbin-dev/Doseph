// ── PrescriptionGroupContext 특성화 테스트 (6C-B Phase 0 안전망) ──────
// 흐름: 현재 동작을 계약으로 못 박는다 -> 리팩터(O1, exhaustive-deps) 전후 불변 증명.
// 잠그는 동작: 마운트 시 선택 프로필로 처방전 그룹 목록 조회 -> groups 노출 + 기본 정렬(DATE_DESC).
// TanStack Query 기반이라 QueryClientProvider + api/useProfile/useMedication mock 으로 격리.

import { useState } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { PrescriptionGroupProvider, usePrescriptionGroup } from '@/contexts/PrescriptionGroupContext'
import api from '@/lib/api'

vi.mock('@/lib/api', () => ({ default: { get: vi.fn() } }))
vi.mock('@/contexts/ProfileContext', () => ({ useProfile: () => ({ selectedProfileId: 'prof-1' }) }))
vi.mock('@/contexts/MedicationContext', () => ({ useMedication: () => ({ medications: [] }) }))

// 컨슈머가 렌더될 때마다 groups 참조를 기록한다(참조 안정성 관찰용).
const renderedRefs = []

function Consumer() {
  const { groups, isLoading, isError } = usePrescriptionGroup()
  renderedRefs.push(groups)
  return (
    <div>
      <span data-testid="loading">{String(isLoading)}</span>
      <span data-testid="error">{String(isError)}</span>
      <span data-testid="ids">{groups.map((g) => g.id).join(',') || 'empty'}</span>
    </div>
  )
}

// 프로바이더 바깥의 state 를 바꿔 **프로바이더 자체의 리렌더**를 강제하는 하네스.
function Harness() {
  const [tick, setTick] = useState(0)
  return (
    <>
      <button onClick={() => setTick(tick + 1)}>리렌더</button>
      <PrescriptionGroupProvider>
        <Consumer />
      </PrescriptionGroupProvider>
    </>
  )
}

function renderProvider() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <PrescriptionGroupProvider>
        <Consumer />
      </PrescriptionGroupProvider>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  renderedRefs.length = 0
})

describe('PrescriptionGroupContext 특성화', () => {
  it('마운트 시 처방전 그룹을 조회하고 기본 정렬(dispensed_date 내림차순)로 노출한다', async () => {
    api.get.mockResolvedValueOnce({
      data: [
        { id: 'old', dispensed_date: '2026-01-01', has_active_medication: true },
        { id: 'new', dispensed_date: '2026-09-01', has_active_medication: true },
      ],
    })
    renderProvider()

    // 로드 후 DATE_DESC -> new 가 앞
    expect(await screen.findByText('new,old')).toBeInTheDocument()
    expect(api.get).toHaveBeenCalledWith(expect.stringContaining('/api/v1/prescription-groups?profile_id=prof-1'))
  })

  // 조회가 실패해 data 가 undefined 인 상태를 쓰는 이유:
  // `listQuery.data || []` 는 **데이터가 있을 때는** TanStack 이 쥔 같은 배열을 그대로
  // 돌려주므로 이미 안정적이다. 매 렌더 새 배열이 생기는 건 data 가 undefined 인
  // 구간(로딩·에러)뿐이고, 바로 그때 아래 useMemo 사슬이 통째로 재계산된다.
  it('조회 결과가 없는 상태에서 리렌더돼도 groups 참조가 유지된다', async () => {
    api.get.mockRejectedValue(new Error('조회 실패'))

    const user = userEvent.setup()
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={qc}>
        <Harness />
      </QueryClientProvider>,
    )
    await screen.findByText('empty')

    const before = renderedRefs.at(-1)
    await user.click(screen.getByRole('button', { name: '리렌더' }))
    const after = renderedRefs.at(-1)

    expect(renderedRefs.length, '리렌더가 실제로 일어나야 비교가 성립한다').toBeGreaterThan(1)
    expect(
      after,
      'groups 가 매 렌더 새 배열이면 이를 의존성으로 쓰는 useMemo/effect 가 매번 재계산된다',
    ).toBe(before)
  })

  // 1-d: 실패를 '빈 목록'과 구분하기 위한 계약. 이 값이 없으면 페이지는
  // `groups.length === 0` 만 보고 "등록된 처방전이 없어요"(EmptyState)를 그린다.
  it('조회에 실패하면 isError 로 실패를 전파한다', async () => {
    api.get.mockRejectedValue({ response: { status: 429 } })

    renderProvider()

    // 같은 화면에 isLoading('true') 도 렌더되므로 **에러 span 안에서만** 본다.
    // 페이지 전체에서 'true' 를 찾으면 로딩 문구에 걸려 항상 통과한다(대장 D19).
    await waitFor(() =>
      expect(
        screen.getByTestId('error'),
        'isError 가 없으면 429/500 이 "처방전 없음"으로 보인다(사용자 오인 + 원인 추적 불가)',
      ).toHaveTextContent('true'),
    )
    expect(screen.getByTestId('ids'), '실패해도 빈 배열 계약은 유지한다').toHaveTextContent('empty')
  })
})
