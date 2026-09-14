// ── ErrorState 계약 (조회 실패 표면화 · 1-d) ──────────────────────────
// 흐름: 조회 실패 -> ErrorState 렌더 -> 사용자가 '다시 시도' 클릭 -> onRetry 호출
// 잠그는 동작:
//   (1) 실패 문구와 재시도 버튼이 함께 보인다(둘 중 하나만 있으면 복구 불가)
//   (2) 재시도 클릭이 onRetry 를 정확히 1회 호출한다
//   (3) 재시도 중에는 버튼이 비활성 — 사용자가 연타로 레이트 리밋을 스스로 유발하지 못한다
//   (4) **서버가 보낸 4xx detail 원문을 화면에 그대로 노출하지 않는다**
//       (항상 보이는 화면이라 토스트보다 노출면이 넓다 — FE CLAUDE.md 5번)
// ⚠️ 의도적으로 단언하지 않는 것: 아이콘·여백 등 시각 표현. 문구와 상호작용만 계약이다.
// 전제: 없음(순수 컴포넌트, 백엔드 불필요).

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import ErrorState from '@/components/common/ErrorState'

// axios 에러 형태를 흉내낸다(응답 유무 + status + detail).
function makeAxiosError(status, detail) {
  return { response: { status, data: detail === undefined ? null : { detail } } }
}

describe('ErrorState', () => {
  it('실패 문구와 재시도 버튼을 함께 보여준다', () => {
    render(<ErrorState title="처방전을 불러오지 못했어요" onRetry={() => {}} />)

    expect(
      screen.getByText('처방전을 불러오지 못했어요'),
      '무엇이 실패했는지 제목으로 알 수 있어야 한다',
    ).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: '다시 시도' }),
      '재시도 수단이 없으면 사용자는 화면을 떠나는 것 말고 할 수 있는 게 없다',
    ).toBeInTheDocument()
  })

  it('재시도 클릭이 onRetry 를 정확히 1회 호출한다', async () => {
    const onRetry = vi.fn()
    const user = userEvent.setup()
    render(<ErrorState onRetry={onRetry} />)

    await user.click(screen.getByRole('button', { name: '다시 시도' }))

    expect(onRetry, '클릭이 재조회로 이어져야 복구 경로가 성립한다').toHaveBeenCalledTimes(1)
  })

  it('재시도 중에는 버튼이 비활성이다', () => {
    render(<ErrorState onRetry={() => {}} isRetrying />)

    expect(
      screen.getByRole('button', { name: '다시 시도 중...' }),
      '재조회 중임이 버튼에 드러나야 한다',
    ).toBeDisabled()
  })

  it('429 는 상태코드 표준 문구로 안내한다', () => {
    render(<ErrorState error={makeAxiosError(429)} onRetry={() => {}} />)

    expect(screen.getByText(/요청이 너무 많습니다/)).toBeInTheDocument()
  })

  it('4xx 의 서버 detail 원문을 화면에 노출하지 않는다', () => {
    render(
      <ErrorState error={makeAxiosError(400, 'medication_repo.py:88 invalid uuid')} onRetry={() => {}} />,
    )

    expect(
      screen.queryByText(/medication_repo/),
      '서버 내부 문자열이 항상 보이는 화면에 남으면 안 된다',
    ).not.toBeInTheDocument()
    expect(screen.getByText('잘못된 요청입니다.')).toBeInTheDocument()
  })

  it('5xx 는 고정 안내 문구를 쓴다', () => {
    render(<ErrorState error={makeAxiosError(500, '무엇이든 서버 원문')} onRetry={() => {}} />)

    expect(screen.queryByText(/서버 원문/)).not.toBeInTheDocument()
    expect(screen.getByText(/일시적인 오류가 발생했습니다/)).toBeInTheDocument()
  })
})
