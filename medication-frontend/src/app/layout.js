import { Geist, Geist_Mono } from 'next/font/google'
import { Toaster } from 'react-hot-toast'
import Script from 'next/script'
import './globals.css'
import Navigation from '@/components/layout/Navigation'
import BottomNav from '@/components/layout/BottomNav'
import GlobalAuthGuard from '@/components/auth/AuthGuard'
import QueryProvider from '@/providers/QueryProvider'
import { ConfirmProvider } from '@/components/common/ConfirmDialog'
import { ProfileProvider } from '@/contexts/ProfileContext'
import { MedicationProvider } from '@/contexts/MedicationContext'
import { PrescriptionGroupProvider } from '@/contexts/PrescriptionGroupContext'
import { ChallengeProvider } from '@/contexts/ChallengeContext'
import { LifestyleGuideProvider } from '@/contexts/LifestyleGuideContext'
import { OcrDraftProvider } from '@/contexts/OcrDraftContext'
import { ChatSessionProvider } from '@/contexts/ChatSessionContext'

// 폰트 최적화: preload와 display swap 적용
const geistSans = Geist({
  variable: '--font-geist-sans',
  subsets: ['latin'],
  display: 'swap', // 폰트 로딩 중 fallback 폰트 표시
  preload: true,
})

const geistMono = Geist_Mono({
  variable: '--font-geist-mono',
  subsets: ['latin'],
  display: 'swap',
  preload: true,
})

export const metadata = {
  title: 'Doseph',
  description: 'AI 기반 지능형 복약 관리 시스템',
}

export default function RootLayout({ children }) {
  return (
    <html
      lang="ko"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
      suppressHydrationWarning
    >
      <head>
        {/* DNS prefetch for external resources */}
        <link rel="dns-prefetch" href="//fonts.googleapis.com" />
        <link rel="dns-prefetch" href="//fonts.gstatic.com" />
        {/* Preconnect for faster font loading */}
        <link rel="preconnect" href="https://fonts.googleapis.com" crossOrigin="anonymous" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
      </head>
      <body className="min-h-full flex flex-col">
        {/* FOUC 방지: 저장된 테마를 하이드레이션 전에 <html>에 적용 */}
        <Script id="theme-init" strategy="beforeInteractive">
          {`(function(){try{var t=localStorage.getItem('theme');if(t==='dark'||t==='light'){document.documentElement.setAttribute('data-theme',t);}}catch(e){}})();`}
        </Script>
        <QueryProvider>
          <ConfirmProvider>
            <GlobalAuthGuard>
              <ProfileProvider>
                <MedicationProvider>
                  <PrescriptionGroupProvider>
                    <ChallengeProvider>
                      <LifestyleGuideProvider>
                        <OcrDraftProvider>
                          <ChatSessionProvider>
                            <Navigation />
                            {children}
                            <BottomNav />
                          </ChatSessionProvider>
                        </OcrDraftProvider>
                      </LifestyleGuideProvider>
                    </ChallengeProvider>
                  </PrescriptionGroupProvider>
                </MedicationProvider>
              </ProfileProvider>
            </GlobalAuthGuard>
          </ConfirmProvider>
        </QueryProvider>
        <Toaster
          position="top-center"
          toastOptions={{
            duration: 3000,
            style: {
              background: '#333',
              color: '#fff',
            },
            error: {
              duration: 4000,
            },
          }}
        />
      </body>
    </html>
  )
}
