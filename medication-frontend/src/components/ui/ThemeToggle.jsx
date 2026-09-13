'use client'
import { useSyncExternalStore } from 'react'
import { Sun, Moon } from 'lucide-react'

const THEME_KEY = 'theme'
const DARK_QUERY = '(prefers-color-scheme: dark)'

// ── 테마 외부 스토어 (localStorage + OS 선호) ─────────────────────────
// 흐름: React 바깥(localStorage·matchMedia)이 원본 -> subscribe 로 변경 구독
//       -> getSnapshot 이 현재 테마를 읽어 반환 -> React 가 렌더에 반영
// effect + setState 로 동기화하지 않는다(React 공식 권장: 외부 스토어는 useSyncExternalStore).
const listeners = new Set()

// 같은 탭에서의 변경(토글 클릭)을 구독자에게 알린다. 다른 탭은 storage 이벤트가 담당.
function emitThemeChange() {
  for (const listener of listeners) listener()
}

function subscribeTheme(listener) {
  listeners.add(listener)
  window.addEventListener('storage', listener)
  const mediaQuery = window.matchMedia(DARK_QUERY)
  mediaQuery.addEventListener('change', listener)

  return () => {
    listeners.delete(listener)
    window.removeEventListener('storage', listener)
    mediaQuery.removeEventListener('change', listener)
  }
}

// 저장값 우선, 없으면 OS 선호. 원시값(문자열)이라 스냅샷이 안정적이다.
function getThemeSnapshot() {
  let stored = null
  try {
    stored = localStorage.getItem(THEME_KEY)
  } catch {
    /* localStorage 접근 불가(프라이빗 모드 등) 시 OS 선호로 폴백 */
  }
  if (stored === 'dark' || stored === 'light') return stored
  return window.matchMedia(DARK_QUERY).matches ? 'dark' : 'light'
}

// 프리렌더(정적 export) 시점엔 테마가 미확정 -> null. 하이드레이션 불일치 방지.
function getThemeServerSnapshot() {
  return null
}

// ── 라이트/다크 테마 토글 ─────────────────────────────────────────────
// 흐름: 외부 스토어에서 현재 테마 구독 -> 클릭 시 <html data-theme> 갱신
//       + localStorage 저장 -> 변경 통지로 스냅샷 재읽기
//       (globals.css 의 :root[data-theme] 오버라이드와 연동. FOUC 방지 스크립트는 layout head)
export default function ThemeToggle({ className = '' }) {
  const theme = useSyncExternalStore(subscribeTheme, getThemeSnapshot, getThemeServerSnapshot)

  const toggle = () => {
    const next = theme === 'dark' ? 'light' : 'dark'
    document.documentElement.setAttribute('data-theme', next)
    try {
      localStorage.setItem(THEME_KEY, next)
    } catch {
      /* localStorage 접근 불가 시 무시 — data-theme 만 적용 */
    }
    emitThemeChange()
  }

  const base =
    'w-9 h-9 rounded-lg flex items-center justify-center text-muted ' +
    'hover:text-ink hover:bg-surface-2 transition-colors cursor-pointer ' +
    `focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent ${className}`

  // 하이드레이션 불일치 방지: 테마 미확정(서버 스냅샷) 구간엔 아이콘 없이 자리만 확보
  if (theme === null) return <span className={base} aria-hidden="true" />

  return (
    <button
      type="button"
      onClick={toggle}
      className={base}
      aria-label={theme === 'dark' ? '라이트 모드로 전환' : '다크 모드로 전환'}
    >
      {theme === 'dark' ? <Sun size={17} /> : <Moon size={17} />}
    </button>
  )
}
