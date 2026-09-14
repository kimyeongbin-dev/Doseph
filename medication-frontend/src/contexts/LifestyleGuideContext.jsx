'use client'

// LifestyleGuide 도메인 — TanStack Query adapter.
//
// 외부 API: guides, latestGuide, generateGuide, deleteGuide,
// revealMoreChallenges, refetchGuides, isLoading + GUIDE_TERMINAL_ERROR_MESSAGES
// + isError / error / isRefetching (조회 실패 표면화, 후속 큐 1-d).
//
// 변경 핵심:
// - GET /lifestyle-guides/latest 호출 폐기 — 가이드 0건일 때 매번 404 가 떴던
//   원인. list endpoint 가 newest-first 정렬이라 latestGuide = list[0] 으로 derive.
// - cross-cascade 는 mutation 의 onSuccess 안에서 invalidate.

import { createContext, useCallback, useContext, useMemo, useRef } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import api from '@/lib/api'
import { streamSSE } from '@/lib/sseClient'
import { useProfile } from '@/contexts/ProfileContext'
import { qk } from '@/queries/keys'

const LifestyleGuideContext = createContext(null)

const GUIDE_TERMINAL_ERROR_MESSAGES = {
  no_active_meds: '활성 약물이 없어 가이드를 만들 수 없어요. 복약 등록 후 다시 시도해주세요.',
  failed: '가이드 생성 중 오류가 발생했어요. 잠시 후 다시 시도해주세요.',
}

// SSE 자동 재연결 wrapper — terminal 까지 status update 를 yield.
async function* watchGuideStatus(guideId, signal) {
  while (true) {
    let timedOut = false
    for await (const ev of streamSSE(`/api/v1/lifestyle-guides/${guideId}/stream`, { signal })) {
      if (ev.event === 'update') yield ev.data
      else if (ev.event === 'timeout') {
        timedOut = true
        break
      } else if (ev.event === 'error') {
        throw new Error(ev.data?.detail || 'sse error')
      }
    }
    if (!timedOut) return
  }
}

export function LifestyleGuideProvider({ children }) {
  const { selectedProfileId } = useProfile()
  const qc = useQueryClient()

  // 사용자가 생성 중인 가이드를 직접 삭제한 경우 SSE 의 "Guide not found" 를 silent
  // 처리하기 위한 ref.
  const cancelledGuideIds = useRef(new Set())

  // ── 1) list query (latest 는 derived) ────────────────────────────
  const listQuery = useQuery({
    queryKey: qk.lifestyleGuides.list(selectedProfileId),
    enabled: !!selectedProfileId,
    queryFn: async () => {
      const { data } = await api.get(
        `/api/v1/lifestyle-guides?profile_id=${selectedProfileId}`,
      )
      return data || []
    },
  })
  // `data || []` 를 그대로 쓰면 data 가 undefined 인 구간(로딩·에러)에서 매 렌더
  // 새 배열이 만들어져, 아래 컨텍스트 value 의 useMemo 가 깨지고 모든 소비자가 리렌더된다.
  const guides = useMemo(() => listQuery.data || [], [listQuery.data])
  const isLoading = listQuery.isLoading
  // 조회 실패 전파 — 가이드는 평소에도 0건일 수 있는 도메인이라, 이 값이 없으면
  // 실패와 "아직 가이드가 없음"이 영원히 같은 화면이 된다.
  const isError = listQuery.isError
  const error = listQuery.error
  const isRefetching = listQuery.isFetching
  // newest-first 정렬이라 [0] = latest. 별 GET /latest 호출 불필요.
  const latestGuide = guides[0] || null

  // ── 2) generate (RQ + SSE) ───────────────────────────────────────
  const generateMutation = useMutation({
    mutationFn: async ({ profileId, prescriptionGroupId, signal }) => {
      if (!prescriptionGroupId) {
        throw new Error('처방전을 먼저 선택해주세요.')
      }
      const params = new URLSearchParams({
        profile_id: profileId,
        prescription_group_id: prescriptionGroupId,
      })
      const enqueueRes = await api.post(
        `/api/v1/lifestyle-guides/generate?${params.toString()}`,
        null,
      )
      const pendingId = enqueueRes.data.id

      // dedupe hit — BE 가 같은 fingerprint ready 가이드 즉시 반환.
      if (enqueueRes.data.status === 'ready') {
        const { data: ready } = await api.get(`/api/v1/lifestyle-guides/${pendingId}`)
        ready.deduped = true
        return ready
      }

      // pending placeholder — list cache 에 즉시 prepend (스켈레톤 렌더 유도).
      const pendingGuide = {
        id: pendingId,
        profile_id: profileId,
        status: 'pending',
        content: {},
        medication_snapshot: [],
        created_at: new Date().toISOString(),
        processed_at: null,
      }
      qc.setQueryData(qk.lifestyleGuides.list(profileId), (prev = []) => [
        pendingGuide,
        ...prev,
      ])

      try {
        for await (const payload of watchGuideStatus(pendingId, signal)) {
          if (payload.status === 'ready') {
            // list 안의 placeholder 를 ready payload 로 교체.
            qc.setQueryData(qk.lifestyleGuides.list(profileId), (prev = []) =>
              prev.map((g) => (g.id === pendingId ? payload : g)),
            )
            return payload
          }
          if (payload.status in GUIDE_TERMINAL_ERROR_MESSAGES) {
            qc.setQueryData(qk.lifestyleGuides.list(profileId), (prev = []) =>
              prev.filter((g) => g.id !== pendingId),
            )
            const err = new Error(GUIDE_TERMINAL_ERROR_MESSAGES[payload.status])
            err.terminal_status = payload.status
            throw err
          }
        }
      } catch (err) {
        if (cancelledGuideIds.current.has(pendingId)) {
          cancelledGuideIds.current.delete(pendingId)
          return null
        }
        qc.setQueryData(qk.lifestyleGuides.list(profileId), (prev = []) =>
          prev.filter((g) => g.id !== pendingId),
        )
        throw err
      }
      // SSE 가 ready 없이 종료 — placeholder 정리.
      qc.setQueryData(qk.lifestyleGuides.list(profileId), (prev = []) =>
        prev.filter((g) => g.id !== pendingId),
      )
      throw new Error('가이드 생성이 완료되지 않았어요. 잠시 후 다시 시도해주세요.')
    },
    onSuccess: (ready, { profileId }) => {
      if (!ready) return
      // 가이드 챌린지가 함께 INSERT 됐으니 challenges 키 invalidate.
      qc.invalidateQueries({ queryKey: qk.lifestyleGuides.challenges(ready.id) })
      qc.invalidateQueries({ queryKey: qk.challenges.list(profileId) })
    },
  })

  // ── 3) delete ────────────────────────────────────────────────────
  const deleteMutation = useMutation({
    mutationFn: async (id) => {
      cancelledGuideIds.current.add(id)
      await api.delete(`/api/v1/lifestyle-guides/${id}`)
      return id
    },
    onSuccess: (id) => {
      qc.setQueryData(qk.lifestyleGuides.list(selectedProfileId), (prev = []) =>
        prev.filter((g) => g.id !== id),
      )
      qc.removeQueries({ queryKey: qk.lifestyleGuides.detail(id) })
      qc.removeQueries({ queryKey: qk.lifestyleGuides.challenges(id) })
      // 미시작 챌린지 soft delete + 활성/완료 보존 — challenge list 도 stale.
      qc.invalidateQueries({ queryKey: qk.challenges.all() })
    },
  })

  // ── 4) reveal more challenges (LLM 호출 X, +5) ───────────────────
  const revealMoreMutation = useMutation({
    mutationFn: async (guideId) => {
      const { data } = await api.post(
        `/api/v1/lifestyle-guides/${guideId}/reveal-more-challenges`,
      )
      return data
    },
    onSuccess: (updated) => {
      // 응답이 갱신된 가이드 — list 안 row 직접 patch.
      qc.setQueryData(qk.lifestyleGuides.list(selectedProfileId), (prev = []) =>
        prev.map((g) => (g.id === updated.id ? updated : g)),
      )
      qc.invalidateQueries({ queryKey: qk.lifestyleGuides.challenges(updated.id) })
      qc.invalidateQueries({ queryKey: qk.challenges.list(selectedProfileId) })
    },
  })

  // 외부 호환 API.
  const generateGuide = useCallback(
    (profileId, prescriptionGroupId, signal) =>
      generateMutation.mutateAsync({ profileId, prescriptionGroupId, signal }),
    [generateMutation],
  )
  const deleteGuide = useCallback((id) => deleteMutation.mutateAsync(id), [deleteMutation])
  const revealMoreChallenges = useCallback(
    (guideId) => revealMoreMutation.mutateAsync(guideId),
    [revealMoreMutation],
  )
  const refetchGuides = useCallback(() => listQuery.refetch(), [listQuery])

  const value = useMemo(
    () => ({
      guides,
      latestGuide,
      isLoading,
      isError,
      error,
      isRefetching,
      generateGuide,
      deleteGuide,
      refetchGuides,
      revealMoreChallenges,
    }),
    [
      guides,
      latestGuide,
      isLoading,
      isError,
      error,
      isRefetching,
      generateGuide,
      deleteGuide,
      refetchGuides,
      revealMoreChallenges,
    ],
  )

  return (
    <LifestyleGuideContext.Provider value={value}>{children}</LifestyleGuideContext.Provider>
  )
}

export function useLifestyleGuide() {
  const ctx = useContext(LifestyleGuideContext)
  if (!ctx) throw new Error('useLifestyleGuide must be used within LifestyleGuideProvider')
  return ctx
}

export { GUIDE_TERMINAL_ERROR_MESSAGES }
