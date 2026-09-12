'use client'

import { useEffect, useState } from 'react'
import { usePathname } from 'next/navigation'
import api from '@/lib/api'

// 로그인 없이 접근 가능한 경로
const PUBLIC_PATHS = ['/', '/login']

export default function AuthGuard({ children }) {
  const pathname = usePathname()
  const isPublic = PUBLIC_PATHS.includes(pathname)
  // 'checking' | 'ok' | 'redirect'
  const [status, setStatus] = useState('checking')

  useEffect(() => {
    if (isPublic) {
      setStatus('ok')
      return
    }

    api.get('/api/v1/auth/me')
      .then(() => setStatus('ok'))
      .catch(() => {
        setStatus('redirect')
        // eslint-disable-next-line @next/next/no-location-assign-relative-destination -- 인증 실패 시 전체 리로드로 앱 상태 초기화 의도
        window.location.href = '/login'
      })
  }, [pathname, isPublic])

  if (!isPublic && status === 'checking') {
    return <AuthSkeleton />
  }

  if (status === 'redirect') return null

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
