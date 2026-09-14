'use client'

// Profile 도메인 — TanStack Query adapter (PR-B 마이그레이션).
//
// 외부 API 시그니처 100% 호환:
//   profiles, selectedProfile, selectedProfileId, isLoading,
//   updateProfile, createProfile, deleteProfile,
//   setSelectedProfileId, refetchProfiles, RELATION_LABELS, RELATION_GENDER_DEFAULT.
//
// ⚠️ 선택 프로필의 계약 (2026-09-14 구조 변경):
//   `selectedProfileId` 는 **state 가 아니라 렌더 중 파생값**이다.
//   사용자가 고른 id(`pickedProfileId`) 를 목록과 대조해 유효하면 쓰고, 아니면
//   저장값 -> SELF -> 첫 프로필 순으로 물러난다(고른 프로필이 삭제돼도 되돌리지 않고 무시).
//   localStorage 반영은 **파생값을 보는 effect 한 곳이 단독 담당**한다 —
//   `setSelectedProfileId` 는 상태만 바꾼다(여기서 또 저장하면 이중 쓰기가 된다).
//
// 변경 핵심:
// - list GET 을 useQuery 로 교체 (staleTime 5분 — 거의 안 바뀜).
// - mutation 은 useMutation, onSuccess 에서 list cache 직접 patch.
// - profile 삭제 시 그 profile 의 prescription-groups / lifestyle-guides /
//   challenges 캐시 invalidate (BE cascade 와 동기화).

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { usePathname } from 'next/navigation'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import api from '@/lib/api'
import { qk, STALE } from '@/queries/keys'

const ProfileContext = createContext(null)

const STORAGE_KEY = 'selectedProfileId'

const PUBLIC_PATHS = ['/', '/login']

// 가족 관계 enum 8종 단일 매핑 — relation_type 만으로 라벨 결정 (gender 합성 없음)
const RELATION_LABELS = {
  SELF: '본인',
  FATHER: '아버지',
  MOTHER: '어머니',
  SON: '아들',
  DAUGHTER: '딸',
  HUSBAND: '남편',
  WIFE: '아내',
  OTHER: '가족',
}

// relation_type → 기본 gender 매핑 (FE form 의 자동 채움 UX)
// SELF / OTHER 는 사용자 직접 입력. BE 도 동일 default 정책 (RELATION_DEFAULT_GENDER).
export const RELATION_GENDER_DEFAULT = {
  FATHER: 'MALE',
  MOTHER: 'FEMALE',
  SON: 'MALE',
  DAUGHTER: 'FEMALE',
  HUSBAND: 'MALE',
  WIFE: 'FEMALE',
}

export function ProfileProvider({ children }) {
  const pathname = usePathname()
  const isPublic = PUBLIC_PATHS.includes(pathname) || pathname.startsWith('/auth/')
  const qc = useQueryClient()

  // 사용자가 직접 고른 id. 실제로 쓰이는 선택값은 아래에서 목록과 대조해 파생한다
  // (고른 프로필이 삭제돼도 이 값을 effect 로 되돌리지 않고 파생 단계에서 무시한다).
  const [pickedProfileId, setPickedProfileId] = useState(null)

  // ── 1) list query ─────────────────────────────────────────────────
  // public path 에서는 enabled=false → fetch 0회 (인증 없는 라우트에서 401 노이즈 방지).
  const listQuery = useQuery({
    queryKey: qk.profile.list(),
    enabled: !isPublic,
    staleTime: STALE.profile,
    queryFn: async () => {
      const { data } = await api.get('/api/v1/profiles')
      return data || []
    },
  })
  // `data || []` 를 그대로 쓰면 data 가 undefined 인 구간(로딩·public path)에서 매 렌더
  // 새 배열이 만들어져 아래 파생·effect 의존성을 흔든다.
  const profiles = useMemo(() => listQuery.data || [], [listQuery.data])
  // 첫 로드 + public path 모두에서 일관된 isLoading.
  const isLoading = isPublic ? false : listQuery.isLoading

  // ── 선택 프로필 파생 (렌더 중) ─────────────────────────────────────
  // 흐름: 목록 없음 -> null / 고른 값이 목록에 있음 -> 그 값
  //       -> 저장값이 목록에 있음 -> 복원 -> 그 외 SELF(없으면 첫 번째)
  // localStorage 읽기는 목록이 비어 있지 않을 때만 결과에 반영된다. 하이드레이션 시점에는
  // 목록이 아직 비어 있어 서버 스냅샷(null)과 같은 값이 나오므로 불일치가 생기지 않는다.
  const savedProfileId = typeof window !== 'undefined' ? localStorage.getItem(STORAGE_KEY) : null
  const selectedProfileId = useMemo(() => {
    if (profiles.length === 0) return null
    if (pickedProfileId && profiles.some((p) => p.id === pickedProfileId)) return pickedProfileId
    if (savedProfileId && profiles.some((p) => p.id === savedProfileId)) return savedProfileId
    return (profiles.find((p) => p.relation_type === 'SELF') || profiles[0]).id
  }, [profiles, pickedProfileId, savedProfileId])

  // ── 선택값을 localStorage 에 반영 ──────────────────────────────────
  // 흐름: 파생된 선택값이 바뀌면 저장 / 선택이 사라졌으면(있다가 없어진 경우만) 제거
  // localStorage 는 React 바깥의 저장소라 effect 가 맞는 자리다. 여기서 state 는 건드리지 않는다.
  useEffect(() => {
    if (typeof window === 'undefined') return
    if (selectedProfileId) {
      localStorage.setItem(STORAGE_KEY, selectedProfileId)
      return
    }
    // 처음부터 목록이 비어 있던 경우까지 지우지는 않는다(기존 동작 유지).
    if (pickedProfileId) localStorage.removeItem(STORAGE_KEY)
  }, [selectedProfileId, pickedProfileId])

  // ── 2) mutations — 응답으로 cache 직접 patch ──────────────────────
  const updateMutation = useMutation({
    mutationFn: async ({ id, patch }) => {
      const { data } = await api.patch(`/api/v1/profiles/${id}`, patch)
      return data
    },
    onSuccess: (updated) => {
      qc.setQueryData(qk.profile.list(), (prev = []) =>
        prev.map((p) => (p.id === updated.id ? updated : p)),
      )
      qc.setQueryData(qk.profile.detail(updated.id), updated)
    },
  })

  const createMutation = useMutation({
    mutationFn: async (input) => {
      const { data } = await api.post('/api/v1/profiles', input)
      return data
    },
    onSuccess: (created) => {
      qc.setQueryData(qk.profile.list(), (prev = []) => [...prev, created])
    },
  })

  const deleteMutation = useMutation({
    mutationFn: async (id) => {
      const target = profiles.find((p) => p.id === id)
      if (target?.relation_type === 'SELF') {
        throw new Error('본인 프로필은 삭제할 수 없습니다. 계정 탈퇴 메뉴를 이용해주세요.')
      }
      await api.delete(`/api/v1/profiles/${id}`)
      return id
    },
    onSuccess: (id) => {
      qc.setQueryData(qk.profile.list(), (prev = []) => prev.filter((p) => p.id !== id))
      qc.removeQueries({ queryKey: qk.profile.detail(id) })
      // BE cascade — 그 profile 의 처방전 / medication / 가이드 / 챌린지 / 챗 / OCR 까지 정리됨.
      qc.invalidateQueries({ queryKey: qk.prescriptionGroups.all() })
      qc.invalidateQueries({ queryKey: qk.medications.all() })
      qc.invalidateQueries({ queryKey: qk.lifestyleGuides.all() })
      qc.invalidateQueries({ queryKey: qk.challenges.all() })
      qc.invalidateQueries({ queryKey: qk.chatSessions.all() })
      qc.invalidateQueries({ queryKey: qk.ocrDraft.all() })
      qc.invalidateQueries({ queryKey: qk.dailyLogs.all() })
    },
  })

  // 외부 호환 API.
  const updateProfile = useCallback(
    (id, patch) => updateMutation.mutateAsync({ id, patch }),
    [updateMutation],
  )
  const createProfile = useCallback((input) => createMutation.mutateAsync(input), [createMutation])
  const deleteProfile = useCallback((id) => deleteMutation.mutateAsync(id), [deleteMutation])
  const refetchProfiles = useCallback(() => listQuery.refetch(), [listQuery])

  // 사용자 선택 — 저장은 위 effect 가 파생값 기준으로 처리하므로 여기선 상태만 바꾼다.
  const setSelectedProfileId = useCallback((id) => setPickedProfileId(id), [])

  // ── computed ───────────────────────────────────────────────
  const selectedProfile = profiles.find((p) => p.id === selectedProfileId) || null

  return (
    <ProfileContext.Provider
      value={{
        profiles,
        selectedProfile,
        selectedProfileId,
        isLoading,
        updateProfile,
        createProfile,
        deleteProfile,
        setSelectedProfileId,
        refetchProfiles,
        RELATION_LABELS,
      }}
    >
      {children}
    </ProfileContext.Provider>
  )
}

export function useProfile() {
  const ctx = useContext(ProfileContext)
  if (!ctx) throw new Error('useProfile must be used within ProfileProvider')
  return ctx
}
