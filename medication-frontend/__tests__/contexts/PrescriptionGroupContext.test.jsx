// ── PrescriptionGroupContext 특성화 테스트 (6C-B Phase 0 안전망) ──────
// 흐름: 현재 동작을 계약으로 못 박는다 -> 리팩터(O1, exhaustive-deps) 전후 불변 증명.
// 잠그는 동작: 마운트 시 선택 프로필로 처방전 그룹 목록 조회 -> groups 노출 + 기본 정렬(DATE_DESC).
// TanStack Query 기반이라 QueryClientProvider + api/useProfile/useMedication mock 으로 격리.

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'

import { PrescriptionGroupProvider, usePrescriptionGroup } from '@/contexts/PrescriptionGroupContext'
import api from '@/lib/api'

vi.mock('@/lib/api', () => ({ default: { get: vi.fn() } }))
vi.mock('@/contexts/ProfileContext', () => ({ useProfile: () => ({ selectedProfileId: 'prof-1' }) }))
vi.mock('@/contexts/MedicationContext', () => ({ useMedication: () => ({ medications: [] }) }))

function Consumer() {
  const { groups, isLoading } = usePrescriptionGroup()
  return (
    <div>
      <span data-testid="loading">{String(isLoading)}</span>
      <span data-testid="ids">{groups.map((g) => g.id).join(',') || 'empty'}</span>
    </div>
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

beforeEach(() => vi.clearAllMocks())

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
})
