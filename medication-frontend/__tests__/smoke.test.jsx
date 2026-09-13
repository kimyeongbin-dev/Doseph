// ── 테스트 하네스 스모크 (6C-A) ──────────────────────────────────────
// 흐름: 자족적 컴포넌트를 렌더 -> jest-dom 매처 확인 -> user-event 클릭 -> state 갱신 확인.
// 목적: Vitest + jsdom + @vitejs/plugin-react(JSX) + RTL + user-event + jest-dom 배선이
//       전부 정상 동작함을 한 번에 검증. (실제 앱 컴포넌트 특성화는 6C-B Phase 0.)

import { useState } from 'react'

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

// 외부 의존 없는 자족 컴포넌트 — 파이프라인 검증 전용.
function Counter() {
  const [count, setCount] = useState(0)
  return (
    <button type="button" onClick={() => setCount((c) => c + 1)}>
      count: {count}
    </button>
  )
}

describe('테스트 하네스 스모크', () => {
  it('JSX 컴포넌트를 렌더하고 jest-dom 매처가 동작한다', () => {
    render(<Counter />)
    expect(screen.getByRole('button')).toBeInTheDocument()
    expect(screen.getByRole('button')).toHaveTextContent('count: 0')
  })

  it('user-event 클릭으로 state 가 갱신되어 리렌더된다', async () => {
    const user = userEvent.setup()
    render(<Counter />)

    await user.click(screen.getByRole('button'))
    expect(screen.getByRole('button')).toHaveTextContent('count: 1')

    await user.click(screen.getByRole('button'))
    expect(screen.getByRole('button')).toHaveTextContent('count: 2')
  })
})
