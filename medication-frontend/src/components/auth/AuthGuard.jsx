'use client'
import { useEffect, useState } from 'react'
import { useRouter, usePathname } from 'next/navigation'
import PropTypes from 'prop-types'
import api from '@/lib/api'
import { AUTH_STATUS, LOGOUT_REASON, getAuthStatus, markLoggedOut } from '@/lib/authStatus'
import LoadingSpinner from '@/components/common/LoadingSpinner'

// 인증이 필요하지 않은 공개 경로들 (화이트리스트)
const PUBLIC_ROUTES = [
  '/', // 랜딩 페이지
  '/login', // 로그인 페이지
]

// 경로가 공개 경로인지 확인
function isPublicRoute(pathname) {
  // 정확한 매치
  if (PUBLIC_ROUTES.includes(pathname)) {
    return true
  }

  // /auth로 시작하는 모든 경로 (로그인 처리 중)
  if (pathname.startsWith('/auth/')) {
    return true
  }

  return false
}

/**
 * 전역 라우팅 가드
 * 인증이 필요한 모든 페이지를 자동으로 보호
 */
export default function GlobalAuthGuard({ children }) {
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [isLoading, setIsLoading] = useState(true)
  const router = useRouter()
  const pathname = usePathname()

  useEffect(() => {
    const checkAuth = async () => {
      // 공개 경로는 인증 확인 생략
      if (isPublicRoute(pathname)) {
        setIsAuthenticated(true)
        setIsLoading(false)
        return
      }

      // 이미 인증 확인된 세션이면 라우트 이동 시 GET /profiles 재호출 안 함.
      // (로그아웃은 페이지 새로고침을 동반해 컴포넌트가 unmount → 다음 mount 시 isAuthenticated=false 로 자연 reset)
      if (isAuthenticated) {
        setIsLoading(false)
        return
      }

      try {
        // 인증 확인 API 호출 (인터셉터 비활성화로 빠른 판정 — RTR 은 skip)
        await api.get('/api/v1/profiles', {
          skipAuthInterceptor: true,
        })
        setIsAuthenticated(true)
      } catch (error) {
        // 로그인 힌트가 있었음에도 세션이 만료됐다면 "로그인 시간이 오래되어..."
        // 안내를 보여줘야 한다. 인터셉터를 우회했으므로 여기서 직접 marking.
        if (getAuthStatus() === AUTH_STATUS.LOGIN) {
          markLoggedOut({ reason: LOGOUT_REASON.SESSION_EXPIRED })
        }
        router.replace('/login')
        return
      } finally {
        setIsLoading(false)
      }
    }

    checkAuth()
  }, [router, pathname, isAuthenticated])

  // 로딩 중
  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-surface">
        <div className="flex flex-col items-center gap-4">
          <LoadingSpinner size="lg" />
          <p className="text-muted font-medium">인증 확인 중...</p>
        </div>
      </div>
    )
  }

  // 인증되지 않은 경우 아무것도 렌더링하지 않음 (리다이렉트 중)
  if (!isAuthenticated) {
    return null
  }

  // 인증된 경우 또는 공개 경로인 경우 자식 컴포넌트 렌더링
  return children
}

GlobalAuthGuard.propTypes = {
  children: PropTypes.node.isRequired,
}
