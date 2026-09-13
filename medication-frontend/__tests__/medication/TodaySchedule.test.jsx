// ── TodaySchedule 특성화 테스트 (6C-B Phase 0 안전망) ─────────────────
// 흐름: 현재 동작을 계약으로 못 박는다 -> 리팩터(K1) 전후 불변 증명.
// 잠그는 동작(warning K1 @ TodaySchedule.jsx:66, set-state-in-effect via fetch effect):
//   (1) 마운트 시 profileId 로 오늘 복약 로그 조회 -> TAKEN 로그를 완료로 반영
//   (2) intake_times 로 약을 시간대 블록에 분류, 시간 미설정 약은 별도 섹션
//   (3) medications 비면 빈 상태 안내
// api / useRouter 는 mock 으로 격리.

import { render, screen } from '@testing-library/react'

import TodaySchedule from '@/components/medication/TodaySchedule'
import api from '@/lib/api'

vi.mock('@/lib/api', () => ({
  default: { get: vi.fn(() => Promise.resolve({ data: [] })) },
}))
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))

beforeEach(() => {
  vi.clearAllMocks()
})

describe('TodaySchedule 특성화', () => {
  it('마운트 시 오늘 복약 로그를 조회하고 TAKEN 을 완료로 반영한다', async () => {
    api.get.mockResolvedValueOnce({
      data: [
        { id: 'log1', medication_id: 'med-1', intake_status: 'TAKEN', scheduled_time: '08:00:00' },
      ],
    })
    render(
      <TodaySchedule
        profileId="prof-1"
        medications={[{ id: 'med-1', medicine_name: '타이레놀', intake_times: ['08:00'] }]}
      />,
    )

    // 로그 조회 발생
    expect(api.get).toHaveBeenCalledWith('/api/v1/intake-logs', {
      params: { profile_id: 'prof-1', target_date: expect.any(String) },
    })
    // 완료 카운트가 1/1 로 반영될 때까지 대기(fetch 반영)
    expect(await screen.findByText(/1\/1\s*완료/)).toBeInTheDocument()
  })

  it('시간 미설정 약은 "복약 시간 미설정" 섹션에 표시한다', async () => {
    render(
      <TodaySchedule
        profileId="prof-1"
        medications={[{ id: 'med-2', medicine_name: '무설정약', intake_times: [] }]}
      />,
    )

    expect(await screen.findByText('복약 시간 미설정')).toBeInTheDocument()
    expect(screen.getByText('무설정약')).toBeInTheDocument()
  })

  it('medications 가 비면 빈 상태를 안내한다', () => {
    render(<TodaySchedule profileId="prof-1" medications={[]} />)
    expect(screen.getByText('오늘 등록된 복약 정보가 없습니다.')).toBeInTheDocument()
  })
})
