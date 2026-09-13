// ── ProfileContext 특성화 테스트 (6C-B Phase 0 안전망) ────────────────
// 흐름: 현재 동작을 계약으로 못 박는다 -> 리팩터(P1/P2) 전후 불변 증명.
// 잠그는 동작(warning P1/P2 @ ProfileContext.jsx:70,78, deps + set-state-in-effect):
//   selectedProfileId 자동 정합 effect 의 3분기 —
//   (1) 저장값 없음 -> SELF 프로필로 폴백(없으면 첫 프로필) + localStorage 저장
//   (2) localStorage 저장값이 목록에 존재 -> 그 값 복원
//   (3) 저장값이 목록에 없음 -> SELF 폴백
// TanStack Query 기반이라 QueryClientProvider + api mock + non-public path 로 격리.

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'

import { ProfileProvider, useProfile } from '@/contexts/ProfileContext'
import api from '@/lib/api'

vi.mock('@/lib/api', () => ({
  default: { get: vi.fn() },
}))
// 인증 라우트(비-public)여야 list query 가 enabled -> profiles fetch.
vi.mock('next/navigation', () => ({
  usePathname: () => '/main',
}))

const STORAGE_KEY = 'selectedProfileId'

const PROFILES = [
  { id: 'p1', name: '엄마', relation_type: 'MOTHER' },
  { id: 'p2', name: '나', relation_type: 'SELF' },
  { id: 'p3', name: '아들', relation_type: 'SON' },
]

function Consumer() {
  const { selectedProfileId, profiles } = useProfile()
  return (
    <div>
      <span data-testid="selected">{selectedProfileId ?? 'none'}</span>
      <span data-testid="count">{profiles.length}</span>
    </div>
  )
}

function renderProvider() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <ProfileProvider>
        <Consumer />
      </ProfileProvider>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  api.get.mockResolvedValue({ data: PROFILES })
})

describe('ProfileContext selectedProfileId 정합', () => {
  it('저장값 없으면 SELF 프로필로 폴백하고 localStorage 에 저장한다', async () => {
    renderProvider()

    expect(await screen.findByText('3')).toBeInTheDocument() // profiles 로드 완료
    expect(screen.getByTestId('selected')).toHaveTextContent('p2') // SELF
    expect(localStorage.getItem(STORAGE_KEY)).toBe('p2')
  })

  it('localStorage 저장값이 목록에 있으면 그 값을 복원한다', async () => {
    localStorage.setItem(STORAGE_KEY, 'p3')
    renderProvider()

    expect(await screen.findByText('3')).toBeInTheDocument()
    expect(screen.getByTestId('selected')).toHaveTextContent('p3')
  })

  it('localStorage 저장값이 목록에 없으면 SELF 로 폴백한다', async () => {
    localStorage.setItem(STORAGE_KEY, 'ghost')
    renderProvider()

    expect(await screen.findByText('3')).toBeInTheDocument()
    expect(screen.getByTestId('selected')).toHaveTextContent('p2') // SELF 폴백
    expect(localStorage.getItem(STORAGE_KEY)).toBe('p2')
  })
})
