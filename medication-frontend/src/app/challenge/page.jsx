'use client'
import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import Header from '@/components/layout/Header'
import BottomNav from '@/components/layout/BottomNav'
import EmptyState from '@/components/common/EmptyState'
import { showError } from '@/lib/api'
import { useProfile } from '@/contexts/ProfileContext'
import { useChallenge, useChallengeStart } from '@/contexts/ChallengeContext'
import StartChallengeModal from '@/components/common/StartChallengeModal'
import { useConfirm } from '@/components/common/ConfirmDialog'
import { useLifestyleGuide } from '@/contexts/LifestyleGuideContext'
import toast from 'react-hot-toast'

// SVG 아이콘 컴포넌트 (진행중/완료 카드 아이콘 폴백용)
const Icons = {
  NoSmoking: ({ className = "w-6 h-6" }) => (
    <svg viewBox="0 0 24 24" fill="none" className={className} stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <line x1="4.93" y1="4.93" x2="19.07" y2="19.07" />
      <line x1="7" y1="12" x2="12" y2="12" />
      <line x1="15" y1="12" x2="17" y2="12" />
    </svg>
  ),
  Walking: ({ className = "w-6 h-6" }) => (
    <svg viewBox="0 0 24 24" fill="none" className={className} stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      <circle cx="13" cy="4" r="1.5" />
      <path d="M9 8.5l1.5 2L13 9l2 4H9" />
      <path d="M9 14l-1 4" />
      <path d="M14 13l1.5 4" />
    </svg>
  ),
  Pill: ({ className = "w-6 h-6" }) => (
    <svg viewBox="0 0 24 24" fill="none" className={className} stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      <path d="m10.5 20.5-8-8a5 5 0 1 1 7.07-7.07l8 8a5 5 0 1 1-7.07 7.07Z" />
      <line x1="8.5" y1="8.5" x2="15.5" y2="15.5" />
    </svg>
  ),
  Salad: ({ className = "w-6 h-6" }) => (
    <svg viewBox="0 0 24 24" fill="none" className={className} stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      <path d="M7 21h10" />
      <path d="M12 21a9 9 0 0 0 9-9H3a9 9 0 0 0 9 9Z" />
      <path d="M11.38 12a2.4 2.4 0 0 1-.4-4.77 2.4 2.4 0 0 1 3.2-3.19 2.4 2.4 0 0 1 3.47-.63 2.4 2.4 0 0 1 3.37 3.37 2.4 2.4 0 0 1-1.1 3.7" />
      <path d="m13 12 4-4" />
    </svg>
  ),
  Water: ({ className = "w-6 h-6" }) => (
    <svg viewBox="0 0 24 24" fill="none" className={className} stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 2C6 9 4 13 4 16a8 8 0 0 0 16 0c0-3-2-7-8-14Z" />
    </svg>
  ),
  Moon: ({ className = "w-6 h-6" }) => (
    <svg viewBox="0 0 24 24" fill="none" className={className} stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z" />
    </svg>
  ),
  Heart: ({ className = "w-6 h-6" }) => (
    <svg viewBox="0 0 24 24" fill="none" className={className} stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      <path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z" />
    </svg>
  ),
  Activity: ({ className = "w-6 h-6" }) => (
    <svg viewBox="0 0 24 24" fill="none" className={className} stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
    </svg>
  ),
  Coffee: ({ className = "w-6 h-6" }) => (
    <svg viewBox="0 0 24 24" fill="none" className={className} stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      <path d="M17 8h1a4 4 0 1 1 0 8h-1" />
      <path d="M3 8h14v9a4 4 0 0 1-4 4H7a4 4 0 0 1-4-4Z" />
      <line x1="6" y1="2" x2="6" y2="4" />
      <line x1="10" y1="2" x2="10" y2="4" />
      <line x1="14" y1="2" x2="14" y2="4" />
    </svg>
  ),
  Stretch: ({ className = "w-6 h-6" }) => (
    <svg viewBox="0 0 24 24" fill="none" className={className} stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="5" r="1" />
      <path d="M9 20l3-6 3 6" />
      <path d="M6 8l6 4 6-4" />
      <path d="M12 12v3" />
    </svg>
  ),
  Target: ({ className = "w-6 h-6" }) => (
    <svg viewBox="0 0 24 24" fill="none" className={className} stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <circle cx="12" cy="12" r="6" />
      <circle cx="12" cy="12" r="2" />
    </svg>
  ),
}

const DIFFICULTY_STYLE = {
  '쉬움':   { bg: 'bg-blue-50',   text: 'text-blue-500' },
  '보통':   { bg: 'bg-green-50',  text: 'text-green-500' },
  '어려움': { bg: 'bg-red-50',    text: 'text-red-500' },
}

const CATEGORY_META = {
  interaction: { label: '약물', color: 'bg-red-50 text-red-500' },
  sleep:       { label: '수면', color: 'bg-indigo-50 text-indigo-500' },
  diet:        { label: '식단', color: 'bg-green-50 text-green-500' },
  exercise:    { label: '운동', color: 'bg-blue-50 text-blue-500' },
  symptom:     { label: '증상', color: 'bg-orange-50 text-orange-500' },
}

function getDaysSince(startedDate) {
  const diff = Date.now() - new Date(startedDate).getTime()
  return Math.floor(diff / (1000 * 60 * 60 * 24)) + 1
}

export default function ChallengePage() {
  const router = useRouter()
  const confirm = useConfirm()
  const [activeTab, setActiveTab] = useState('추천')
  const [processingIds, setProcessingIds] = useState([])

  const { selectedProfileId: profileId } = useProfile()
  // 모든 server state 는 Context 가 단일 진실로 관리
  const {
    activeChallenges,
    completedChallenges,
    unstartedByGuide,
    isLoading: challengesLoading,
    checkChallenge,
    deleteChallenge,
  } = useChallenge()
  // 챌린지 시작은 어디서 호출하든 StartChallengeModal 확인 후 실행 (단일 정책)
  const { startTarget, isStarting, requestStart, cancelStart, confirmStart } = useChallengeStart()
  const { latestGuide, isLoading: guidesLoading } = useLifestyleGuide()
  const isLoading = challengesLoading || guidesLoading

  const getIconByTitle = (title) => {
    if (title.includes('금연')) return <Icons.NoSmoking />
    if (title.includes('걷기')) return <Icons.Walking />
    if (title.includes('복약')) return <Icons.Pill />
    if (title.includes('식단')) return <Icons.Salad />
    if (title.includes('물')) return <Icons.Water />
    if (title.includes('수면')) return <Icons.Moon />
    if (title.includes('혈압')) return <Icons.Heart />
    if (title.includes('혈당')) return <Icons.Activity />
    if (title.includes('카페인')) return <Icons.Coffee />
    if (title.includes('스트레칭')) return <Icons.Stretch />
    return <Icons.Target />
  }

  // 추천 = 최신 가이드의 미시작 챌린지 (Context 의 unstartedByGuide selector)
  const recommended = latestGuide ? unstartedByGuide(latestGuide.id) : []
  const noGuide = !guidesLoading && !latestGuide

  // ongoing/completed 는 derived (icon 추가만 페이지에서)
  const ongoing = activeChallenges.map(c => ({
    ...c,
    icon: getIconByTitle(c.title),
    current: c.completed_dates?.length || 0,
  }))
  const completed = completedChallenges.map(c => ({
    ...c,
    icon: getIconByTitle(c.title),
  }))

  // 모달 onConfirm — useChallengeStart 의 confirmStart 가 PATCH /start 호출.
  // 성공 시 Context 가 응답으로 list 자동 갱신 (active 로 이동, recommended 에서 자동 제거).
  const handleConfirmStart = async (difficulty, targetDays) => {
    try {
      const updated = await confirmStart(difficulty, targetDays)
      if (updated) {
        toast.success('챌린지가 시작되었습니다!')
        setActiveTab('진행중')
      }
    } catch (err) {
      showError(err.parsed?.message || '챌린지 시작에 실패했습니다.')
    }
  }

  const handleCheck = async (challenge) => {
    if (processingIds.includes(challenge.id)) return
    const today = new Date().toISOString().split('T')[0]

    if (challenge.completed_dates?.includes(today)) {
      showError('오늘은 이미 체크했습니다!')
      return
    }

    setProcessingIds(prev => [...prev, challenge.id])

    try {
      // 완료 날짜·진행 상태는 서버가 단독 결정한다 (POST /check). 클라는 트리거만.
      const updated = await checkChallenge(challenge.id)
      if (updated.challenge_status === 'COMPLETED') {
        toast.success('챌린지를 완료했습니다! 수고하셨어요.')
        setActiveTab('완료')
      }
    } catch (err) {
      showError(err.parsed?.message || '체크에 실패했습니다.')
    } finally {
      setProcessingIds(prev => prev.filter(id => id !== challenge.id))
    }
  }

  const handleAbandon = async (challenge) => {
    const ok = await confirm({
      title: '챌린지 포기',
      message: `'${challenge.title}' 챌린지를 포기하시겠습니까?`,
      confirmLabel: '포기',
      danger: true,
    })
    if (!ok) return
    try {
      await deleteChallenge(challenge.id)
      toast.success('챌린지가 삭제되었습니다.')
    } catch (err) {
      showError(err.parsed?.message || '삭제에 실패했습니다.')
    }
  }

  // started_date 내림차순 정렬 (최근 시작한 챌린지 먼저)
  const sortedOngoing = [...ongoing].sort(
    (a, b) => new Date(b.started_date) - new Date(a.started_date)
  )

  if (isLoading) {
    return (
      <main className="min-h-screen bg-surface-2 pb-24">
        <Header title="생활습관 챌린지" subtitle="건강한 습관을 만들어보세요" showBack={true} />
        <div className="max-w-3xl mx-auto px-6 py-6 space-y-4 animate-pulse">
          {[1, 2, 3].map(i => <div key={i} className="bg-surface rounded-2xl h-32 w-full" />)}
        </div>
        <BottomNav />
      </main>
    )
  }

  return (
    <main className="min-h-screen bg-surface-2 pb-24">
      <Header title="생활습관 챌린지" subtitle="건강한 습관을 만들어보세요" showBack={true} />

      <div className="max-w-3xl mx-auto px-6 py-6">
        <div className="flex gap-8 mb-8 border-b border-line">
          {['추천', '진행중', '완료'].map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`pb-3 text-sm font-bold cursor-pointer transition-colors relative active:scale-[0.98]
                ${activeTab === tab
                  ? 'text-ink border-b-2 border-accent'
                  : 'text-muted hover:text-muted'}`}
            >
              {tab}
              {tab === '진행중' && ongoing.length > 0 && (
                <span className="ml-1.5 bg-accent text-accent-ink text-[10px] px-1.5 py-0.5 rounded-full">
                  {ongoing.length}
                </span>
              )}
              {tab === '완료' && completed.length > 0 && (
                <span className="ml-1.5 bg-green-500 text-accent-ink text-[10px] px-1.5 py-0.5 rounded-full">
                  {completed.length}
                </span>
              )}
            </button>
          ))}
        </div>

        {/* 추천 탭 — AI 가이드 기반 */}
        {activeTab === '추천' && (
          <div className="space-y-3">
            {noGuide ? (
              <EmptyState
                title="아직 AI 추천 챌린지가 없어요"
                message="생활습관 가이드를 먼저 받아보세요"
                onAction={() => router.push('/lifestyle-guide')}
                actionLabel="가이드 받기"
              />
            ) : recommended.length === 0 ? (
              <EmptyState
                title="모든 추천 챌린지를 시작했습니다!"
                message="진행 중인 챌린지를 확인해보세요"
                onAction={() => setActiveTab('진행중')}
                actionLabel="진행중 보기"
              />
            ) : (
              recommended.map((item) => {
                const categoryMeta = item.category ? CATEGORY_META[item.category] : null
                return (
                  <div key={item.id} className="bg-surface rounded-2xl shadow-sm p-5 border border-line hover:border-blue-100 transition-all">
                    <div className="flex items-center justify-between gap-3">
                      <div className="flex items-center gap-4 flex-1 min-w-0">
                        <div className={`w-11 h-11 rounded-xl flex items-center justify-center shrink-0 ${categoryMeta ? categoryMeta.color : 'bg-surface-2 text-muted'}`}>
                          {getIconByTitle(item.title)}
                        </div>
                        <div className="min-w-0">
                          <h3 className="font-bold text-ink text-sm">{item.title}</h3>
                          <p className="text-muted text-xs mt-0.5 leading-relaxed line-clamp-1">{item.description}</p>
                          <div className="flex gap-1.5 mt-1.5">
                            <span className="bg-surface-2 text-muted text-[10px] px-2 py-0.5 rounded-full font-bold">{item.target_days}일</span>
                            {categoryMeta && (
                              <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${categoryMeta.color}`}>
                                {categoryMeta.label}
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                      <button
                        onClick={() => requestStart(item)}
                        disabled={isStarting}
                        className={`px-4 py-2 rounded-xl text-xs font-bold transition-colors shrink-0
                          ${isStarting
                            ? 'bg-surface-2 text-muted cursor-wait'
                            : 'bg-accent text-accent-ink hover:brightness-110 active:scale-95 shadow-sm'}`}
                      >
                        {isStarting && startTarget?.id === item.id ? '처리중...' : '시작하기'}
                      </button>
                    </div>
                  </div>
                )
              })
            )}
          </div>
        )}

        {/* 진행중 탭 — started_date 내림차순, D+N 표시 */}
        {activeTab === '진행중' && (
          <div className="space-y-4">
            {sortedOngoing.length > 0 ? (
              sortedOngoing.map((item) => {
                const isProcessing = processingIds.includes(item.id)
                const today = new Date().toISOString().split('T')[0]
                const checkedToday = item.completed_dates?.includes(today)
                const diffStyle = item.difficulty ? (DIFFICULTY_STYLE[item.difficulty] || DIFFICULTY_STYLE['보통']) : null
                const categoryMeta = item.category ? CATEGORY_META[item.category] : null
                return (
                  <div key={item.id} className="bg-surface rounded-2xl shadow-sm p-6 border border-line">
                    <div className="flex items-center gap-4 mb-5">
                      <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${categoryMeta ? categoryMeta.color : 'bg-surface-2 text-muted'}`}>
                        {item.icon}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <h3 className="font-bold text-ink">{item.title}</h3>
                          {categoryMeta && (
                            <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${categoryMeta.color}`}>
                              {categoryMeta.label}
                            </span>
                          )}
                          {diffStyle && !categoryMeta && (
                            <span className={`${diffStyle.bg} ${diffStyle.text} text-[10px] px-2 py-0.5 rounded-full font-bold`}>
                              {item.difficulty}
                            </span>
                          )}
                        </div>
                        <p className="text-muted text-xs mt-0.5">
                          {item.started_date
                            ? `D+${getDaysSince(item.started_date)} · ${item.target_days}일 목표`
                            : `${item.current}일째 진행 중`}
                        </p>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        <span className="text-blue-500 text-sm font-bold">{item.current}/{item.target_days}일</span>
                        <button
                          onClick={() => handleAbandon(item)}
                          className="w-7 h-7 flex items-center justify-center rounded-full text-muted hover:text-red-400 hover:bg-red-50 transition-all cursor-pointer"
                          title="챌린지 포기"
                        >
                          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-4 h-4">
                            <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
                          </svg>
                        </button>
                      </div>
                    </div>
                    <div className="w-full bg-surface-2 rounded-full h-2 mb-4 overflow-hidden">
                      <div
                        className="bg-blue-500 h-2 rounded-full transition-all duration-500 shadow-sm"
                        style={{ width: `${(item.current / item.target_days) * 100}%` }}
                      />
                    </div>
                    <button
                      onClick={() => handleCheck(item)}
                      disabled={isProcessing || checkedToday}
                      className={`w-full py-3.5 rounded-xl text-sm font-bold transition-colors active:scale-[0.98]
                        ${checkedToday
                          ? 'bg-green-50 text-green-500'
                          : isProcessing
                            ? 'bg-surface-2 text-muted cursor-wait'
                            : 'bg-surface-2 text-muted hover:bg-surface-2 cursor-pointer'}`}
                    >
                      {checkedToday ? '오늘 완료!' : isProcessing ? '처리중...' : '오늘 완료 체크'}
                    </button>
                  </div>
                )
              })
            ) : (
              <EmptyState title="진행 중인 챌린지가 없어요" message="AI 추천 챌린지를 시작해보세요!" onAction={() => setActiveTab('추천')} actionLabel="추천 챌린지 보기" />
            )}
          </div>
        )}

        {/* 완료 탭 */}
        {activeTab === '완료' && (
          <div className="space-y-4">
            {completed.length > 0 ? (
              completed.map((item) => {
                const diffStyle = item.difficulty ? (DIFFICULTY_STYLE[item.difficulty] || DIFFICULTY_STYLE['보통']) : null
                const categoryMeta = item.category ? CATEGORY_META[item.category] : null
                return (
                  <div key={item.id} className="bg-surface rounded-2xl shadow-sm p-6 border border-line opacity-80">
                    <div className="flex items-center gap-4">
                      <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${categoryMeta ? categoryMeta.color : 'bg-green-50 text-green-400'}`}>
                        {item.icon}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <h3 className="font-bold text-ink">{item.title}</h3>
                          {categoryMeta && (
                            <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${categoryMeta.color}`}>
                              {categoryMeta.label}
                            </span>
                          )}
                          {diffStyle && !categoryMeta && (
                            <span className={`${diffStyle.bg} ${diffStyle.text} text-[10px] px-2 py-0.5 rounded-full font-bold`}>
                              {item.difficulty}
                            </span>
                          )}
                        </div>
                        <p className="text-muted text-xs mt-0.5">
                          {item.target_days}일 달성
                          {item.started_date && <span className="ml-1">· {item.started_date} 시작</span>}
                        </p>
                      </div>
                      <span className="bg-green-50 text-green-500 text-xs font-bold px-3 py-1.5 rounded-full border border-green-100 shrink-0">
                        완료
                      </span>
                    </div>
                  </div>
                )
              })
            ) : (
              <EmptyState title="완료한 챌린지가 없어요" message="도전을 시작하고 목표를 달성해보세요!" onAction={() => setActiveTab('추천')} actionLabel="추천 챌린지 보기" />
            )}
          </div>
        )}
      </div>
      <BottomNav />

      {/* 챌린지 시작 확인 모달 — useChallengeStart 흐름 (모든 진입점 공통) */}
      {startTarget && (
        <StartChallengeModal
          challenge={startTarget}
          onConfirm={handleConfirmStart}
          onClose={cancelStart}
          isLoading={isStarting}
        />
      )}
    </main>
  )
}
