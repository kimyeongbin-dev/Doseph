'use client'
import { useEffect, useRef, Suspense } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import api, { parseApiError, showError } from '@/lib/api'
import { markLoggedIn } from '@/lib/authStatus'

// 메인 페이지 스켈레톤 UI
function MainSkeleton() {
  return (
    <main className="min-h-screen bg-surface-2 animate-pulse">
      {/* 상단 헤더 스켈레톤 */}
      <div className="bg-surface px-10 py-4 shadow-sm">
        <div className="h-4 w-24 bg-surface-2 rounded mb-2" />
        <div className="h-6 w-32 bg-surface-2 rounded" />
      </div>

      <div className="p-10 grid grid-cols-2 gap-4">
        {/* 오늘 복약 현황 스켈레톤 */}
        <div className="bg-surface rounded-2xl shadow-sm p-6 col-span-2">
          <div className="h-5 w-32 bg-surface-2 rounded mb-4" />
          <div className="h-4 w-48 bg-surface-2 rounded" />
        </div>

        {/* 챗봇 버튼 스켈레톤 */}
        <div className="bg-surface-2 rounded-2xl p-6">
          <div className="h-4 w-32 bg-surface-2 rounded mb-2" />
          <div className="h-6 w-40 bg-surface-2 rounded" />
        </div>

        {/* 처방전 업로드 스켈레톤 */}
        <div className="bg-surface rounded-2xl shadow-sm p-6">
          <div className="h-5 w-24 bg-surface-2 rounded mb-2" />
          <div className="h-4 w-36 bg-surface-2 rounded mb-4" />
          <div className="w-full border-2 border-dashed border-line py-4 rounded-xl">
            <div className="h-4 w-16 bg-surface-2 rounded mx-auto" />
          </div>
        </div>
      </div>

      {/* 하단 네비게이션 스켈레톤 */}
      <div className="fixed bottom-0 w-full bg-surface border-t border-line flex">
        <div className="flex-1 py-4 flex justify-center">
          <div className="h-4 w-8 bg-surface-2 rounded" />
        </div>
        <div className="flex-1 py-4 flex justify-center">
          <div className="h-4 w-16 bg-surface-2 rounded" />
        </div>
      </div>
    </main>
  )
}

function KakaoCallbackContent() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const isProcessing = useRef(false)

  useEffect(() => {
    const handleCallback = async () => {
      // 1. URL에서 code, state, error 추출
      const code = searchParams.get('code')
      const state = searchParams.get('state')
      const errorParam = searchParams.get('error')
      const errorDescription = searchParams.get('error_description')

      // searchParams가 아직 로드되지 않은 경우 대기 (Next.js hydration)
      if (!code && !errorParam) {
        return
      }

      // 중복 실행 방지 (React 18 Strict Mode, 브라우저 캐시 등)
      if (isProcessing.current) return
      isProcessing.current = true

      // 에러 발생 시 Toast + 로그인 페이지로 리다이렉트
      const handleError = (message) => {
        showError(message)
        setTimeout(() => router.replace('/login'), 1500)
      }

      // 카카오에서 에러 응답이 온 경우
      if (errorParam) {
        handleError(errorDescription || '카카오 로그인 중 오류가 발생했습니다.')
        return
      }

      // 2. state 검증 (CSRF 방지) - localStorage 사용 (모든 탭에서 공유 — 이유는 login/page.jsx, QA-36)
      // 이 비교가 "이 브라우저가 로그인을 시작했다" 를 묶는 유일한 자리다.
      // 서버의 HMAC 검증은 "우리가 최근에 발급했다" 까지만 증명한다(공격자도 자기 몫의 state 를 받을 수 있다).
      const savedState = localStorage.getItem('oauth_state')
      if (!savedState || savedState !== state) {
        localStorage.removeItem('oauth_state')
        handleError('유효하지 않은 요청입니다.')
        return
      }

      // state 사용 완료 후 삭제 (재사용 방지)
      localStorage.removeItem('oauth_state')

      try {
        // 3. BE에 인가 코드 전달하여 로그인 처리
        // access_token은 HttpOnly 쿠키로 자동 저장됨
        const response = await api.get('/api/v1/auth/kakao/callback', {
          params: { code, state },
        })

        // 로그인 성공 — 이후 재접속자 판별용 힌트 기록
        markLoggedIn()

        // 4. 신규 사용자면 메인 위에 설문 모달 팝업 (HealthSurveyModal SSOT 컴포넌트)
        //    dev 로그인 흐름과 동일하게 ?showSurvey=true 로 진입 → 메인 페이지가
        //    팝업 띄움. 별도 /survey 페이지로 가지 않음 (PR #134 통합 SSOT).
        const { show_survey } = response.data
        if (show_survey) {
          router.replace('/main?showSurvey=true')
        } else {
          router.replace('/main')
        }
      } catch (err) {
        console.error('로그인 처리 실패:', err)
        const parsed = err.parsed || parseApiError(err)
        handleError(parsed.message)
      }
    }

    handleCallback()
  }, [searchParams, router])

  // 로딩 중 - 메인 페이지 스켈레톤 표시
  return <MainSkeleton />
}

export default function KakaoCallbackPage() {
  return (
    <Suspense fallback={<MainSkeleton />}>
      <KakaoCallbackContent />
    </Suspense>
  )
}
