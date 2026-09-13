// ── TimeSlotPicker 특성화 테스트 (6C-B Phase 0 안전망) ────────────────
// 흐름: 현재 동작을 계약으로 못 박는다 -> 리팩터(J1: props->state 동기화) 전후 불변 증명.
// 잠그는 동작(warning J1/J2 @ TimeSlotPicker.jsx:32-33, set-state-in-effect + deps):
//   (1) intake_times 를 슬롯 활성 상태로 반영(HH:MM 정규화)
//   (2) medication.id 가 바뀌면 currentTimes 를 새 약 기준으로 재초기화  <- 핵심 리팩터 대상
//   (3) 슬롯 토글 시 낙관적 반영 + PATCH 호출
// api / MedicationContext 는 mock 으로 격리(백엔드 불필요, 결정적).

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import TimeSlotPicker from '@/components/medication/TimeSlotPicker'
import api from '@/lib/api'
import { makeMedication } from '@/../__tests__/fixtures'

vi.mock('@/lib/api', () => ({
  default: { patch: vi.fn(() => Promise.resolve({ data: {} })) },
}))
vi.mock('@/contexts/MedicationContext', () => ({
  useMedication: () => ({ refetchMedications: vi.fn(() => Promise.resolve()) }),
}))

// 활성 슬롯 = accent 배경 클래스가 붙은 버튼(현재 DOM 계약).
function isSlotActive(name) {
  return screen.getByRole('button', { name }).className.includes('bg-accent')
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('TimeSlotPicker 특성화', () => {
  it('4개 슬롯을 렌더하고 intake_times 를 활성 상태로 반영한다', () => {
    render(<TimeSlotPicker medication={makeMedication({ intake_times: ['08:00'] })} />)

    expect(screen.getByRole('button', { name: '아침' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '점심' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '저녁' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '취침' })).toBeInTheDocument()

    expect(isSlotActive('아침')).toBe(true)
    expect(isSlotActive('저녁')).toBe(false)
  })

  it('HH:MM:SS 형식도 HH:MM 으로 정규화해 반영한다', () => {
    render(<TimeSlotPicker medication={makeMedication({ intake_times: ['19:00:00'] })} />)
    expect(isSlotActive('저녁')).toBe(true)
    expect(isSlotActive('아침')).toBe(false)
  })

  it('medication.id 가 바뀌면 시간대를 새 약 기준으로 재초기화한다 (J1 핵심)', () => {
    const { rerender } = render(
      <TimeSlotPicker medication={makeMedication({ id: 'med-A', intake_times: ['08:00'] })} />,
    )
    expect(isSlotActive('아침')).toBe(true)
    expect(isSlotActive('저녁')).toBe(false)

    rerender(<TimeSlotPicker medication={makeMedication({ id: 'med-B', intake_times: ['19:00'] })} />)
    expect(isSlotActive('아침')).toBe(false)
    expect(isSlotActive('저녁')).toBe(true)
  })

  it('비활성 슬롯 토글 시 낙관적으로 활성화하고 PATCH 를 호출한다', async () => {
    const user = userEvent.setup()
    render(<TimeSlotPicker medication={makeMedication({ id: 'med-1', intake_times: ['08:00'] })} />)

    await user.click(screen.getByRole('button', { name: '점심' }))

    // 낙관적 반영
    expect(isSlotActive('점심')).toBe(true)
    // PATCH 호출(정렬된 next 배열 포함)
    expect(api.patch).toHaveBeenCalledWith('/api/v1/medications/med-1', {
      intake_times: ['08:00', '13:00'],
    })
  })
})
