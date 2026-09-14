// ── MedicationContext 조회 실패 계약 (1-d) ────────────────────────────
// 흐름: 목록 조회 실패 -> isError=true 로 소비자에게 전파 -> 페이지가 에러 화면 선택
// 잠그는 동작:
//   (1) 조회 성공 시 medications 노출 + isError=false
//   (2) **조회 실패 시 isError=true** — 실패가 '빈 목록'과 구분된다
//   (3) 실패해도 medications 는 빈 배열이라 소비자가 터지지 않는다(기존 계약 유지)
// (2)가 왜 안전망인가: 이 값이 없으면 페이지는 실패를 알 길이 없어
// `length === 0` 분기로 "등록된 약이 없어요"(EmptyState)를 그린다 — 실패가 사라진다.
// ⚠️ 의도적으로 단언하지 않는 것: 에러 객체의 내용. 화면 문구는 ErrorState 의 책임이다.
// 전제: 없음(api/ProfileContext mock 으로 격리, 백엔드 불필요).

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'

import { MedicationProvider, useMedication } from '@/contexts/MedicationContext'
import api from '@/lib/api'

vi.mock('@/lib/api', () => ({
  default: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}))
vi.mock('@/contexts/ProfileContext', () => ({
  useProfile: () => ({ selectedProfileId: 'prof-1' }),
}))

function Consumer() {
  const { medications, isError } = useMedication()
  return (
    <div>
      <span data-testid="error">{String(isError)}</span>
      <span data-testid="names">{medications.map((m) => m.medicine_name).join(',') || 'empty'}</span>
    </div>
  )
}

function renderProvider() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MedicationProvider>
        <Consumer />
      </MedicationProvider>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('MedicationContext 조회 실패 표면화', () => {
  it('조회에 성공하면 목록을 노출하고 isError 는 false 다', async () => {
    api.get.mockResolvedValue({ data: [{ id: 'm-1', medicine_name: '타이레놀', is_active: true }] })

    renderProvider()

    expect(await screen.findByText('타이레놀')).toBeInTheDocument()
    expect(screen.getByTestId('error'), '성공했는데 에러로 보이면 안 된다').toHaveTextContent('false')
  })

  it('조회에 실패하면 isError 로 실패를 전파한다', async () => {
    api.get.mockRejectedValue({ response: { status: 429 } })

    renderProvider()

    // 에러 span 안에서만 단언한다 — 페이지 전체 텍스트 검색은 이웃 요소에 걸려
    // 깨져도 통과할 수 있다(대장 D19).
    await waitFor(() =>
      expect(
        screen.getByTestId('error'),
        'isError 가 없으면 페이지는 실패를 "약이 하나도 없음"으로 렌더한다',
      ).toHaveTextContent('true'),
    )
    expect(
      screen.getByTestId('names'),
      '실패 시에도 빈 배열이라 소비자가 터지지 않는 기존 계약은 유지한다',
    ).toHaveTextContent('empty')
  })
})
