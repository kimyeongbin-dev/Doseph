'use client'
import { useRouter, usePathname } from 'next/navigation'
import { Home, FileText, Trophy, Pill, User } from 'lucide-react'
import { useOcrEntryNavigator } from '@/contexts/OcrDraftContext'

export default function BottomNav() {
  const router = useRouter()
  const pathname = usePathname()
  const goToOcrEntry = useOcrEntryNavigator()

  // 랜딩 페이지에서는 표시하지 않음
  if (pathname === '/') return null

  // "등록" 탭은 진행 중/확인 대기 draft 가 있으면 result 로, 없으면 새 업로드(/ocr) 로
  // 보내는 정책을 useOcrEntryNavigator 가 담당. 다른 탭은 기존대로 router.push.
  const tabs = [
    { label: '홈', path: '/main', Icon: Home, onClick: () => router.push('/main') },
    { label: '등록', path: '/ocr', Icon: FileText, onClick: goToOcrEntry },
    { label: '챌린지', path: '/challenge', Icon: Trophy, onClick: () => router.push('/challenge') },
    {
      label: '가이드',
      path: '/lifestyle-guide',
      Icon: Pill,
      onClick: () => router.push('/lifestyle-guide'),
    },
    { label: '마이', path: '/mypage', Icon: User, onClick: () => router.push('/mypage') },
  ]

  return (
    <nav className="md:hidden fixed bottom-0 left-0 w-full bg-surface/95 backdrop-blur-lg border-t border-line flex py-3 px-2 z-50 shadow-[0_-5px_30px_rgba(0,0,0,0.08)] rounded-t-[28px]">
      {tabs.map(({ label, path, Icon, onClick }) => {
        const isActive = path === '/ocr' ? pathname.startsWith('/ocr') : pathname === path
        return (
          <button
            key={path}
            onClick={onClick}
            className="flex-1 flex flex-col items-center justify-center gap-1.5 group cursor-pointer"
          >
            <div
              className={`p-1 transition-all duration-300 ${isActive ? 'scale-110 text-accent' : 'text-muted'}`}
            >
              <Icon size={22} strokeWidth={isActive ? 2.5 : 2} />
            </div>
            <span
              className={`text-[10px] tracking-tight transition-all duration-300
              ${isActive ? 'text-ink font-black' : 'text-muted font-bold'}`}
            >
              {label}
            </span>
          </button>
        )
      })}
    </nav>
  )
}
