// ── ThemeToggle 특성화 테스트 (6C-B Phase 0 안전망) ──────────────────
// 흐름: 현재 동작을 계약으로 못 박는다 -> 리팩터(L1: useSyncExternalStore 정석) 전후 불변 증명.
// 잠그는 동작(warning L1, set-state-in-effect @ ThemeToggle.jsx:14):
//   (1) 마운트 시 localStorage('theme') 우선, 없으면 OS(prefers-color-scheme) 선호로 테마 결정
//   (2) 클릭 시 테마 전환 + <html data-theme> 갱신 + localStorage 저장
//   (3) 마운트 후 aria-label 이 현재 테마 기준으로 표시(하이드레이션 가드 통과)
// effect 는 이 테스트 통과를 유지하며 리팩터한다.

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import ThemeToggle from '@/components/ui/ThemeToggle'

// OS 선호 stub — jsdom 은 matchMedia 미구현이라 테스트마다 명시적으로 주입한다.
function stubMatchMedia(prefersDark) {
  window.matchMedia = () => ({
    matches: prefersDark,
    media: '(prefers-color-scheme: dark)',
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  })
}

beforeEach(() => {
  localStorage.clear()
  document.documentElement.removeAttribute('data-theme')
  stubMatchMedia(false)
})

describe('ThemeToggle 특성화', () => {
  it('저장된 테마(light)를 반영해 "다크로 전환" 버튼을 보인다', () => {
    localStorage.setItem('theme', 'light')
    render(<ThemeToggle />)

    // light 상태 -> 다음 전환 대상은 dark -> aria-label 이 "다크 모드로 전환"
    expect(screen.getByRole('button', { name: '다크 모드로 전환' })).toBeInTheDocument()
  })

  it('저장된 테마(dark)를 반영해 "라이트로 전환" 버튼을 보인다', () => {
    localStorage.setItem('theme', 'dark')
    render(<ThemeToggle />)

    expect(screen.getByRole('button', { name: '라이트 모드로 전환' })).toBeInTheDocument()
  })

  it('저장값이 없으면 OS 선호(dark)를 따른다', () => {
    stubMatchMedia(true) // prefers dark
    render(<ThemeToggle />)

    expect(screen.getByRole('button', { name: '라이트 모드로 전환' })).toBeInTheDocument()
  })

  it('클릭 시 테마가 전환되고 <html data-theme> + localStorage 에 저장된다', async () => {
    const user = userEvent.setup()
    localStorage.setItem('theme', 'light')
    render(<ThemeToggle />)

    await user.click(screen.getByRole('button', { name: '다크 모드로 전환' }))

    // 전환 결과: dark
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
    expect(localStorage.getItem('theme')).toBe('dark')
    // aria-label 도 이제 "라이트 모드로 전환"으로 뒤집힘
    expect(screen.getByRole('button', { name: '라이트 모드로 전환' })).toBeInTheDocument()
  })
})
