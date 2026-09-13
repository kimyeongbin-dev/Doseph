// ── SymptomLogForm 특성화 테스트 (6C-B Phase 0 안전망) ───────────────
// 흐름: 현재 동작을 계약으로 못 박는다 -> 리팩터(H1~H3) 전후 불변 증명.
// 잠그는 동작(warning H1~H3 @ SymptomLogForm.jsx:100, exhaustive-deps):
//   initialSymptoms/initialNote prop 이 바뀌면 폼을 그 값으로 재동기화(reset).
//   (부모가 fetchTodaySymptoms 로 갱신 -> 같은 페이지 누적 기록 UX)
// api 는 mock. react-hook-form + zod 는 실제로 동작시켜 검증.

import { render, screen } from '@testing-library/react'

import SymptomLogForm from '@/components/lifestyle/SymptomLogForm'

vi.mock('@/lib/api', () => ({ default: { post: vi.fn() }, showError: vi.fn() }))

// preset 칩 선택 여부 = 활성 배경 클래스(bg-orange-500).
function chipSelected(name) {
  return screen.getByRole('button', { name }).className.includes('bg-orange-500')
}

describe('SymptomLogForm 특성화', () => {
  it('initialSymptoms 를 선택 상태로 반영한다', () => {
    render(<SymptomLogForm profileId="p1" initialSymptoms={['두통']} initialNote="" />)
    expect(chipSelected('두통')).toBe(true)
    expect(chipSelected('복통')).toBe(false)
  })

  it('initialSymptoms prop 이 바뀌면 폼을 새 값으로 재동기화한다 (H1~H3)', () => {
    const { rerender } = render(
      <SymptomLogForm profileId="p1" initialSymptoms={['두통']} initialNote="" />,
    )
    expect(chipSelected('두통')).toBe(true)

    rerender(<SymptomLogForm profileId="p1" initialSymptoms={['복통']} initialNote="" />)
    expect(chipSelected('복통')).toBe(true)
    expect(chipSelected('두통')).toBe(false)
  })
})
