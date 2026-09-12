'use client'
import { useState, useEffect, useRef, Suspense } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { User, Activity, Users, Home, Trash2, X, Check, Plus, FileText, LogOut, Pencil } from 'lucide-react'
import { Controller, useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'

import EmptyState from '@/components/common/EmptyState'
import BottomNav from '@/components/layout/BottomNav'
import LogoutModal, { useLogout, DeleteAccountModal, useDeleteAccount } from '@/components/auth/LogoutModal'
import api, { handleApiError } from '@/lib/api'
import toast from 'react-hot-toast'
import { useConfirm } from '@/components/common/ConfirmDialog'
import FormError from '@/components/form/FormError'
import HealthSurveyModal from '@/components/common/HealthSurveyModal'
import { useProfile } from '@/contexts/ProfileContext'
import {
  familyProfileSchema,
  nicknameUpdateSchema,
} from '@/schemas'

// --- 모달 컴포넌트들 ---
function Modal({ title, children, onClose, onSave, saveDisabled }) {
  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-[100] flex items-center justify-center p-4">
      <div className="bg-surface rounded-[40px] w-full max-w-lg overflow-hidden shadow-2xl animate-in fade-in zoom-in duration-200">
        <div className="flex justify-between items-center p-8 border-b border-line">
          <h3 className="text-xl font-black text-ink">{title}</h3>
          <button onClick={onClose} className="p-2 hover:bg-surface-2 rounded-full transition-colors cursor-pointer">
            <X size={24} className="text-muted" />
          </button>
        </div>
        <div className="p-8 max-h-[70vh] overflow-y-auto">{children}</div>
        <div className="p-8 pt-4 flex gap-3">
          <button onClick={onClose} className="flex-1 py-4 rounded-2xl bg-surface-2 text-muted font-bold hover:bg-surface-2 transition-all cursor-pointer">취소</button>
          <button onClick={onSave} disabled={saveDisabled} className="flex-1 py-4 rounded-2xl bg-accent text-accent-ink font-black hover:brightness-110 transition-all shadow-lg cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed">저장하기</button>
        </div>
      </div>
    </div>
  )
}

function BasicInfoModal({ info, onClose, onSave }) {
  const {
    register,
    handleSubmit,
    formState: { errors, isValid },
  } = useForm({
    resolver: zodResolver(nicknameUpdateSchema),
    mode: 'onChange',
    defaultValues: { nickname: info?.name?.split('(')[0] || '' },
  })

  const onSubmit = (values) => {
    onSave(values)
  }

  return (
    <Modal title="계정 정보 수정" onClose={onClose} onSave={handleSubmit(onSubmit)} saveDisabled={!isValid}>
      <div className="space-y-6">
        <div>
          <label className="text-xs font-black text-muted mb-2 block ml-1">닉네임</label>
          <input
            type="text"
            {...register('nickname')}
            className={`w-full px-6 py-4 bg-surface-2 border focus:bg-surface rounded-2xl outline-none font-bold text-ink transition-all ${
              errors.nickname ? 'border-red-500' : 'border-transparent focus:border-line'
            }`}
          />
          <FormError name="nickname" errors={errors} />
        </div>
      </div>
    </Modal>
  )
}

// 가족 관계 선택지 — 7종 (SELF 제외, OTHER 포함). 라벨 = ProfileContext 의 RELATION_LABELS 와 일치.
// SELF 는 본인 계정이므로 가족 추가 흐름에 절대 노출되면 안 됨 — zod 'familyProfileSchema'
// 의 enum 에도 SELF 가 빠져 있어 validation 에러를 유발한다 (운영 검증 발견 이슈).
const FAMILY_RELATION_OPTIONS = [
  { value: 'FATHER', label: '아버지' },
  { value: 'MOTHER', label: '어머니' },
  { value: 'SON', label: '아들' },
  { value: 'DAUGHTER', label: '딸' },
  { value: 'HUSBAND', label: '남편' },
  { value: 'WIFE', label: '아내' },
  { value: 'OTHER', label: '기타' },
]

// relation_type → 기본 gender 매핑 (BE 의 RELATION_DEFAULT_GENDER 와 동기화)
const RELATION_GENDER_DEFAULT = {
  FATHER: 'MALE',
  MOTHER: 'FEMALE',
  SON: 'MALE',
  DAUGHTER: 'FEMALE',
  HUSBAND: 'MALE',
  WIFE: 'FEMALE',
}

function FamilyModal({ member, onClose, onSave }) {
  const {
    register,
    control,
    handleSubmit,
    setValue,
    formState: { errors, isValid },
  } = useForm({
    resolver: zodResolver(familyProfileSchema),
    mode: 'onChange',
    defaultValues: member
      ? { name: member.name, relation_type: member.relation_type, gender: member.gender || null }
      : { name: '', relation_type: 'FATHER', gender: 'MALE' },
  })

  // 관계 변경 시 gender 자동 default — 사용자가 별도로 선택한 성별이 있어도 default 로 덮음
  // (BE 의 RELATION_DEFAULT_GENDER 와 동기화). OTHER 는 default null.
  const handleRelationChange = (newRelation) => {
    const defaultGender = RELATION_GENDER_DEFAULT[newRelation] ?? null
    setValue('relation_type', newRelation, { shouldValidate: true })
    setValue('gender', defaultGender, { shouldValidate: true })
  }

  const onSubmit = (values) => onSave(values)

  return (
    <Modal title={member ? '가족 정보 수정' : '가족 추가하기'} onClose={onClose} onSave={handleSubmit(onSubmit)} saveDisabled={!isValid}>
      <div className="space-y-6">
        <div>
          <label className="text-xs font-black text-muted mb-2 block ml-1">이름</label>
          <input
            type="text"
            placeholder="이름을 입력하세요"
            {...register('name')}
            className={`w-full px-6 py-4 bg-surface-2 rounded-2xl outline-none font-bold text-ink border transition-colors ${
              errors.name ? 'border-red-500' : 'border-transparent'
            }`}
          />
          <FormError name="name" errors={errors} />
        </div>
        <div>
          <label className="text-xs font-black text-muted mb-2 block ml-1">관계</label>
          <Controller
            control={control}
            name="relation_type"
            render={({ field }) => (
              <select
                value={field.value}
                onChange={(e) => handleRelationChange(e.target.value)}
                className="w-full px-6 py-4 bg-surface-2 rounded-2xl outline-none font-bold text-ink appearance-none"
              >
                {FAMILY_RELATION_OPTIONS.map(({ value, label }) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            )}
          />
          <FormError name="relation_type" errors={errors} />
        </div>
        <div>
          <label className="text-xs font-black text-muted mb-2 block ml-1">성별</label>
          <Controller
            control={control}
            name="gender"
            render={({ field }) => (
              <div className="flex gap-3">
                {['MALE', 'FEMALE'].map((g) => (
                  <button
                    key={g}
                    type="button"
                    onClick={() => field.onChange(g)}
                    className={`flex-1 py-4 rounded-2xl text-sm font-bold border transition-all cursor-pointer ${
                      field.value === g
                        ? 'bg-accent text-accent-ink border-accent'
                        : 'bg-surface-2 text-muted border-line hover:bg-surface-2'
                    }`}
                  >
                    {g === 'MALE' ? '남성' : '여성'}
                  </button>
                ))}
              </div>
            )}
          />
        </div>
      </div>
    </Modal>
  )
}

function MyPageSkeleton() {
  return (
    <div className="max-w-[1400px] mx-auto w-full px-8 py-12 min-h-screen bg-surface-2">
      <div className="h-32 bg-surface rounded-[40px] mb-10 animate-pulse" />
      <div className="grid md:grid-cols-12 gap-8">
        <div className="md:col-span-4 space-y-6"><div className="h-64 bg-surface rounded-[40px] animate-pulse" /><div className="h-80 bg-surface rounded-[40px] animate-pulse" /></div>
        <div className="md:col-span-8"><div className="h-full bg-surface rounded-[40px] animate-pulse" /></div>
      </div>
    </div>
  )
}

function MyPageContent() {
  const router = useRouter()
  const confirm = useConfirm()
  const searchParams = useSearchParams()
  const {
    selectedProfileId: profileId,
    selectedProfile,
    profiles,
    updateProfile,
    createProfile,
    deleteProfile,
    setSelectedProfileId,
    refetchProfiles,
  } = useProfile()
  const isInitialLoad = useRef(true)
  const [isLoading, setIsLoading] = useState(true)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [activeMenu, setActiveMenu] = useState('기본정보')
  // ProfileContext 의 데이터를 그대로 파생 사용 (single source of truth).
  // mutation 시 ProfileContext 가 in-place 갱신하므로 자동 리렌더.
  const userProfile = selectedProfile
  // 가족 관리 탭 = "내 모든 프로필" 뷰. SELF 도 포함해 표시하되 SELF 를 항상 맨 앞으로.
  const family = [...profiles].sort((a, b) => {
    if (a.relation_type === 'SELF') return -1
    if (b.relation_type === 'SELF') return 1
    return 0
  })
  const [ongoingCount, setOngoingCount] = useState(0)
  const [streakDays, setStreakDays] = useState(0)
  const [todayTakenCount, setTodayTakenCount] = useState(0)
  const [modalType, setModalType] = useState(null)
  const [selectedFamilyMember, setSelectedFamilyMember] = useState(null)

  // 가족 관계 enum 8종 단일 매핑 — gender 합성 없이 라벨 결정
  const relationLabels = {
    SELF: '본인',
    FATHER: '아버지',
    MOTHER: '어머니',
    SON: '아들',
    DAUGHTER: '딸',
    HUSBAND: '남편',
    WIFE: '아내',
    OTHER: '기타',
  }

  useEffect(() => {
    if (!profileId) return
    fetchData()
  }, [profileId])

  // 가족관리 탭은 모든 프로필 상태에서 표시되며 (HEAD 의 옵션 B fix), main 의 강제 탭
  // 전환 useEffect 는 의도와 어긋나 제거.

  // ProfileSwitcher 의 "프로필 추가" 버튼이 ?tab=family 로 진입하면 가족관리 탭 자동 활성화.
  // 활성화 직후 URL 의 ?tab= query 는 router.replace 로 정리 (history 오염 방지).
  useEffect(() => {
    if (searchParams.get('tab') === 'family') {
      setActiveMenu('가족관리')
      router.replace('/mypage')
    }
  }, [searchParams, router])

  // ProfileContext 가 이미 가진 profiles 재사용 — /profiles 와 /profiles/{id} GET 안 함.
  // 페이지 자체에서 GET 하는 건 챌린지/스트릭 같이 ProfileContext 가 모르는 데이터만.
  const fetchData = async () => {
    if (isInitialLoad.current) setIsLoading(true)
    else setIsRefreshing(true)
    try {
      // ProfileContext 가 profile / list 는 이미 fetch — 페이지는 챌린지/스트릭/오늘
      // 복약 같은 Context 외부 데이터만 호출.
      const [challengeRes, streakRes, todayLogsRes] = await Promise.all([
        api.get(`/api/v1/challenges?profile_id=${profileId}`),
        api.get(`/api/v1/intake-logs/streak?profile_id=${profileId}`),
        api.get(`/api/v1/intake-logs?profile_id=${profileId}`),
      ])
      // 진행 중인 챌린지 개수 계산 — 챌린지 리스트에서 is_active + status 필터링. BE 에서 별도 카운트 제공 안 함.
      const ongoing = (challengeRes.data || []).filter(c =>
        c.is_active === true && c.challenge_status === 'IN_PROGRESS').length;
        setOngoingCount(ongoing);

      setStreakDays(streakRes.data.streak_days ?? 0)
      setTodayTakenCount((todayLogsRes.data || []).filter(l => l.intake_status === 'TAKEN').length)
    } catch (err) { handleApiError(err) } finally {
      setIsLoading(false)
      setIsRefreshing(false)
      isInitialLoad.current = false
    }
  }

  // mutation 핸들러는 ProfileContext 가 응답으로 in-place 갱신하므로 수동 fetchData 호출 안 함.
  // challenge/streak 데이터는 [profileId] effect 가 selectedProfileId 변경 시 자동 재조회 —
  // 활성 프로필 삭제 시 stale profileId 로 fetchData 가 호출되어 발생하던 404 경합 제거.

  const handleSaveBasic = async (newData) => {
    try {
      // BasicInfoModal 호출자가 selectedFamilyMember 로 명시한 프로필을 우선
      // 사용. 미지정이면 활성 프로필. (가족관리 탭 본인 카드 클릭 → SELF 강제,
      // 기본정보 탭 수정 → 활성 프로필 — 흐름 분리)
      const target = selectedFamilyMember ?? userProfile
      await updateProfile(target.id, { name: newData.nickname })
      toast.success('닉네임이 수정되었습니다.')
      if (refetchProfiles) await refetchProfiles()
      setModalType(null)
      setSelectedFamilyMember(null)
    } catch (err) { handleApiError(err) }
  }

  const handleSaveHealth = async (newData) => {
    try {
      const healthSurvey = {
        age: parseInt(newData.age) || null,
        gender: newData.gender || null,
        height: parseInt(newData.height) || null,
        weight: parseFloat(newData.weight) || null,
        is_smoking: newData.is_smoking,
        is_drinking: newData.is_drinking,
        conditions: newData.conditions.length > 0 ? newData.conditions : null,
        allergies: newData.allergies.length > 0 ? newData.allergies : null,
      }
      // gender 는 별도 컬럼으로도 저장 (BE 의 Profile.gender) — health_survey.gender 와 dual write
      await updateProfile(userProfile.id, { health_survey: healthSurvey, gender: newData.gender || null })
      toast.success('건강 정보가 업데이트되었습니다.')
      setModalType(null)
    } catch (err) { handleApiError(err) }
  }

  const handleSaveFamily = async (newData) => {
    try {
      // BE 가 RELATION_DEFAULT_GENDER 로 자동 채우므로 gender 미지정 시 null 도 안전.
      // 사용자가 form 에서 성별 토글 변경 시 그 값이 그대로 BE 에 전송되어 우선됨.
      const payload = {
        name: newData.name,
        relation_type: newData.relation_type,
        gender: newData.gender,
      }
      if (selectedFamilyMember) {
        await updateProfile(selectedFamilyMember.id, payload)
        toast.success('가족 정보가 수정되었습니다.')
      } else {
        await createProfile(payload)
        toast.success('가족이 추가되었습니다.')
      }

      if (refetchProfiles) await refetchProfiles();
      setModalType(null);
      setSelectedFamilyMember(null);
    } catch (err) { handleApiError(err); }
  }

  const handleDeleteFamily = async (id, e) => {
    e.stopPropagation()
    const ok = await confirm({
      title: '가족 프로필 삭제',
      message: '이 가족 프로필을 삭제할까요?\n관련 약품·가이드·챌린지가 함께 정리됩니다.',
      confirmLabel: '삭제',
      danger: true,
    })
    if (!ok) return
    try {
      await deleteProfile(id)
      toast.success('삭제되었습니다.')
    } catch (err) { handleApiError(err) }
  }

  const { showLogoutModal, setShowLogoutModal, handleLogout } = useLogout()
  const { showDeleteModal, setShowDeleteModal, handleDeleteAccount } = useDeleteAccount()

  if (isLoading || !profileId) return <MyPageSkeleton />

  const menuItems = [
    { id: '기본정보', label: '기본 정보', icon: <User size={18} /> },
    { id: '건강정보', label: '건강 정보', icon: <Activity size={18} /> },
    { id: '가족관리', label: '가족 관리', icon: <Users size={18} /> },
  ]

  // 상세 관계 텍스트 — gender 합성 없이 enum 8종 단일 매핑
  const getDetailRelation = (profile) => {
    const rel = profile?.relation_type
    if (rel === 'SELF') return '본인 계정'
    return relationLabels[rel] ?? '가족'
  }

  return (
    <main className={`max-w-[1400px] mx-auto w-full px-8 py-12 min-h-screen bg-surface-2 relative transition-opacity duration-200 ${isRefreshing ? 'opacity-50 pointer-events-none' : 'opacity-100'}`}>
      <div className="flex justify-between items-end mb-10 bg-surface p-10 rounded-[40px] shadow-sm border border-line">
        <div>
          <p className="text-muted text-sm font-bold mb-2">내 설정 및 관리</p>
          <h1 className="text-4xl font-black text-ink">마이페이지</h1>
        </div>
        <div className="hidden md:flex items-center gap-10">
          <button onClick={() => router.push('/main')} className="flex items-center gap-2 text-muted font-bold hover:text-ink transition-all cursor-pointer"><Home size={18} /> 홈</button>
          <button className="flex items-center gap-2 text-ink font-black"><User size={18} /> 마이페이지</button>
        </div>
      </div>

      <div className="grid md:grid-cols-12 gap-8">
        <div className="md:col-span-4 space-y-6">
          <div className="bg-surface rounded-[40px] shadow-sm p-8 border border-line">
            <div className="flex flex-col items-center text-center">
              <div className="w-24 h-24 bg-accent rounded-full flex items-center justify-center shadow-lg mb-4 border-4 border-surface"><User size={40} className="text-accent-ink" /></div>
              <h2 className="text-xl font-black text-ink mb-1">{userProfile?.name.split('(')[0]}님</h2>
              {/* [수정] 상단 프로필 요약 관계 표시 상세화 */}
              <p className="text-muted text-xs font-bold mb-6">{getDetailRelation(userProfile)}</p>
              <div className="grid grid-cols-3 gap-3 w-full">
                <div className="bg-surface-2 p-4 rounded-[24px] border border-line">
                  <p className="text-[10px] font-black text-muted mb-1">연속 복약</p>
                  <p className="text-lg font-black text-ink">{streakDays}일째 🔥</p>
                </div>
                <div className={`p-4 rounded-[24px] border ${todayTakenCount > 0 ? 'bg-green-50 border-green-100' : 'bg-surface-2 border-line'}`}>
                  <p className={`text-[10px] font-black mb-1 ${todayTakenCount > 0 ? 'text-green-600' : 'text-muted'}`}>오늘 복약</p>
                  <p className="text-lg font-black text-ink">{todayTakenCount > 0 ? `${todayTakenCount}종 완료` : '-'}</p>
                </div>
                <div className="bg-orange-50 p-4 rounded-[24px] border border-orange-100">
                  <p className="text-[10px] font-black text-orange-500 mb-1">진행 챌린지</p>
                  <p className="text-lg font-black text-ink">{ongoingCount}개 🏆</p>
                </div>
              </div>
            </div>
          </div>

          <div className="bg-surface rounded-[40px] shadow-sm p-4 border border-line">
            <nav className="flex flex-col space-y-2">
              {menuItems.map((item) => (
                <button key={item.id} onClick={() => setActiveMenu(item.id)} className={`flex items-center gap-4 px-6 py-4 rounded-[24px] transition-all ${activeMenu === item.id ? 'bg-accent text-accent-ink font-black shadow-lg' : 'text-muted hover:bg-surface-2 font-bold'}`}>
                  <span>{item.icon}</span><span className="text-sm">{item.label}</span>
                </button>
              ))}
            </nav>
          </div>
        </div>

        <div className="md:col-span-8">
          <div className="bg-surface rounded-[40px] shadow-sm p-10 border border-line h-full min-h-[600px]">
            {activeMenu === '기본정보' && (
              <div className="space-y-8 h-full flex flex-col">
                <div className="flex justify-between items-center mb-4">
                  <h3 className="text-2xl font-black text-ink">계정 정보</h3>
                  <button onClick={() => { setSelectedFamilyMember(null); setModalType('basic') }} className="text-xs font-bold text-muted hover:bg-surface-2 px-4 py-2 rounded-xl transition-all border border-line cursor-pointer">정보 수정</button>
                </div>
                <div className="space-y-4">
                  <div className="flex justify-between items-center p-6 bg-surface-2 rounded-[28px]">
                    <span className="text-sm text-muted font-black">닉네임</span>
                    <span className="text-base font-black text-ink">{userProfile?.name.split('(')[0]}</span>
                  </div>
                  <div className="flex justify-between items-center p-6 bg-surface-2 rounded-[28px]">
                    <span className="text-sm text-muted font-black">관계</span>
                    <div className="bg-accent-soft px-3 py-1.5 rounded-full border border-accent/20">
                      {/* [수정] 기본 정보 탭 관계 표시 상세화 */}
                      <span className="text-sm font-black text-accent">{getDetailRelation(userProfile).replace('부모님', '부모').replace('계정', '')}</span>
                    </div>
                  </div>
                </div>
                <div className="mt-auto pt-10 space-y-6">
                  <button onClick={() => setShowLogoutModal(true)} className="w-full bg-surface border-2 border-line text-muted py-5 rounded-[28px] text-sm font-black hover:bg-surface-2 cursor-pointer transition-all">로그아웃</button>
                  <div className="flex items-center justify-center">
                    <button onClick={() => setShowDeleteModal(true)} className="text-xs text-muted hover:text-red-400 transition-colors cursor-pointer underline underline-offset-2">회원 탈퇴</button>
                  </div>
                </div>
              </div>
            )}

            {activeMenu === '건강정보' && (
              <div className="space-y-8">
                <div className="flex justify-between items-center mb-4">
                  <h3 className="text-2xl font-black text-ink">건강 프로필</h3>
                  <button onClick={() => setModalType('health')} className="text-xs font-black text-muted hover:bg-surface-2 px-4 py-2 rounded-xl transition-all border border-line cursor-pointer">수정하기</button>
                </div>
                <div className="grid sm:grid-cols-2 gap-6">
                  <div className="p-8 bg-surface-2 rounded-[32px] border border-line"><p className="text-xs font-black text-muted mb-2">나이</p><p className="text-xl font-black text-ink">{userProfile?.health_survey?.age ? `${userProfile.health_survey.age}세` : '-'}</p></div>
                  <div className="p-8 bg-surface-2 rounded-[32px] border border-line"><p className="text-xs font-black text-muted mb-2">성별</p><p className="text-xl font-black text-ink">{(() => { const g = userProfile?.gender ?? userProfile?.health_survey?.gender; return g === 'MALE' ? '남성' : g === 'FEMALE' ? '여성' : '-' })()}</p></div>
                  <div className="p-8 bg-surface-2 rounded-[32px] border border-line"><p className="text-xs font-black text-muted mb-2">키 / 몸무게</p><p className="text-xl font-black text-ink">{userProfile?.health_survey?.height ? `${userProfile.health_survey.height}cm` : '-'} / {userProfile?.health_survey?.weight ? `${userProfile.health_survey.weight}kg` : '-'}</p></div>
                  <div className="p-8 bg-surface-2 rounded-[32px] border border-line"><p className="text-xs font-black text-muted mb-2">흡연 / 음주</p><p className="text-xl font-black text-ink">{userProfile?.health_survey?.is_smoking === true ? '흡연' : userProfile?.health_survey?.is_smoking === false ? '비흡연' : '-'} / {userProfile?.health_survey?.is_drinking === true ? '음주' : userProfile?.health_survey?.is_drinking === false ? '비음주' : '-'}</p></div>
                  <div className="p-8 bg-surface-2 rounded-[32px] border border-line"><p className="text-xs font-black text-muted mb-2">보유 질환</p><p className="text-xl font-black text-ink">{userProfile?.health_survey?.conditions?.join(', ') || '없음'}</p></div>
                  <div className="p-8 bg-surface-2 rounded-[32px] border border-line"><p className="text-xs font-black text-muted mb-2">특이 알레르기</p><p className="text-xl font-black text-ink">{userProfile?.health_survey?.allergies?.join(', ') || '없음'}</p></div>
                </div>
              </div>
            )}

            {activeMenu === '가족관리' && (
              <div className="space-y-8">
                <div className="flex justify-between items-center mb-4">
                  <h3 className="text-2xl font-black text-ink">함께 관리하는 가족</h3>
                  <button onClick={() => { setSelectedFamilyMember(null); setModalType('family'); }} className="bg-accent text-accent-ink px-6 py-3 rounded-2xl text-sm font-black hover:brightness-110 cursor-pointer">+ 가족 추가하기</button>
                </div>
                {family.length > 0 ? (
                  <div className="grid sm:grid-cols-2 gap-4">
                    {family.map((member) => {
                      const isSelf = member.relation_type === 'SELF'
                      const isActive = member.id === profileId
                      // 카드 본체 클릭 = 프로필 전환. 편집/삭제는 stopPropagation 으로 분리.
                      const handleSwitchProfile = () => {
                        if (!isActive) setSelectedProfileId(member.id)
                      }
                      // 본인(SELF) 은 관계 변경 불가 — 닉네임만 BasicInfoModal 로 수정.
                      // 가족(FATHER/MOTHER/...)은 기존 FamilyModal (관계+성별+이름).
                      // 활성 프로필이 가족이라도 본인 카드 클릭 시엔 SELF row 를
                      // 대상으로 — selectedFamilyMember 에 SELF member 명시.
                      const handleEdit = (e) => {
                        e.stopPropagation()
                        if (isSelf) {
                          setSelectedFamilyMember(member)
                          setModalType('basic')
                        } else {
                          setSelectedFamilyMember(member)
                          setModalType('family')
                        }
                      }
                      // 상세 호칭 — relation_type enum 8종 단일 매핑 (gender 합성 없음)
                      const detailLabel = relationLabels[member.relation_type] ?? '가족'
                      return (
                        <div
                          key={member.id}
                          onClick={handleSwitchProfile}
                          className={`relative rounded-[32px] p-8 transition-all flex justify-between items-center group cursor-pointer ${
                            isActive
                              ? 'bg-surface shadow-lg ring-2 ring-accent'
                              : isSelf
                                ? 'bg-surface-2 hover:bg-surface-2 border border-line'
                                : 'bg-surface-2 hover:bg-surface hover:shadow-md'
                          }`}
                        >
                          {isActive && (
                            <span className="absolute top-3 right-3 bg-accent text-accent-ink text-[10px] font-black px-2.5 py-1 rounded-full flex items-center gap-1">
                              <Check size={11} />현재 활성
                            </span>
                          )}
                          <div className="flex items-center gap-5">
                            <div className={`w-16 h-16 rounded-[24px] flex items-center justify-center text-2xl font-black transition-all ${isSelf ? 'bg-accent text-accent-ink' : 'bg-surface text-ink group-hover:bg-accent group-hover:text-accent-ink'}`}>{member.name[0]}</div>
                            <div>
                              <div className="flex items-center gap-2">
                                <p className="text-lg font-black text-ink">{member.name}</p>
                                {isSelf && <span className="bg-accent text-accent-ink text-[10px] font-black px-2 py-0.5 rounded-full">본인</span>}
                              </div>
                              <p className="text-xs font-bold text-muted uppercase">{detailLabel}</p>
                            </div>
                          </div>
                          <div className="flex items-center gap-2">
                            <button
                              onClick={handleEdit}
                              aria-label={isSelf ? '본인 정보 수정' : '가족 정보 수정'}
                              className="w-10 h-10 bg-surface rounded-full flex items-center justify-center text-muted hover:text-ink shadow-sm cursor-pointer"
                            >
                              <Pencil size={16} />
                            </button>
                            {!isSelf && (
                              <button
                                onClick={(e) => handleDeleteFamily(member.id, e)}
                                aria-label="가족 삭제"
                                className="w-10 h-10 bg-surface rounded-full flex items-center justify-center text-muted hover:text-red-500 shadow-sm cursor-pointer"
                              >
                                <Trash2 size={18} />
                              </button>
                            )}
                          </div>
                        </div>
                      )
                    })}
                  </div>
                ) : (
                  <div className="py-20 bg-surface-2 rounded-[40px] border border-dashed border-line">
                    <EmptyState title="등록된 가족이 없어요" message="우측 상단의 버튼을 눌러 가족을 추가해보세요!" />
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      {modalType === 'basic' && (
        <BasicInfoModal
          info={selectedFamilyMember ?? userProfile}
          onClose={() => { setModalType(null); setSelectedFamilyMember(null) }}
          onSave={handleSaveBasic}
        />
      )}
      {modalType === 'health' && (
        <HealthSurveyModal
          info={userProfile?.health_survey}
          onClose={() => setModalType(null)}
          onSave={handleSaveHealth}
          title="건강 프로필 수정"
        />
      )}
      {modalType === 'family' && <FamilyModal member={selectedFamilyMember} onClose={() => { setModalType(null); setSelectedFamilyMember(null); }} onSave={handleSaveFamily} />}
      {showLogoutModal && <LogoutModal onClose={() => setShowLogoutModal(false)} onConfirm={handleLogout} />}
      {showDeleteModal && <DeleteAccountModal onClose={() => setShowDeleteModal(false)} onConfirm={handleDeleteAccount} />}
      <BottomNav />
    </main>
  )
}

export default function MyPage() {
  return (
    <Suspense fallback={<MyPageSkeleton />}>
      <MyPageContent />
    </Suspense>
  )
}
