'use client'

// Challenge 도메인 — TanStack Query adapter.
//
// 외부 API 는 기존 그대로 유지 (challenges, activeChallenges, …, refetchChallenges,
// useChallengeStart, useChallengeCheck). 내부적으로 useQuery + useMutation 으로 교체해
// dedupe + invalidate 자동화. cross-cascade (가이드/처방전 mutation) 가 자기 손으로
// challenges 키를 invalidate 하면 본 Provider 가 자동 refetch.

import { createContext, useCallback, useContext, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'

import api, { showError } from '@/lib/api'
import { useProfile } from '@/contexts/ProfileContext'
import { qk } from '@/queries/keys'

const ChallengeContext = createContext(null)

export function ChallengeProvider({ children }) {
  const { selectedProfileId } = useProfile()
  const qc = useQueryClient()

  // ── 1) list query ─────────────────────────────────────────────────
  const listQuery = useQuery({
    queryKey: qk.challenges.list(selectedProfileId),
    enabled: !!selectedProfileId,
    queryFn: async () => {
      const { data } = await api.get(
        `/api/v1/challenges?profile_id=${selectedProfileId}`,
      )
      return data || []
    },
  })
  const challenges = listQuery.data || []
  const isLoading = listQuery.isLoading

  // ── 2) mutations ──────────────────────────────────────────────────
  // 모두 응답으로 cache 직접 patch — 화면 즉시 반영 + invalidate 로 stale 제거.
  const startMutation = useMutation({
    mutationFn: async ({ id, difficulty, target_days }) => {
      const payload = {}
      if (difficulty !== undefined) payload.difficulty = difficulty
      if (target_days !== undefined) payload.target_days = target_days
      const url = `/api/v1/challenges/${id}/start`
      const { data } =
        Object.keys(payload).length > 0
          ? await api.patch(url, payload)
          : await api.patch(`/api/v1/challenges/${id}`, { is_active: true })
      return data
    },
    onSuccess: (updated, { id }) => {
      qc.setQueryData(qk.challenges.list(selectedProfileId), (prev = []) =>
        prev.map((c) => (c.id === id ? { ...c, ...updated } : c)),
      )
    },
  })

  const updateMutation = useMutation({
    mutationFn: async ({ id, patch }) => {
      const { data } = await api.patch(`/api/v1/challenges/${id}`, patch)
      return data
    },
    onSuccess: (updated, { id }) => {
      qc.setQueryData(qk.challenges.list(selectedProfileId), (prev = []) =>
        prev.map((c) => (c.id === id ? { ...c, ...updated } : c)),
      )
    },
  })

  const deleteMutation = useMutation({
    mutationFn: async (id) => {
      await api.delete(`/api/v1/challenges/${id}`)
      return id
    },
    onSuccess: (id) => {
      qc.setQueryData(qk.challenges.list(selectedProfileId), (prev = []) =>
        prev.filter((c) => c.id !== id),
      )
    },
  })

  // 오늘 완료 체크 — 완료 날짜·진행 상태는 서버가 단독 결정한다 (POST /check).
  // 클라는 트리거만 보낸다 (완료/스트릭 위조 방지).
  const checkMutation = useMutation({
    mutationFn: async (id) => {
      const { data } = await api.post(`/api/v1/challenges/${id}/check`)
      return data
    },
    onSuccess: (updated, id) => {
      qc.setQueryData(qk.challenges.list(selectedProfileId), (prev = []) =>
        prev.map((c) => (c.id === id ? { ...c, ...updated } : c)),
      )
    },
  })

  // 외부 호환 API — 기존 시그니처 그대로 (await 가능한 promise 반환).
  const startChallenge = useCallback(
    (id, opts) => startMutation.mutateAsync({ id, ...(opts || {}) }),
    [startMutation],
  )
  const updateChallenge = useCallback(
    (id, patch) => updateMutation.mutateAsync({ id, patch }),
    [updateMutation],
  )
  const deleteChallenge = useCallback((id) => deleteMutation.mutateAsync(id), [deleteMutation])
  const checkChallenge = useCallback((id) => checkMutation.mutateAsync(id), [checkMutation])
  // 가이드 mutation 후 챌린지 추가 INSERT 를 store 에 즉시 union 하던 helper —
  // 이제는 가이드 mutation 의 onSuccess 에서 challenges 키를 invalidate 하므로 별 호출 불요.
  // 외부에서 직접 union 이 필요한 흐름이 남아있을 수 있으니 호환 stub 으로 유지.
  const appendChallenges = useCallback(
    (incoming) => {
      if (!incoming || incoming.length === 0) return
      qc.setQueryData(qk.challenges.list(selectedProfileId), (prev = []) => {
        const byId = new Map(prev.map((c) => [c.id, c]))
        for (const c of incoming) byId.set(c.id, c)
        return Array.from(byId.values())
      })
    },
    [qc, selectedProfileId],
  )
  const refetchChallenges = useCallback(() => listQuery.refetch(), [listQuery])

  // ── 3) computed selectors ─────────────────────────────────────────
  const activeChallenges = challenges.filter(
    (c) => c.challenge_status === 'IN_PROGRESS' && c.is_active,
  )
  const completedChallenges = challenges.filter((c) => c.challenge_status === 'COMPLETED')
  const unstartedByGuide = (guideId) =>
    challenges.filter(
      (c) => c.guide_id === guideId && !c.is_active && c.challenge_status !== 'DELETED',
    )
  const challengesByGuide = (guideId) => challenges.filter((c) => c.guide_id === guideId)

  return (
    <ChallengeContext.Provider
      value={{
        challenges,
        activeChallenges,
        completedChallenges,
        unstartedByGuide,
        challengesByGuide,
        isLoading,
        startChallenge,
        updateChallenge,
        deleteChallenge,
        checkChallenge,
        appendChallenges,
        refetchChallenges,
      }}
    >
      {children}
    </ChallengeContext.Provider>
  )
}

export function useChallenge() {
  const ctx = useContext(ChallengeContext)
  if (!ctx) throw new Error('useChallenge must be used within ChallengeProvider')
  return ctx
}

// ── 챌린지 시작 단일 정책 (모달 흐름) ────────────────────────────────
export function useChallengeStart() {
  const { startChallenge } = useChallenge()
  const [startTarget, setStartTarget] = useState(null)
  const [isStarting, setIsStarting] = useState(false)

  const requestStart = useCallback(
    (challenge) => {
      if (isStarting) return
      setStartTarget(challenge)
    },
    [isStarting],
  )

  const cancelStart = useCallback(() => {
    if (isStarting) return
    setStartTarget(null)
  }, [isStarting])

  const confirmStart = useCallback(
    async (difficulty, targetDays) => {
      if (!startTarget || isStarting) return null
      setIsStarting(true)
      try {
        const updated = await startChallenge(startTarget.id, {
          difficulty,
          target_days: targetDays,
        })
        setStartTarget(null)
        return updated
      } finally {
        setIsStarting(false)
      }
    },
    [startTarget, isStarting, startChallenge],
  )

  return { startTarget, isStarting, requestStart, cancelStart, confirmStart }
}

// ── 오늘 완료 체크 단일 정책 ─────────────────────────────────────────
export function useChallengeCheck() {
  const { checkChallenge } = useChallenge()
  const [checkingId, setCheckingId] = useState(null)

  const checkToday = useCallback(
    async (challenge) => {
      if (checkingId) return null
      const today = new Date().toISOString().split('T')[0]
      const alreadyChecked = challenge.completed_dates?.some(
        (d) => (typeof d === 'string' ? d : d.toISOString?.().split('T')[0]) === today,
      )
      if (alreadyChecked) {
        showError('오늘은 이미 체크했습니다!')
        return null
      }
      setCheckingId(challenge.id)
      try {
        // 완료 날짜·진행 상태는 서버가 단독 결정한다 (POST /check). 클라는 트리거만.
        const updated = await checkChallenge(challenge.id)
        if (updated.challenge_status === 'COMPLETED') {
          toast.success('챌린지를 완료했습니다! 수고하셨어요.')
        }
        return updated
      } catch {
        showError('체크에 실패했습니다.')
        return null
      } finally {
        setCheckingId(null)
      }
    },
    [checkingId, checkChallenge],
  )

  return { checkingId, checkToday }
}
