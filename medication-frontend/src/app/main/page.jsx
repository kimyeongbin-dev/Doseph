'use client'
import { useState, useEffect, useRef, Suspense, useCallback } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import api from '@/lib/api'
import { Flame, Plus, MessageCircle, FileText, Loader2, X, Trash2, Activity } from 'lucide-react'
import ChatModal from '@/components/chat/ChatModal'
import HealthSurveyModal from '@/components/common/HealthSurveyModal'
import { useProfile } from '@/contexts/ProfileContext'
import toast from 'react-hot-toast'
import { showError } from '@/lib/api'
import { useMedication } from '@/contexts/MedicationContext'
import { useChallenge } from '@/contexts/ChallengeContext'
import { useOcrDraft, useOcrEntryNavigator } from '@/contexts/OcrDraftContext'
import TodaySchedule from '@/components/medication/TodaySchedule'
import ErrorState from '@/components/common/ErrorState'
import Button from '@/components/ui/Button'
import Card from '@/components/ui/Card'
import SectionHeader from '@/components/ui/SectionHeader'

// ── 히어로 배경 이미지 슬라이드쇼 ────────────────────────────────────────────
// 흐름: 3초 타이머 → 다음 이미지 인덱스로 순환 → CSS transition으로 페이드
const HERO_BG_IMAGES = [
  '/hero_bg_1.png',
  '/hero_bg_2.png',
  '/hero_bg_3.png',
]

// 활성 OCR draft 카드 — main 우측하단 floating (챗봇 아이콘 위)
// 사용자가 X 로 카드 전체를 숨길 수 있고 (새로고침 시 다시 표시),
// 각 항목 좌측의 휴지통으로 개별 draft 를 폐기할 수도 있다.
function ActiveDraftsCard({ drafts, onSelect, onDelete }) {
  const [dismissed, setDismissed] = useState(false)
  if (!drafts || drafts.length === 0 || dismissed) return null

  const formatTime = (iso) => {
    const d = new Date(iso)
    return d.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' })
  }
  const STATUS_LABEL = {
    pending: '처리 중',
    ready: '확인 대기',
    no_text: '텍스트 없음',
    no_candidates: '인식 실패',
    failed: '오류',
  }

  return (
    <div className="fixed right-6 bottom-44 z-40 w-72 bg-surface rounded-2xl border border-line shadow-[var(--shadow-pop)] p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <FileText size={16} className="text-muted" />
          <p className="font-bold text-sm text-ink">처방전 ({drafts.length}건)</p>
        </div>
        <button
          onClick={() => setDismissed(true)}
          className="text-muted hover:text-ink cursor-pointer"
          aria-label="카드 숨기기"
        >
          <X size={16} />
        </button>
      </div>
      <ul className="space-y-1 max-h-56 overflow-y-auto">
        {drafts.map((d) => (
          <li key={d.draft_id} className="flex items-center gap-1">
            <button
              onClick={() => onDelete(d.draft_id)}
              className="text-muted hover:text-critical cursor-pointer flex-shrink-0 p-2 rounded-lg hover:bg-critical/10 transition-colors"
              aria-label="처방전 폐기"
            >
              <Trash2 size={14} />
            </button>
            <button
              onClick={() => onSelect(d.draft_id)}
              className="flex-1 flex items-center justify-between gap-3 px-3 py-2 rounded-xl hover:bg-surface-2 cursor-pointer transition-colors text-left"
            >
              <div className="flex items-center gap-2 min-w-0">
                {d.status === 'pending' ? (
                  <Loader2 size={14} className="text-accent animate-spin flex-shrink-0" />
                ) : (
                  <span className="w-2 h-2 rounded-full bg-success flex-shrink-0" />
                )}
                <span className="text-sm font-bold text-ink truncate">
                  {formatTime(d.created_at)} 업로드
                </span>
              </div>
              <span className="text-xs text-muted flex-shrink-0">
                {STATUS_LABEL[d.status] || d.status}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}

// 스켈레톤은 main의 레이아웃을 따름
function MainSkeleton() {
  return (
    <>
      <div className="w-full min-h-[540px] bg-ink animate-pulse" />
      <main className="max-w-7xl mx-auto w-full px-6 py-14 animate-pulse">
        <div className="grid md:grid-cols-12 gap-6">
          <div className="md:col-span-8 bg-surface-2 rounded-card h-[420px]" />
          <div className="md:col-span-4 space-y-6">
            <div className="bg-surface-2 rounded-card h-52" />
            <div className="bg-surface-2 rounded-card h-52" />
          </div>
        </div>
      </main>
    </>
  )
}

// ── 복약 잔여 일수 계산 ────────────────────────────────────────────────────────
// 흐름: end_date 우선 → 없으면 start_date + total_intake_days 로 추정
function getRemainingDays(med) {
  const today = new Date()
  today.setHours(0, 0, 0, 0)

  if (med.end_date) {
    const end = new Date(med.end_date)
    end.setHours(0, 0, 0, 0)
    const diff = Math.ceil((end - today) / (1000 * 60 * 60 * 24))
    if (diff > 0) return `${diff}일 남음`
    if (diff === 0) return '오늘 종료'
    return null
  }

  if (med.total_intake_days && med.start_date) {
    const start = new Date(med.start_date)
    start.setHours(0, 0, 0, 0)
    const elapsed = Math.ceil((today - start) / (1000 * 60 * 60 * 24))
    const remaining = med.total_intake_days - elapsed
    if (remaining > 0) return `${remaining}일 남음`
    return null
  }

  return null
}

// ── 메인 페이지 컴포넌트 (Suspense 적용) ──────────────────────────────────────────
export default function MainPage() {
  return (
    <Suspense fallback={<MainSkeleton />}>
      <MainPageContent />
    </Suspense>
  )
}

function MainPageContent() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const [isLoading, setIsLoading] = useState(true)
  // 설문 모달의 최초 표시 여부는 진입 URL 이 결정한다(effect 로 뒤늦게 켜지 않는다).
  // 진입 경로는 카카오 콜백의 router.replace('/main?showSurvey=true') 뿐이며,
  // 이때 main 은 새로 마운트되므로 초깃값으로 충분하다.
  const [showSurvey, setShowSurvey] = useState(() => searchParams.get('showSurvey') === 'true')
  const [showChat, setShowChat] = useState(false)
  // 챌린지 랜덤 선택용 시드 — 마운트당 1회만 뽑아 렌더 중 파생을 순수하게 유지한다.
  const [challengePickSeed] = useState(() => Math.random())
  const [greeting, setGreeting] = useState({ msg: '반가워요', sub: '오늘 하루도 건강하게 시작해봐요' })

  // [추가] 오늘의 증상 관련 상태 관리
  const [todaySymptoms, setTodaySymptoms] = useState([])
  const [todayNote, setTodayNote] = useState('')

  const { profiles, selectedProfileId, selectedProfile, createProfile, updateProfile } = useProfile()
  const [isSurveySubmitting, setIsSurveySubmitting] = useState(false)
  // 4 Context 가 모든 server state 를 단일 진실로 관리 — 자체 fetch 0
  const {
    activeMedications: medications,
    isError: medicationsError,
    error: medicationsErrorObject,
    isRefetching: medicationsRefetching,
    refetchMedications,
  } = useMedication()
  const { activeChallenges } = useChallenge()
  const { activeDrafts, removeDraftLocally, refetchDrafts } = useOcrDraft()
  const goToOcrFlow = useOcrEntryNavigator()
  const userName = selectedProfile?.name?.split('(')[0] || '사용자'
  const isInitialLoad = useRef(true)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [currentBgIndex, setCurrentBgIndex] = useState(0)
  const bgTimerRef = useRef(null)

  // ── 히어로 배경 이미지 슬라이드쇼 ──────────────────────────────────────────
  // 흐름: mount → 3초 타이머 → 인덱스 순환 → 이전 타이머 클린업
  useEffect(() => {
    bgTimerRef.current = setTimeout(() => {
      setCurrentBgIndex((prev) => (prev + 1) % HERO_BG_IMAGES.length)
    }, 3000)
    return () => clearTimeout(bgTimerRef.current)
  }, [currentBgIndex])

  // ── 설문 진입 쿼리 정리 ────────────────────────────────────────────
  // 흐름: ?showSurvey=true 로 진입 -> (모달은 이미 초깃값으로 열림) -> URL 에서 쿼리 제거
  // 뒤로가기로 다시 설문이 뜨는 오염을 막기 위한 것. 상태가 아니라 URL(외부 시스템)만 건드린다.
  useEffect(() => {
    if (searchParams.get('showSurvey') === 'true') {
      router.replace('/main', { scroll: false })
    }
  }, [searchParams, router])

  // Context 들이 자동으로 server state 를 관리 — 페이지는 derived state 만 갱신.
  // [수정] 증상 데이터 fetch 로직 통합
  useEffect(() => {
    if (!selectedProfileId) return

    const fetchData = async () => {
      isInitialLoad.current = false
      setIsLoading(false)

      // 인사말 설정 로직
      const hour = new Date().getHours()
      if (hour < 12) setGreeting({ msg: '좋은 아침이에요', sub: '오늘 하루도 건강하게 시작해봐요' })
      else if (hour < 17) setGreeting({ msg: '좋은 오후예요', sub: '점심 식사 후 약 챙기셨나요?' })
      else setGreeting({ msg: '좋은 저녁이에요', sub: '저녁 복약 시간을 확인해보세요' })

      // [추가] 오늘 증상 데이터 가져오기 (API 호출)
      try {
        const today = new Date().toISOString().split('T')[0]
        const response = await api.get(`/api/v1/daily-logs`, {
          params: {
            profile_id: selectedProfileId,
            days: 1
          }
        })
        if (response.data && response.data.length > 0) {
          const todayLogs = response.data.find(log => log.log_date === today)
          setTodaySymptoms(todayLogs?.symptoms || [])
          setTodayNote(todayLogs?.note || '')
        } else {
          setTodaySymptoms([])
          setTodayNote('')
        }
      } catch (error) {
        console.warn('Failed to fetch symptoms:', error)
        setTodaySymptoms([])
        setTodayNote('')
      }
    }

    fetchData()
  }, [selectedProfileId])

  // ── 표시할 챌린지 선택 (렌더 중 파생) ───────────────────────────────
  // 흐름: 진행 중 챌린지 목록 -> 마운트당 고정된 시드로 인덱스 계산 -> 1건 선택
  // effect + setState 로 뽑으면 목록의 참조가 바뀔 때마다 재추첨되어 표시가 흔들린다.
  const activeChallenge =
    activeChallenges.length > 0
      ? activeChallenges[Math.floor(challengePickSeed * activeChallenges.length)]
      : null

  // main 페이지 진입 시 / 프로필 전환 시 OCR drafts 동기화.
  useEffect(() => {
    if (selectedProfileId) refetchDrafts()
  }, [selectedProfileId, refetchDrafts])

  // window focus 시 drafts 재동기화 (백그라운드에서 다른 탭에서 등록·완료한 draft 반영)
  useEffect(() => {
    if (!selectedProfileId) return
    window.addEventListener('focus', refetchDrafts)
    return () => window.removeEventListener('focus', refetchDrafts)
  }, [selectedProfileId, refetchDrafts])

  // 카드에서 개별 draft 폐기 — 백엔드 DELETE 후 즉시 목록에서 제외.
  const handleDeleteDraft = useCallback(async (draftId) => {
    try {
      await api.delete(`/api/v1/ocr/draft/${draftId}`, {
        params: selectedProfileId ? { profile_id: selectedProfileId } : undefined,
      })
    } catch {
      // ignore
    }
    removeDraftLocally(draftId)
  }, [removeDraftLocally, selectedProfileId])

  // ── 첫 로그인 설문 모달 핸들러 (createProfile / updateProfile 분기) ────────
  // 흐름: 사용자가 본인 프로필 (relation_type='SELF') 미등록이면 createProfile,
  //       이미 있으면 updateProfile. mypage 의 건강 정보 수정도 같은 모달을 쓰며,
  //       호출 측이 다른 분기를 갖는다 (mypage 는 항상 update).
  const existingSelfProfile = profiles?.find((p) => p.id === selectedProfileId) || null
  const handleSurveySave = async (values) => {
    setIsSurveySubmitting(true)
    try {
      const healthSurvey = {
        age: parseInt(values.age) || null,
        gender: values.gender || null,
        height: parseInt(values.height) || null,
        weight: parseFloat(values.weight) || null,
        is_smoking: values.is_smoking,
        is_drinking: values.is_drinking,
        conditions: values.conditions?.length ? values.conditions : null,
        allergies: values.allergies?.length ? values.allergies : null,
      }
      if (existingSelfProfile) {
        await updateProfile(existingSelfProfile.id, {
          health_survey: healthSurvey,
          gender: values.gender || null,
        })
      } else {
        await createProfile({
          relation_type: 'SELF',
          name: userName || '나',
          health_survey: healthSurvey,
        })
      }
      toast.success('건강 정보가 저장되었습니다.')
      setShowSurvey(false)
    } catch (err) {
      console.error(err)
      showError(err.parsed?.message || '설문 저장에 실패했습니다.')
    } finally {
      setIsSurveySubmitting(false)
    }
  }
  const handleSurveySkip = async () => {
    if (!existingSelfProfile) {
      setIsSurveySubmitting(true)
      try {
        await createProfile({ relation_type: 'SELF', name: userName || '나', health_survey: null })
      } catch (err) {
        console.error(err)
      }
      setIsSurveySubmitting(false)
    }
    setShowSurvey(false)
  }

  if (isLoading) return <MainSkeleton />

  return (
    <div className={`transition-opacity duration-200 ${isRefreshing ? 'opacity-50 pointer-events-none' : 'opacity-100'}`}>
      {showSurvey && (
        <HealthSurveyModal
          info={existingSelfProfile?.health_survey}
          onClose={() => setShowSurvey(false)}
          onSave={handleSurveySave}
          onSkip={handleSurveySkip}
          title="건강 정보 입력"
          subtitle={`${userName} 님에게 딱 맞는 복약 가이드를 준비할게요`}
          showSkip
          isSubmitting={isSurveySubmitting}
        />
      )}
      {showChat && <ChatModal onClose={() => setShowChat(false)} profileId={selectedProfileId} />}

      {/* ── 히어로 섹션 (배경 이미지 슬라이드쇼 + 다크 오버레이) ── */}
      <section
        className="relative w-full min-h-[540px] flex items-center justify-center overflow-hidden bg-black"
        style={{
          backgroundImage: `url('${HERO_BG_IMAGES[currentBgIndex]}')`,
          backgroundSize: 'cover',
          backgroundPosition: 'center',
          transition: 'background-image 1s ease-in-out',
        }}
      >
        {/* 다크 그라데이션 오버레이 — 깊이감 + 텍스트 가독성 */}
        <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/45 to-black/35" />
        {/* 그리드 패턴 */}
        <div className="absolute inset-0 opacity-[0.08]" style={{ backgroundImage: 'radial-gradient(circle, #ffffff 1px, transparent 1px)', backgroundSize: '40px 40px' }} />

        <div className="relative z-10 text-center px-6 max-w-3xl mx-auto py-24">
          <p className="text-white/55 text-xs sm:text-sm font-bold mb-5 tracking-[0.22em] uppercase">{greeting.sub}</p>
          <h1 className="text-5xl md:text-7xl font-black text-white leading-[1.05] tracking-tight text-balance mb-9">
            {greeting.msg},<br /><span className="text-white/50">{userName} 님</span>
          </h1>
          <div className="flex flex-col sm:flex-row gap-3 justify-center">
            <Button variant="primary" size="lg" onClick={goToOcrFlow}>처방전 등록하기</Button>
            <Button variant="glass" size="lg" onClick={() => setShowChat(true)}>
              <MessageCircle size={20} /> AI 상담하기
            </Button>
          </div>

          {/* 이미지 인디케이터 — 클릭으로 수동 전환 (터치 영역 44px) */}
          <div className="flex gap-1 justify-center mt-12">
            {HERO_BG_IMAGES.map((_, i) => (
              <button
                key={i}
                type="button"
                onClick={() => setCurrentBgIndex(i)}
                aria-label={`배경 이미지 ${i + 1}`}
                className="h-11 w-11 cursor-pointer flex items-center justify-center rounded-full focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white/70"
              >
                <span className={`block h-2 rounded-full transition-all ${currentBgIndex === i ? 'w-8 bg-white' : 'w-2 bg-white/35'}`} />
              </button>
            ))}
          </div>
        </div>
      </section>

      <main className="max-w-7xl mx-auto w-full px-6 py-14">
        <div className="grid md:grid-cols-12 gap-8">
          <div className="md:col-span-8 space-y-8">

            {/* ── 오늘의 증상 ── */}
            <Card>
              <SectionHeader
                icon={<Activity size={20} />}
                title="오늘의 증상"
                action={
                  <button
                    onClick={() => router.push('/lifestyle-guide?tab=symptom')}
                    className="text-sm font-bold text-muted hover:text-ink transition-colors"
                  >
                    기록하기
                  </button>
                }
              />
              {todaySymptoms.length > 0 ? (
                <div className="space-y-4">
                  <div className="flex flex-wrap gap-2">
                    {todaySymptoms.map((s, idx) => (
                      <span key={idx} className="px-4 py-2 bg-surface-2 text-ink rounded-full text-sm font-bold border border-line">
                        {s}
                      </span>
                    ))}
                  </div>
                  {todayNote && (
                    <p className="text-muted text-sm leading-relaxed bg-surface-2/60 p-4 rounded-2xl border border-dashed border-line">
                      &quot;{todayNote}&quot;
                    </p>
                  )}
                </div>
              ) : (
                <div className="py-4 text-center">
                  <p className="text-muted text-sm mb-4">오늘 기록된 증상이 없습니다.</p>
                  <Button onClick={() => router.push('/lifestyle-guide?tab=symptom')}>지금 기록하기</Button>
                </div>
              )}
            </Card>

            {/* ── 복약 스케줄 (TodaySchedule 자체가 카드 + 헤더) ── */}
            {/* 약 목록 조회가 실패하면 일정이 "오늘 먹을 약 없음"으로 보인다.
                복약 누락으로 이어질 수 있는 오인이라 실패를 그 자리에 드러낸다. */}
            {medicationsError ? (
              <ErrorState
                error={medicationsErrorObject}
                title="복약 일정을 불러오지 못했어요"
                onRetry={refetchMedications}
                isRetrying={medicationsRefetching}
              />
            ) : (
              <TodaySchedule medications={medications} profileId={selectedProfileId} />
            )}
          </div>

          <div className="md:col-span-4 space-y-8">
            {/* ── 챌린지 카드 (accent 피처) ── */}
            <Card tone="accent" className="relative overflow-hidden group">
              <div className="absolute top-0 right-0 p-8 opacity-15 group-hover:scale-110 transition-transform duration-500">
                <Flame size={80} />
              </div>
              <div className="relative z-10">
                <div className="flex items-center gap-2 mb-6">
                  <span className="px-3 py-1 bg-accent-ink/15 rounded-full text-[10px] font-bold tracking-wider uppercase">Active Challenge</span>
                </div>
                {activeChallenge ? (
                  <>
                    <h3 className="text-2xl font-black mb-2">{activeChallenge.title}</h3>
                    <p className="text-sm mb-8 leading-relaxed opacity-75">{activeChallenge.description}</p>
                    <button onClick={() => router.push('/challenge')} className="w-full py-4 bg-accent-ink text-accent font-bold rounded-2xl hover:brightness-105 transition-all">진행 상황 보기</button>
                  </>
                ) : (
                  <>
                    <h3 className="text-2xl font-black mb-2">새로운 도전을<br />시작해보세요</h3>
                    <p className="text-sm mb-8 opacity-75">건강한 습관을 만드는 가장 쉬운 방법</p>
                    <button onClick={() => router.push('/challenge')} className="w-full py-4 bg-accent-ink text-accent font-bold rounded-2xl hover:brightness-105 transition-all">챌린지 둘러보기</button>
                  </>
                )}
              </div>
            </Card>

            {/* ── 복약 관리 카드 ── */}
            <Card>
              <h3 className="text-lg font-black text-ink mb-6">복약 관리</h3>
              <div className="space-y-4">
                {medications.slice(0, 2).map((med, index) => (
                  <div key={`${med.id}-${index}`} className="p-4 rounded-2xl bg-surface-2 border border-line">
                    <div className="flex justify-between items-start mb-1">
                      <p className="font-bold text-ink truncate flex-1">{med.medicine_name}</p>
                      <span className="text-[10px] font-bold text-accent bg-accent-soft px-2 py-0.5 rounded-full ml-2 flex-shrink-0">
                        {getRemainingDays(med)}
                      </span>
                    </div>
                    <p className="text-xs text-muted">{med.dosage}</p>
                  </div>
                ))}
                <button onClick={() => router.push('/medication')} className="w-full py-4 bg-surface-2 text-ink font-bold rounded-2xl hover:brightness-95 transition-all flex items-center justify-center gap-2">
                  <Plus size={18} /> 전체 보기
                </button>
              </div>
            </Card>
          </div>
        </div>
      </main>

      <ActiveDraftsCard
        drafts={activeDrafts}
        onSelect={(id) => router.push(`/ocr/result?draft_id=${id}`)}
        onDelete={handleDeleteDraft}
      />
    </div>
  )
}
