// ── ChallengeContext 특성화 테스트 (6C-B 안전망 · B2 뿌리) ────────────
// 흐름: 현재 계약을 못 박는다 -> main/page 의 B2(effect 랜덤 선택) 리팩터 전후 불변 증명.
// 잠그는 동작:
//   (1) activeChallenges = challenge_status 'IN_PROGRESS' AND is_active 인 것만
//   (2) 같은 데이터로 리렌더돼도 파생 배열의 **참조가 유지**된다
//
// (2)가 왜 안전망인가: main/page 의 B2 effect 는 `[activeChallenges]` 에 의존한다.
// 파생 배열이 매 렌더 새 참조면 프로바이더가 리렌더될 때마다 effect 가 다시 돌아
// 표시 중인 챌린지가 임의로 재추첨된다. 참조 안정성이 그 재추첨의 뿌리이며,
// 같은 `data || []` 패턴이 다른 컨텍스트에도 있으므로 도메인 무관한 일반 계약이다.
//
// api / ProfileContext 는 mock 으로 격리(백엔드 불필요, 결정적).

import { useState } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { ChallengeProvider, useChallenge } from '@/contexts/ChallengeContext'
import api from '@/lib/api'

vi.mock('@/lib/api', () => ({
  default: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  showError: vi.fn(),
}))
vi.mock('@/contexts/ProfileContext', () => ({
  useProfile: () => ({ selectedProfileId: 'prof-1' }),
}))

// 챌린지 1건. overrides 로 활성/상태만 바꿔 필터 계약을 검증한다.
function makeChallenge(overrides = null) {
  return {
    id: 'ch-1',
    title: '물 마시기',
    description: '하루 2L',
    target_days: 7,
    challenge_status: 'IN_PROGRESS',
    is_active: true,
    ...(overrides || {}),
  }
}

// 컨슈머가 렌더될 때마다 activeChallenges 참조를 기록한다(참조 안정성 관찰용).
const renderedRefs = []

function Consumer() {
  const { activeChallenges } = useChallenge()
  renderedRefs.push(activeChallenges)
  return <span data-testid="titles">{activeChallenges.map((c) => c.title).join(',') || 'empty'}</span>
}

// 프로바이더 바깥의 state 를 바꿔 **프로바이더 자체의 리렌더**를 강제하는 하네스.
// (컨슈머만 리렌더되는 경우와 달리, 파생 셀렉터가 다시 계산되는 경로다.)
function Harness() {
  const [tick, setTick] = useState(0)
  return (
    <>
      <button onClick={() => setTick(tick + 1)}>리렌더</button>
      <ChallengeProvider>
        <Consumer />
      </ChallengeProvider>
    </>
  )
}

function renderHarness() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <Harness />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  renderedRefs.length = 0
})

describe('ChallengeContext 특성화', () => {
  it('activeChallenges 는 IN_PROGRESS 이면서 is_active 인 챌린지만 노출한다', async () => {
    api.get.mockResolvedValue({
      data: [
        makeChallenge({ id: 'a', title: '활성', is_active: true, challenge_status: 'IN_PROGRESS' }),
        makeChallenge({ id: 'b', title: '미시작', is_active: false, challenge_status: 'IN_PROGRESS' }),
        makeChallenge({ id: 'c', title: '완료', is_active: true, challenge_status: 'COMPLETED' }),
      ],
    })

    renderHarness()

    expect(await screen.findByText('활성')).toBeInTheDocument()
    expect(api.get).toHaveBeenCalledWith(expect.stringContaining('/api/v1/challenges?profile_id=prof-1'))
  })

  it('같은 데이터로 프로바이더가 리렌더돼도 activeChallenges 참조가 유지된다', async () => {
    api.get.mockResolvedValue({ data: [makeChallenge({ id: 'a', title: '활성' })] })

    const user = userEvent.setup()
    renderHarness()
    await screen.findByText('활성')

    const before = renderedRefs.at(-1)
    await user.click(screen.getByRole('button', { name: '리렌더' }))
    const after = renderedRefs.at(-1)

    expect(renderedRefs.length, '리렌더가 실제로 일어나야 비교가 성립한다').toBeGreaterThan(1)
    expect(
      after,
      'activeChallenges 가 매 렌더 새 배열이면 이를 의존성으로 쓰는 effect 가 매번 재실행된다',
    ).toBe(before)
  })
})
