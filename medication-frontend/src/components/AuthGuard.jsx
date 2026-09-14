'use client'

import { useEffect, useState } from 'react'
import { usePathname } from 'next/navigation'
import api from '@/lib/api'

// 로그인 없이 접근 가능한 경로
const PUBLIC_PATHS = ['/', '/login']

// ── 인증 게이트 ───────────────────────────────────────────────────────
// 흐름: public 경로면 검사 없이 통과 -> 보호 경로면 /auth/me 확인
//       -> 성공 시 렌더, 실패 시 /login 으로 전체 리로드
// public 여부는 pathname 에서 바로 파생되므로 state 로 들고 있지 않는다
// (effect 안에서 setState 하면 렌더 -> effect -> 재렌더로 한 번 더 돈다).
export default function AuthGuard({ children }) {
  const pathname = usePathname()
  const isPublic = PUBLIC_PATHS.includes(pathname)
  // 보호 경로의 인증 확인 결과만 보관: null(확인 중) | 'ok' | 'redirect'
  const [authResult, setAuthResult] = useState(null)

  useEffect(() => {
    // public 경로는 확인 자체가 필요 없다 — 아래 렌더 분기에서 바로 통과시킨다.
    if (isPublic) return

    let cancelled = false
    api.get('/api/v1/auth/me')
      .then(() => {
        if (!cancelled) setAuthResult('ok')
      })
      .catch(() => {
        if (cancelled) return
        setAuthResult('redirect')
        // eslint-disable-next-line @next/next/no-location-assign-relative-destination -- 인증 실패 시 전체 리로드로 앱 상태 초기화 의도
        window.location.href = '/login'
      })

    // 경로가 바뀌면 이전 확인 결과가 뒤늦게 반영되지 않도록 무효화
    return () => {
      cancelled = true
    }
  }, [pathname, isPublic])

  if (isPublic) return children
  if (authResult === null) return <AuthSkeleton />
  if (authResult === 'redirect') return null

  return children
}

function AuthSkeleton() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-surface-2">
      <div className="flex flex-col items-center gap-3">
        <div className="w-10 h-10 bg-surface-2 rounded-xl animate-pulse" />
        <div className="w-24 h-3 bg-surface-2 rounded-full animate-pulse" />
      </div>
    </div>
  )
}
