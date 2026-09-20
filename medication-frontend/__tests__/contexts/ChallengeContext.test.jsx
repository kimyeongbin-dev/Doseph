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
import { render, screen, waitFor } from '@testing-library/react'
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
  const { activeChallenges, unstartedByGuide, isError } = useChallenge()
  renderedRefs.push(activeChallenges)
  return (
    <div>
      <span data-testid="titles">{activeChallenges.map((c) => c.title).join(',') || 'empty'}</span>
      <span data-testid="unstarted">
        {unstartedByGuide('guide-1')
          .map((c) => c.title)
          .join(',') || 'empty'}
      </span>
      <span data-testid="error">{String(isError)}</span>
    </div>
  )
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

  // ── 추천 탭의 "미시작" 계약 ────────────────────────────────────────
  // 백엔드 정의(`challenge_repository.not_started`)와 **같아야 한다**:
  //   is_active = false  AND  challenge_status != 'COMPLETED'
  // 🔴 예전 구현은 `!== 'DELETED'` 로 걸렀는데, ChallengeStatus enum 에는
  //    IN_PROGRESS / COMPLETED 뿐이라 **아무것도 안 거르는 no-op** 이었다.
  //    폐지된 soft delete(QA-01)의 잔재이자, 완료된 비활성 챌린지가
  //    추천 탭에 되살아나는 경로였다(QA-38).
  it('unstartedByGuide 는 같은 가이드의 미시작 챌린지만 준다', async () => {
    api.get.mockResolvedValue({
      data: [
        makeChallenge({ id: 'u', title: '미시작', guide_id: 'guide-1', is_active: false }),
        makeChallenge({ id: 'a', title: '시작함', guide_id: 'guide-1', is_active: true }),
        makeChallenge({ id: 'o', title: '다른가이드', guide_id: 'guide-2', is_active: false }),
      ],
    })

    renderHarness()

    await screen.findByText('미시작')
    // 바닥값 — 목록이 비면 `not.toContain` 은 무조건 통과한다(D49).
    expect(screen.getByTestId('unstarted').textContent).toBe('미시작')
  })

  it('unstartedByGuide 는 완료된 비활성 챌린지를 추천에 되살리지 않는다', async () => {
    api.get.mockResolvedValue({
      data: [
        makeChallenge({ id: 'u', title: '미시작', guide_id: 'guide-1', is_active: false }),
        makeChallenge({
          id: 'c',
          title: '완료했지만비활성',
          guide_id: 'guide-1',
          is_active: false,
          challenge_status: 'COMPLETED',
        }),
      ],
    })

    renderHarness()

    // 🔴 `findByText` 는 정확 일치라 합쳐진 텍스트를 못 찾는다 — testid 로 기다린다.
    await waitFor(() => expect(screen.getByTestId('unstarted').textContent).toContain('미시작'))
    const shown = screen.getByTestId('unstarted').textContent
    expect(shown, '표본이 비면 이 단언은 공짜로 통과한다').toContain('미시작')
    expect(shown).not.toContain('완료했지만비활성')
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

  // 1-d: 챌린지 페이지는 세 탭 모두 이 한 쿼리에서 파생되므로, 실패가 뭉개지면
  // "추천도 없고 진행중도 없고 완료도 없는" 화면이 통째로 거짓이 된다.
  it('조회에 실패하면 isError 로 실패를 전파한다', async () => {
    api.get.mockRejectedValue({ response: { status: 429 } })

    renderHarness()

    // 에러 span 안에서만 단언한다 — 페이지 전체 텍스트 검색은 이웃 요소에 걸려
    // 깨져도 통과할 수 있다(대장 D19).
    await waitFor(() =>
      expect(
        screen.getByTestId('error'),
        'isError 가 없으면 조회 실패가 "아직 추천 챌린지가 없어요"로 보인다',
      ).toHaveTextContent('true'),
    )
    expect(screen.getByTestId('titles'), '실패해도 빈 배열 계약은 유지한다').toHaveTextContent('empty')
  })
})
