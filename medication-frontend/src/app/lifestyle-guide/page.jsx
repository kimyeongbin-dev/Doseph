'use client'
// [신규 파일] 생활습관 가이드 페이지 (/lifestyle-guide)
// - AI가 생성한 5개 카테고리(약물상호작용/수면/식단/운동/증상) 가이드를 탭으로 표시
// - 이력 날짜 칩으로 과거 가이드 조회 가능 (과거 가이드는 챌린지 버튼 비활성화)
// - 각 탭에 연결된 챌린지를 하단 배너로 표시 (3-상태: 시작 전/진행중/완료)
// - 증상 탭에는 오늘의 일일 증상 로그 입력 폼 포함
import { useState, useEffect, useRef, Suspense } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import Header from '@/components/layout/Header'
import BottomNav from '@/components/layout/BottomNav'
import EmptyState from '@/components/common/EmptyState'
import api, { showError } from '@/lib/api'
import { useProfile } from '@/contexts/ProfileContext'
import { useLifestyleGuide } from '@/contexts/LifestyleGuideContext'
import { useChallenge, useChallengeStart, useChallengeCheck } from '@/contexts/ChallengeContext'
import { usePrescriptionGroup } from '@/contexts/PrescriptionGroupContext'
import StartChallengeModal from '@/components/common/StartChallengeModal'
import { useConfirm } from '@/components/common/ConfirmDialog'
import PrescriptionPickerModal from '@/components/lifestyle/PrescriptionPickerModal'
import SymptomLogForm from '@/components/lifestyle/SymptomLogForm'
import toast from 'react-hot-toast'
import { AlertTriangle, Moon, Utensils, Dumbbell, Stethoscope, ChevronLeft, ChevronRight } from 'lucide-react'


const CHALLENGES_PER_PAGE = 5

const TABS = [
  {
    key: 'interaction',
    label: '약물 상호작용',
    icon: <AlertTriangle size={16} />,
    color: 'text-red-500',
    bg: 'bg-red-50',
    border: 'border-red-200',
    activeBorder: 'border-red-500',
  },
  {
    key: 'sleep',
    label: '수면·생체리듬',
    icon: <Moon size={16} />,
    color: 'text-indigo-500',
    bg: 'bg-indigo-50',
    border: 'border-indigo-200',
    activeBorder: 'border-indigo-500',
  },
  {
    key: 'diet',
    label: '식단·수분',
    icon: <Utensils size={16} />,
    color: 'text-green-500',
    bg: 'bg-green-50',
    border: 'border-green-200',
    activeBorder: 'border-green-500',
  },
  {
    key: 'exercise',
    label: '운동',
    icon: <Dumbbell size={16} />,
    color: 'text-blue-500',
    bg: 'bg-blue-50',
    border: 'border-blue-200',
    activeBorder: 'border-blue-500',
  },
  {
    key: 'symptom',
    label: '증상 트래킹',
    icon: <Stethoscope size={16} />,
    color: 'text-orange-500',
    bg: 'bg-orange-50',
    border: 'border-orange-200',
    activeBorder: 'border-orange-500',
  },
]

const DIFFICULTY_STYLE = {
  '쉬움': { bg: 'bg-blue-50', text: 'text-blue-500' },
  '보통': { bg: 'bg-green-50', text: 'text-green-500' },
  '어려움': { bg: 'bg-red-50', text: 'text-red-500' },
}

function formatDate(isoStr) {
  const d = new Date(isoStr)
  return `${d.getMonth() + 1}/${d.getDate()}`
}

function formatFullDateTime(isoStr) {
  const d = new Date(isoStr)
  const yyyy = d.getFullYear()
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  const HH = String(d.getHours()).padStart(2, '0')
  const MM = String(d.getMinutes()).padStart(2, '0')
  return `${yyyy}.${mm}.${dd} ${HH}:${MM}`
}

function summarizePrescribedRange(snapshot) {
  if (!Array.isArray(snapshot) || snapshot.length === 0) return null
  const dates = snapshot
    .map((m) => (typeof m === 'object' ? m.dispensed_date || m.start_date : null))
    .filter(Boolean)
    .sort()
  if (dates.length === 0) return null
  const first = dates[0].slice(0, 10).replace(/-/g, '.')
  const last = dates[dates.length - 1].slice(0, 10).replace(/-/g, '.')
  return first === last ? first : `${first} ~ ${last}`
}

// ── 챌린지 배너 컴포넌트 ────────────────────────────────────────────────────────
function ChallengeBanner({ challenge, isViewingHistory }) {
  const router = useRouter()
  const { isStarting, startTarget, requestStart } = useChallengeStart()
  const { checkingId, checkToday } = useChallengeCheck()

  if (!challenge) return null

  const isStartingThis = isStarting && startTarget?.id === challenge.id
  const isChecking = checkingId === challenge.id
  const isProcessing = isStartingThis || isChecking

  const today = new Date().toISOString().split('T')[0]
  const checkedToday = challenge.completed_dates?.some(
    (d) => (typeof d === 'string' ? d : d.toISOString?.().split('T')[0]) === today
  )

  if (challenge.challenge_status === 'COMPLETED') {
    return (
      <div className="fixed bottom-20 left-0 w-full px-4 z-40 pointer-events-none">
        <div className="max-w-3xl mx-auto bg-green-50 border border-green-200 rounded-2xl px-4 py-3 flex items-center justify-between shadow-lg">
          <div className="min-w-0">
            <p className="text-[10px] font-bold text-green-400 uppercase tracking-wide">챌린지 완료</p>
            <p className="text-sm font-bold text-green-700 truncate">{challenge.title}</p>
          </div>
          <span className="bg-green-500 text-accent-ink text-xs font-bold px-3 py-1.5 rounded-full shrink-0 ml-3">완료</span>
        </div>
      </div>
    )
  }

  return (
    <div className="fixed bottom-20 left-0 w-full px-4 z-40">
      <div className="max-w-3xl mx-auto bg-surface border border-line rounded-2xl px-4 py-3 flex items-center justify-between shadow-lg">
        <div className="min-w-0 flex-1">
          <p className="text-[10px] font-bold text-muted uppercase tracking-wide">이 가이드 관련 챌린지</p>
          <p className="text-sm font-bold text-ink truncate">{challenge.title}</p>
          {challenge.target_days && (
            <p className="text-xs text-muted">
              {challenge.completed_dates?.length || 0}/{challenge.target_days}일
            </p>
          )}
        </div>

        {isViewingHistory ? (
          <span className="text-xs text-muted shrink-0 ml-3">과거 가이드</span>
        ) : !challenge.is_active ? (
          <button
            onClick={() => requestStart(challenge)}
            disabled={isProcessing}
            className={`ml-3 px-4 py-2 rounded-xl text-xs font-bold shrink-0 transition-colors cursor-pointer ${
              isProcessing ? 'bg-surface-2 text-muted cursor-wait' : 'bg-accent text-accent-ink hover:brightness-110 active:scale-95'
            }`}
          >
            {isProcessing && startTarget?.id === challenge.id ? '처리중...' : '시작하기'}
          </button>
        ) : checkedToday ? (
          <div className="flex items-center gap-2 ml-3 shrink-0">
            <span className="bg-green-50 text-green-500 text-xs font-bold px-3 py-2 rounded-xl">
              오늘 완료!
            </span>
            <button
              onClick={() => router.push('/challenge')}
              className="text-xs font-bold text-muted hover:text-ink px-2 py-2 rounded-xl hover:bg-surface-2 transition-colors cursor-pointer"
              title="챌린지 페이지에서 보기"
            >
              →
            </button>
          </div>
        ) : (
          <button
            onClick={() => checkToday(challenge)}
            disabled={isProcessing}
            className={`ml-3 px-3 py-2 rounded-xl text-xs font-bold shrink-0 transition-colors cursor-pointer ${
              isProcessing ? 'bg-surface-2 text-muted cursor-wait' : 'bg-blue-500 text-accent-ink hover:bg-blue-600'
            }`}
          >
            {isProcessing ? '처리중...' : '오늘 완료 체크'}
          </button>
        )}
      </div>
    </div>
  )
}

// ── 메인 페이지 ────────────────────────────────────────────────────────────────
// 유효한 탭 키 (TABS 의 key 와 일치). 메인 → ?tab=symptom 진입 시 활용.
const VALID_TAB_KEYS = ['interaction', 'sleep', 'diet', 'exercise', 'symptom']

function LifestyleGuideContent() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const confirm = useConfirm()
  const { selectedProfileId: profileId } = useProfile()
  const {
    guides,
    latestGuide,
    isLoading: guidesLoading,
    generateGuide,
    deleteGuide,
  } = useLifestyleGuide()
  const { challengesByGuide } = useChallenge()
  const { groups: prescriptionGroups, isLoading: groupsLoading } = usePrescriptionGroup()
  const { startTarget, isStarting, requestStart, cancelStart, confirmStart } = useChallengeStart()
  const { checkingId, checkToday } = useChallengeCheck()

  const [isGenerating, setIsGenerating] = useState(false)
  const [isPickerOpen, setIsPickerOpen] = useState(false)
  const [selectedGuide, setSelectedGuide] = useState(null)
  const [userPickedGuideId, setUserPickedGuideId] = useState(null)
  // 챌린지 페이지네이션 (5개씩 1/3, 2/3, 3/3). 가이드 변경 시 첫 페이지로 reset.
  const [challengePage, setChallengePage] = useState(0)
  // 메인 페이지의 '오늘의 증상 → 기록하기' 같은 deep link 가 ?tab=<key> 로
  // 진입 탭을 지정할 수 있게 한다 (예: /lifestyle-guide?tab=symptom).
  const initialTabFromQuery = searchParams.get('tab')
  const [activeTab, setActiveTab] = useState(
    VALID_TAB_KEYS.includes(initialTabFromQuery) ? initialTabFromQuery : 'interaction'
  )

  // ── 오늘의 증상 상태 ──
  const [todaySymptoms, setTodaySymptoms] = useState([])
  const [todayNote, setTodayNote] = useState('')
  const [symptomsLoading, setSymptomsLoading] = useState(false)

  const chipScrollRef = useRef(null)
  const isLoading = guidesLoading

  // ── 오늘의 증상 fetch ──
  // GET /api/v1/daily-logs?profile_id=...&days=1
  // 응답: list[DailySymptomLogResponse]
  // 필드: { id, profile_id, log_date, symptoms: string[], note: string|null, created_at }
  // 후속 정정: 다른 페이지/컴포넌트와 동일하게 axios 기반 `api` client 사용 (auth
  // 헤더 자동 주입 + 일관된 에러 처리). 직접 fetch 제거.
  const fetchTodaySymptoms = async () => {
    if (!profileId) return
    const today = new Date().toISOString().split('T')[0]
    setSymptomsLoading(true)
    try {
      const res = await api.get('/api/v1/daily-logs', {
        params: { profile_id: profileId, days: 1 },
      })
      const data = res.data || [] // list[DailySymptomLogResponse]
      // days=1 이지만 혹시 어제 것도 포함될 수 있으니 오늘 날짜로 한 번 더 필터
      const todayLog = data.find((log) => log.log_date === today)
      setTodaySymptoms(todayLog?.symptoms ?? [])
      setTodayNote(todayLog?.note ?? '')
    } catch {
      // 조용히 실패 — 카드 빈 상태로 표시
    } finally {
      setSymptomsLoading(false)
    }
  }

  // 페이지 마운트 시 조회
  useEffect(() => {
    fetchTodaySymptoms()
  }, [profileId])

  // 증상 탭 진입 시 재조회
  useEffect(() => {
    if (activeTab === 'symptom') {
      fetchTodaySymptoms()
    }
  }, [activeTab])

  // 가이드가 바뀌면 챌린지 페이지를 1쪽으로 리셋 (사용자가 칩으로 다른 가이드 선택 등)
  useEffect(() => {
    setChallengePage(0)
  }, [selectedGuide?.id])

  // ── guideChallenges ──
  const guideChallenges = (selectedGuide ? challengesByGuide(selectedGuide.id) : [])
    .slice()
    .sort((a, b) => {
      const da = a.target_days || 0
      const db = b.target_days || 0
      if (da !== db) return da - db
      const ta = a.title || ''
      const tb = b.title || ''
      const cmp = ta.localeCompare(tb, 'ko')
      if (cmp !== 0) return cmp
      return a.id < b.id ? -1 : a.id > b.id ? 1 : 0
    })
  const isLoadingChallenges = false

  const firstReadyGuide = guides.find(g => g.status === 'ready') || null
  const isViewingHistory =
    !!selectedGuide && !!firstReadyGuide && selectedGuide.id !== firstReadyGuide.id

  // ── selectedGuide 자동 보정 ──
  useEffect(() => {
    if (userPickedGuideId) {
      const picked = guides.find(g => g.id === userPickedGuideId && g.status === 'ready')
      if (picked) {
        if (picked !== selectedGuide) setSelectedGuide(picked)
        return
      }
      setUserPickedGuideId(null)
      return
    }

    if (latestGuide && latestGuide.status === 'ready') {
      if (selectedGuide?.id !== latestGuide.id || selectedGuide !== latestGuide) {
        setSelectedGuide(latestGuide)
      }
      return
    }

    if (guides.length > 0) {
      const firstReady = guides.find(g => g.status === 'ready')
      setSelectedGuide(firstReady || null)
    } else {
      setSelectedGuide(null)
    }
  }, [latestGuide, guides, selectedGuide, userPickedGuideId])

  const eligibleGroups = (prescriptionGroups || []).filter((g) => g.has_active_medication)
  const hasEligibleGroup = eligibleGroups.length > 0

  // ── 새 가이드 버튼 클릭 ──
  const handleClickNewGuide = () => {
    if (!profileId) {
      showError('프로필을 먼저 선택해주세요.')
      return
    }
    if (isGenerating) return
    if (groupsLoading) return
    if (!hasEligibleGroup) {
      showError('처방전이 등록되어야 맞춤 가이드 생성이 가능합니다.')
      router.push('/ocr')
      return
    }
    setIsPickerOpen(true)
  }

  // ── 가이드 생성 ──
  const handleConfirmPickGroup = async (prescriptionGroupId) => {
    setIsPickerOpen(false)
    if (isGenerating) return
    setIsGenerating(true)
    setUserPickedGuideId(null)
    const abortController = new AbortController()
    try {
      const result = await generateGuide(profileId, prescriptionGroupId, abortController.signal)
      if (!result) return
      if (result.deduped) {
        toast.success('동일 처방전 + 건강정보 가이드가 이미 있어 그대로 보여드려요.')
      } else {
        toast.success('새 가이드가 생성되었습니다!')
      }
    } catch (err) {
      const detail = err.response?.data?.detail
      if (err.response?.status === 409 && detail?.code === 'NO_ACTIVE_MEDICATIONS') {
        showError(detail.message || '이 처방전엔 복용 중인 약이 없어 가이드를 만들 수 없어요.')
        router.push(detail.redirect_to || '/medication')
        return
      }
      showError(
        err.parsed?.message ||
          err.message ||
          '가이드 생성에 실패했습니다. 잠시 후 다시 시도해주세요.',
      )
    } finally {
      abortController.abort()
      setIsGenerating(false)
    }
  }

  // ── 가이드 삭제 ──
  const handleDeleteGuide = async (guide) => {
    const ok = await confirm({
      title: '가이드 삭제',
      message: `${formatFullDateTime(guide.created_at)} 에 만들어진 가이드를 삭제하시겠습니까?`,
      confirmLabel: '삭제',
      danger: true,
    })
    if (!ok) return
    try {
      if (userPickedGuideId === guide.id) setUserPickedGuideId(null)
      await deleteGuide(guide.id)
      toast.success('가이드가 삭제되었습니다.')
    } catch {
      showError('가이드 삭제에 실패했습니다.')
    }
  }

  // ── 챌린지 시작 ──
  const handleConfirmStart = async (difficulty, targetDays) => {
    try {
      const updated = await confirmStart(difficulty, targetDays)
      if (!updated) return
      toast(
        (t) => (
          <div className="flex items-center gap-3">
            <span className="text-sm">챌린지가 시작되었습니다!</span>
            <button
              onClick={() => { toast.dismiss(t.id); router.push('/challenge') }}
              className="text-blue-500 font-bold text-sm shrink-0 cursor-pointer"
            >
              보러가기
            </button>
          </div>
        ),
        { duration: 4000 }
      )
    } catch {
      showError('챌린지 시작에 실패했습니다.')
    }
  }

  // ── 로딩 스켈레톤 ──
  if (isLoading) {
    return (
      <main className="min-h-screen bg-surface-2 pb-24">
        <Header title="생활습관 가이드" subtitle="맞춤형 건강 가이드" showBack={false} />
        <div className="max-w-3xl mx-auto px-4 py-6 space-y-4 animate-pulse">
          <div className="h-10 bg-surface rounded-xl w-full" />
          <div className="flex gap-2 overflow-hidden">
            {[1, 2, 3].map((i) => <div key={i} className="h-8 bg-surface rounded-full w-16 shrink-0" />)}
          </div>
          {[1, 2, 3].map((i) => <div key={i} className="h-24 bg-surface rounded-2xl w-full" />)}
        </div>
        <BottomNav />
      </main>
    )
  }

  const currentTab = TABS.find((t) => t.key === activeTab)

  return (
    <main className="min-h-screen bg-surface-2 pb-40">
      <Header title="생활습관 가이드" subtitle="맞춤형 건강 가이드" showBack={false} />

      <div className="max-w-3xl mx-auto px-4 py-4 space-y-4">

        {/* ── 새 가이드 버튼 ── */}
        <div className="flex items-center justify-between">
          <p className="text-xs text-muted">
            {isGenerating ? '🤖 AI가 분석 중입니다...' : ''}
          </p>
          <button
            onClick={handleClickNewGuide}
            disabled={isGenerating || !profileId}
            className={`px-4 py-2 rounded-xl text-xs font-bold border transition-all ${
              isGenerating || !profileId
                ? 'bg-surface-2 text-muted border-line cursor-wait'
                : 'bg-surface text-ink border-line hover:bg-surface-2 cursor-pointer'
            }`}
          >
            {isGenerating ? '생성 중...' : '+ 새 가이드'}
          </button>
        </div>

        {/* ── 가이드 없음 ── */}
        {guides.length === 0 && !isGenerating && (
          <>
            <EmptyState
              title="아직 생활습관 가이드가 없어요"
              message={
                hasEligibleGroup
                  ? '위 버튼을 눌러 AI 맞춤 가이드를 받아보세요'
                  : '처방전을 먼저 등록하면 맞춤 가이드를 받을 수 있어요'
              }
            />
            {!hasEligibleGroup && !groupsLoading && (
              <button
                onClick={() => router.push('/ocr')}
                className="mx-auto block px-5 py-2.5 rounded-xl text-sm font-bold bg-accent text-accent-ink hover:brightness-110 cursor-pointer"
              >
                처방전 등록하러 가기
              </button>
            )}
          </>
        )}

        {/* ── 첫 가이드 생성 중 스켈레톤 ── */}
        {isGenerating && guides.filter(g => g.status === 'ready').length === 0 && (
          <div className="animate-pulse space-y-4">
            <div className="flex gap-2">
              <div className="h-7 bg-surface-2 rounded-full w-20" />
            </div>
            <div className="bg-surface rounded-2xl px-4 py-3 shadow-sm border border-line">
              <div className="h-3 bg-surface-2 rounded w-32 mb-3" />
              <div className="flex flex-wrap gap-1.5">
                {[1, 2, 3].map((i) => <div key={i} className="h-6 bg-surface-2 rounded-full w-16" />)}
              </div>
            </div>
            <div className="flex gap-1 overflow-hidden">
              {[1, 2, 3, 4, 5].map((i) => <div key={i} className="h-9 bg-surface-2 rounded-xl w-20 shrink-0" />)}
            </div>
            <div className="bg-surface rounded-2xl shadow-sm border border-line p-5">
              <div className="flex items-center gap-2 mb-4">
                <div className="h-6 w-6 bg-surface-2 rounded" />
                <div className="h-5 bg-surface-2 rounded w-28" />
              </div>
              <div className="space-y-2.5">
                {['w-full', 'w-11/12', 'w-4/5', 'w-full', 'w-3/4', 'w-5/6'].map((w, i) => (
                  <div key={i} className={`h-4 bg-surface-2 rounded ${w}`} />
                ))}
              </div>
            </div>
          </div>
        )}

        {/* ── 기존 가이드 있고 신규 생성 중 — inline 알림 ── */}
        {isGenerating && guides.filter(g => g.status === 'ready').length > 0 && (
          <div className="bg-blue-50 border border-blue-200 rounded-xl px-4 py-3 flex items-center gap-3">
            <div className="h-4 w-4 rounded-full border-2 border-blue-300 border-t-blue-600 animate-spin shrink-0" />
            <div className="min-w-0">
              <p className="text-xs font-bold text-blue-700">새 가이드 생성 중</p>
              <p className="text-[11px] text-blue-500 mt-0.5">
                완료되면 자동으로 새 칩으로 추가됩니다. 기존 가이드는 계속 열람 가능.
              </p>
            </div>
          </div>
        )}

        {/* ── 이력 날짜 칩 ── */}
        {guides.length > 0 && (
          <div ref={chipScrollRef} className="flex gap-2 overflow-x-auto pb-1 scrollbar-hide">
            {guides.map((guide) => {
              const isSelected = selectedGuide?.id === guide.id
              return (
                <div
                  key={guide.id}
                  className={`shrink-0 flex items-center gap-1 px-3 py-1.5 rounded-full text-xs font-bold border transition-all ${
                    isSelected
                      ? 'bg-accent text-accent-ink border-accent'
                      : 'bg-surface text-muted border-line hover:border-line'
                  }`}
                >
                  <button
                    onClick={() => guide.status === 'ready' && setUserPickedGuideId(guide.id)}
                    disabled={guide.status !== 'ready'}
                    className={guide.status === 'ready' ? 'cursor-pointer' : 'cursor-wait'}
                  >
                    {guide.status !== 'ready'
                      ? '생성중...'
                      : firstReadyGuide?.id === guide.id
                        ? `${formatDate(guide.created_at)} 최신`
                        : formatDate(guide.created_at)}
                  </button>
                  <button
                    onClick={(e) => { e.stopPropagation(); handleDeleteGuide(guide) }}
                    className={`ml-0.5 leading-none cursor-pointer transition-colors ${
                      isSelected ? 'text-muted hover:text-accent-ink' : 'text-muted hover:text-red-400'
                    }`}
                    title="가이드 삭제"
                  >
                    ×
                  </button>
                </div>
              )
            })}
          </div>
        )}

        {/* ── 과거 가이드 열람 배너 ── */}
        {isViewingHistory && (() => {
          const prescribed = summarizePrescribedRange(selectedGuide.medication_snapshot)
          return (
            <div className="bg-amber-50 border border-amber-200 rounded-xl px-4 py-3 space-y-1">
              <div className="flex items-center gap-2">
                <span className="text-amber-500 text-sm">⚠️</span>
                <p className="text-xs text-amber-800 font-bold">
                  {formatFullDateTime(selectedGuide.created_at)} 에 만들어진 가이드예요
                </p>
              </div>
              <p className="text-[11px] text-amber-700 leading-relaxed pl-5">
                {prescribed && <>처방일 {prescribed} 기준으로 작성됐어요. </>}
                이후 처방이나 설문조사가 바뀌었다면 새 가이드를 만들어 주세요.
              </p>
            </div>
          )
        })()}

        {/* ── 가이드 내용 ── */}
        {selectedGuide && (
          <>
            {/* 복용 약 스냅샷 */}
            {selectedGuide.medication_snapshot?.length > 0 && (
              <div className="bg-surface rounded-2xl px-4 py-3 shadow-sm border border-line">
                <p className="text-xs font-bold text-muted mb-2">💊 가이드 생성 시 복용 약</p>
                <div className="flex flex-wrap gap-1.5">
                  {selectedGuide.medication_snapshot.map((med, i) => {
                    const name =
                      typeof med === 'string'
                        ? med
                        : med.medicine_name || med.name || JSON.stringify(med)
                    const dispensed =
                      typeof med === 'object' ? med.dispensed_date || med.start_date : null
                    return (
                      <span
                        key={i}
                        className="bg-surface-2 text-muted text-xs px-2.5 py-1 rounded-full font-bold inline-flex items-center gap-1.5"
                      >
                        {name}
                        {dispensed && (
                          <span className="text-[10px] font-normal text-muted">
                            처방 {dispensed.slice(5, 10).replace('-', '/')}
                          </span>
                        )}
                      </span>
                    )
                  })}
                </div>
              </div>
            )}

            {/* 5개 탭 네비게이션 */}
            <div className="overflow-x-auto scrollbar-hide">
              <div className="flex gap-1 min-w-max pb-1">
                {TABS.map((tab) => (
                  <button
                    key={tab.key}
                    onClick={() => setActiveTab(tab.key)}
                    className={`px-3 py-2 rounded-xl text-xs font-bold transition-all cursor-pointer whitespace-nowrap ${
                      activeTab === tab.key
                        ? `${tab.bg} ${tab.color}`
                        : 'bg-surface text-muted hover:text-muted'
                    }`}
                  >
                    {tab.icon} {tab.label}
                  </button>
                ))}
              </div>
            </div>

            {/* 탭 콘텐츠 */}
            <div className={`bg-surface rounded-2xl shadow-sm border ${currentTab?.border || 'border-line'} p-5`}>
              <div className="flex items-center gap-2 mb-3">
                <span className="text-xl">{currentTab?.icon}</span>
                <h2 className={`font-black text-base ${currentTab?.color}`}>{currentTab?.label}</h2>
              </div>

              {selectedGuide.content?.[activeTab] ? (
                <p className="text-sm text-ink leading-relaxed whitespace-pre-line">
                  {selectedGuide.content[activeTab]}
                </p>
              ) : (
                <p className="text-sm text-muted">이 카테고리의 가이드 내용이 없습니다.</p>
              )}

              {/* ── 증상 탭: 오늘의 증상 요약 카드 + 입력 폼 ── */}
              {activeTab === 'symptom' && (
                <div className="mt-5 space-y-4">

                  {/* 오늘의 증상 요약 카드 */}
                  {/* data-testid: 아래 입력 폼의 프리셋 칩과 같은 텍스트가 나오므로,
                      테스트가 "조회된 기록"만 골라 단언할 수 있게 경계를 노출한다. */}
                  <div
                    data-testid="today-symptom-summary"
                    className="bg-orange-50/40 border border-orange-100 rounded-2xl p-4"
                  >
                    <div className="flex items-center gap-2 mb-3">
                      <div className="w-7 h-7 bg-orange-50 rounded-lg flex items-center justify-center text-orange-500">
                        <Stethoscope size={14} />
                      </div>
                      <p className="text-xs font-black text-orange-700">오늘의 증상 요약</p>
                    </div>

                    {symptomsLoading ? (
                      <div className="animate-pulse flex gap-2">
                        <div className="h-7 bg-orange-100 rounded-full w-16" />
                        <div className="h-7 bg-orange-100 rounded-full w-20" />
                      </div>
                    ) : todaySymptoms.length > 0 || todayNote ? (
                      <div className="space-y-3">
                        {todaySymptoms.length > 0 && (
                          <div className="flex flex-wrap gap-1.5">
                            {todaySymptoms.map((s, idx) => (
                              <span
                                key={idx}
                                className="px-3 py-1.5 bg-surface text-orange-700 rounded-full text-xs font-bold border border-orange-100"
                              >
                                {s}
                              </span>
                            ))}
                          </div>
                        )}
                        {todayNote && (
                          <p className="text-muted text-xs leading-relaxed bg-surface/70 p-3 rounded-xl border border-dashed border-orange-100">
                            &quot;{todayNote}&quot;
                          </p>
                        )}
                      </div>
                    ) : (
                      <p className="text-xs text-orange-400">
                        아직 오늘 기록된 증상이 없어요. 아래에서 입력해보세요.
                      </p>
                    )}
                  </div>

                  {/* 증상 입력 폼 — 저장 후 요약 카드 자동 갱신.
                      지난 가이드를 보고 있을 땐 폼을 숨기고 안내 배너 표시.
                      증상 로그는 (profile_id, log_date) 단위라 가이드 무관 = 같은
                      날 1건만. 지난 가이드에서 새 입력을 받으면 사용자 혼란 +
                      upsert 로 기존 기록을 덮어쓸 수 있어 의도와 다를 수 있음. */}
                  {isViewingHistory ? (
                    <div className="bg-surface-2 border border-line rounded-2xl p-4 flex items-center justify-between gap-3">
                      <div className="text-xs text-muted leading-relaxed">
                        <p className="font-bold text-ink mb-1">지난 가이드를 보고 계셔요</p>
                        <p>오늘의 증상은 한 곳에서만 기록할 수 있어요. 최근 가이드에서 입력해주세요.</p>
                      </div>
                      <button
                        type="button"
                        onClick={() => {
                          if (firstReadyGuide) {
                            setUserPickedGuideId(null)
                            setSelectedGuide(firstReadyGuide)
                          }
                        }}
                        className="shrink-0 px-3 py-2 text-xs font-bold rounded-xl bg-orange-500 text-accent-ink hover:bg-orange-600 cursor-pointer"
                      >
                        최근 가이드로
                      </button>
                    </div>
                  ) : (
                    <SymptomLogForm
                      profileId={profileId}
                      initialSymptoms={todaySymptoms}
                      initialNote={todayNote}
                      onSaved={() => fetchTodaySymptoms()}
                    />
                  )}
                </div>
              )}
            </div>

            {/* ── 챌린지 목록 (5개씩 페이지네이션) ── */}
            {guideChallenges.length > 0 && (() => {
              const totalPages = Math.max(1, Math.ceil(guideChallenges.length / CHALLENGES_PER_PAGE))
              const safePage = Math.min(challengePage, totalPages - 1)
              const pageStart = safePage * CHALLENGES_PER_PAGE
              const pageItems = guideChallenges.slice(pageStart, pageStart + CHALLENGES_PER_PAGE)
              const isFirstPage = safePage === 0
              const isLastPage = safePage >= totalPages - 1
              return (
                <div className="bg-surface rounded-2xl shadow-sm border border-line p-4">
                  <div className="flex items-center justify-between mb-3 gap-2">
                    <div className="min-w-0">
                      <p className="text-xs font-bold text-muted">🎯 이 가이드에서 생성된 챌린지</p>
                      <p className="text-[11px] text-muted mt-0.5 break-keep">
                        총 {guideChallenges.length}개의 추천 챌린지를 페이지로 넘겨가며 둘러볼 수 있어요.
                      </p>
                    </div>
                  </div>

                  <div className="space-y-2">
                    {isLoadingChallenges ? (
                      <div className="animate-pulse space-y-2">
                        {[1, 2].map((i) => <div key={i} className="h-10 bg-surface-2 rounded-xl" />)}
                      </div>
                    ) : (
                      pageItems.map((c) => {
                        const tabMeta = TABS.find((t) => t.key === c.category)
                        const diffStyle = c.difficulty ? (DIFFICULTY_STYLE[c.difficulty] || DIFFICULTY_STYLE['보통']) : null
                        const today = new Date().toISOString().split('T')[0]
                        const checkedToday = c.completed_dates?.some(
                          (d) => (typeof d === 'string' ? d : d.toISOString?.().split('T')[0]) === today
                        )
                        const isProcessing =
                          (isStarting && startTarget?.id === c.id) || checkingId === c.id

                        return (
                          <div
                            key={c.id}
                            className="flex items-center justify-between gap-3 py-2 px-3 bg-surface-2 rounded-xl"
                          >
                            <div className="flex items-center gap-2 min-w-0">
                              {tabMeta && (
                                <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${tabMeta.bg} ${tabMeta.color}`}>
                                  {tabMeta.icon}
                                </span>
                              )}
                              <span className="text-sm font-bold text-ink truncate">{c.title}</span>
                              {diffStyle && (
                                <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded-full shrink-0 ${diffStyle.bg} ${diffStyle.text}`}>
                                  {c.difficulty}
                                </span>
                              )}
                            </div>

                            <div className="shrink-0">
                              {c.challenge_status === 'COMPLETED' ? (
                                <span className="bg-green-50 text-green-500 text-[10px] font-bold px-2 py-1 rounded-full">완료</span>
                              ) : !c.is_active ? (
                                <button
                                  onClick={() => requestStart(c)}
                                  disabled={isViewingHistory || isProcessing}
                                  className={`text-[10px] font-bold px-3 py-1.5 rounded-full transition-colors ${
                                    isViewingHistory
                                      ? 'bg-surface-2 text-muted cursor-default'
                                      : isProcessing
                                        ? 'bg-surface-2 text-muted cursor-wait'
                                        : 'bg-accent text-accent-ink hover:brightness-110 cursor-pointer'
                                  }`}
                                >
                                  {isProcessing ? '...' : '시작하기'}
                                </button>
                              ) : checkedToday ? (
                                <span className="bg-green-50 text-green-500 text-[10px] font-bold px-2 py-1 rounded-full">오늘 완료</span>
                              ) : (
                                <button
                                  onClick={() => checkToday(c)}
                                  disabled={isViewingHistory || isProcessing}
                                  className={`text-[10px] font-bold px-3 py-1.5 rounded-full transition-colors ${
                                    isViewingHistory
                                      ? 'bg-surface-2 text-muted cursor-default'
                                      : isProcessing
                                        ? 'bg-surface-2 text-muted cursor-wait'
                                        : 'bg-accent text-accent-ink hover:brightness-110 active:scale-95 cursor-pointer'
                                  }`}
                                >
                                  {isProcessing ? '...' : '오늘 체크'}
                                </button>
                              )}
                            </div>
                          </div>
                        )
                      })
                    )}
                  </div>

                  {/* ── 페이지네이션 컨트롤 ── */}
                  {totalPages > 1 && (
                    <div className="mt-4 flex items-center justify-center gap-3">
                      <button
                        type="button"
                        onClick={() => setChallengePage((p) => Math.max(0, p - 1))}
                        disabled={isFirstPage}
                        aria-label="이전 페이지"
                        className={`w-8 h-8 flex items-center justify-center rounded-full border transition-colors ${
                          isFirstPage
                            ? 'bg-surface-2 text-muted border-line cursor-not-allowed'
                            : 'bg-surface text-ink border-line hover:bg-surface-2 cursor-pointer'
                        }`}
                      >
                        <ChevronLeft size={16} />
                      </button>
                      <span className="text-xs font-bold text-muted tabular-nums">
                        {safePage + 1} / {totalPages}
                      </span>
                      <button
                        type="button"
                        onClick={() => setChallengePage((p) => Math.min(totalPages - 1, p + 1))}
                        disabled={isLastPage}
                        aria-label="다음 페이지"
                        className={`w-8 h-8 flex items-center justify-center rounded-full border transition-colors ${
                          isLastPage
                            ? 'bg-surface-2 text-muted border-line cursor-not-allowed'
                            : 'bg-surface text-ink border-line hover:bg-surface-2 cursor-pointer'
                        }`}
                      >
                        <ChevronRight size={16} />
                      </button>
                    </div>
                  )}
                </div>
              )
            })()}
          </>
        )}
      </div>

      <BottomNav />

      {/* ── 챌린지 시작 모달 ── */}
      {startTarget && (
        <StartChallengeModal
          challenge={startTarget}
          onConfirm={handleConfirmStart}
          onClose={cancelStart}
          isLoading={isStarting}
        />
      )}

      {/* ── 처방전 선택 모달 ── */}
      {isPickerOpen && (
        <PrescriptionPickerModal
          onConfirm={handleConfirmPickGroup}
          onClose={() => setIsPickerOpen(false)}
          isLoading={isGenerating}
        />
      )}
    </main>
  )
}

export default function LifestyleGuidePage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-surface-2" />}>
      <LifestyleGuideContent />
    </Suspense>
  )
}
