// ── MedicineNameAutocomplete 특성화 테스트 (6C-B Phase 0 안전망) ──────
// 흐름: 현재 동작을 계약으로 못 박는다 -> 리팩터(I1) 전후 불변 증명.
// 잠그는 동작(warning I1 @ MedicineNameAutocomplete.jsx:52, set-state-in-effect):
//   (1) 사용자 typing + 최소 2자 -> debounce 후 GET /medicines/suggest -> dropdown open
//   (2) 2자 미만 -> fetch 안 함, dropdown 닫힘
//   (3) prefilled value(마운트 시, OCR 결과 등)는 fetch 스킵
// controlled 컴포넌트라 value/onChange 를 관리하는 상태 harness 로 감싼다. api 는 mock.

import { useState } from 'react'

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import MedicineNameAutocomplete from '@/components/medication/MedicineNameAutocomplete'
import api from '@/lib/api'

vi.mock('@/lib/api', () => ({
  default: { get: vi.fn(() => Promise.resolve({ data: [] })) },
}))

// value/onChange 를 실제로 관리하는 harness (controlled 계약 재현).
function Harness({ initialValue = '', onSelect }) {
  const [value, setValue] = useState(initialValue)
  return (
    <MedicineNameAutocomplete value={value} onChange={setValue} onSelectSuggestion={onSelect} />
  )
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('MedicineNameAutocomplete 특성화', () => {
  it('2자 이상 입력 시 debounce 후 제안을 조회해 dropdown 을 연다', async () => {
    api.get.mockResolvedValueOnce({
      data: [
        { id: 'm1', medicine_name: '타이레놀' },
        { id: 'm2', medicine_name: '타이레놀서방정' },
      ],
    })
    const user = userEvent.setup()
    render(<Harness />)

    await user.type(screen.getByRole('textbox'), '타이')

    // debounce(250ms) 후 조회 + 옵션 렌더
    expect(await screen.findByRole('option', { name: /타이레놀$/ })).toBeInTheDocument()
    expect(api.get).toHaveBeenCalledWith('/api/v1/medicines/suggest', {
      params: { q: '타이', limit: 8 },
      signal: expect.anything(),
    })
  })

  it('2자 미만 입력은 조회하지 않고 dropdown 을 열지 않는다', async () => {
    const user = userEvent.setup()
    render(<Harness />)

    await user.type(screen.getByRole('textbox'), '타')

    // 짧은 입력은 debounce 자체를 스케줄하지 않음 -> 조회 0회, listbox 없음
    await waitFor(() => expect(screen.queryByRole('listbox')).not.toBeInTheDocument())
    expect(api.get).not.toHaveBeenCalled()
  })

  it('마운트 시 prefilled value 는 조회를 스킵한다 (OCR 결과 등)', async () => {
    render(<Harness initialValue="아스피린" />)

    // 사용자 typing 이 없었으므로 fetch 스킵
    await waitFor(() => expect(screen.queryByRole('listbox')).not.toBeInTheDocument())
    expect(api.get).not.toHaveBeenCalled()
  })
})
