// 라이프스타일 가이드 도메인 — list / detail / challenges / mutations + SSE 흐름.
//
// 정책:
// - latest 는 별 endpoint (/latest 가이드 없을 때 404) 대신 list 결과의 [0] 으로 derive.
//   newest-first 정렬이라 OK. → /latest 호출 폐기 = 404 noise 제거.
// - generateGuide 는 SSE 진행 중 store 를 직접 갱신하지 않고, ready 도달 시
//   list 캐시를 invalidate 해 다음 read 에서 신선한 list 를 받는다.
// - revealMore / delete 도 onSuccess 에서 list/detail/challenges 키 invalidate.

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import api from '@/lib/api'
import { streamSSE } from '@/lib/sseClient'
import { qk } from '@/queries/keys'

export const GUIDE_TERMINAL_ERROR_MESSAGES = {
  no_active_meds: '활성 약물이 없어 가이드를 만들 수 없어요. 복약 등록 후 다시 시도해주세요.',
  failed: '가이드 생성 중 오류가 발생했어요. 잠시 후 다시 시도해주세요.',
}

export function useLifestyleGuides(profileId) {
  return useQuery({
    queryKey: qk.lifestyleGuides.list(profileId),
    enabled: !!profileId,
    queryFn: async () => {
      const { data } = await api.get(`/api/v1/lifestyle-guides?profile_id=${profileId}`)
      return data || []
    },
  })
}

export function useGuideChallenges(guideId) {
  return useQuery({
    queryKey: qk.lifestyleGuides.challenges(guideId),
    enabled: !!guideId,
    queryFn: async () => {
      const { data } = await api.get(`/api/v1/lifestyle-guides/${guideId}/challenges`)
      return data || []
    },
  })
}

// 가이드 생성 mutation — 처방전 그룹 단위 + SSE 진행.
// 호출자가 abort signal 을 줘서 페이지 unmount 시 SSE 끊을 수 있게 한다.
export function useGenerateLifestyleGuide() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ profileId, prescriptionGroupId, signal }) => {
      if (!profileId) throw new Error('프로필이 없습니다.')
      if (!prescriptionGroupId) throw new Error('처방전을 먼저 선택해주세요.')

      const params = new URLSearchParams({
        profile_id: profileId,
        prescription_group_id: prescriptionGroupId,
      })
      const enqueueRes = await api.post(
        `/api/v1/lifestyle-guides/generate?${params.toString()}`,
        null,
      )
      const pendingId = enqueueRes.data.id

      // dedupe hit — BE 가 같은 fingerprint 의 ready 가이드를 즉시 반환.
      if (enqueueRes.data.status === 'ready') {
        const { data: ready } = await api.get(`/api/v1/lifestyle-guides/${pendingId}`)
        ready.deduped = true
        return ready
      }

      // SSE wait — ready / terminal 까지 polling.
      for await (const ev of _watchGuideStatus(pendingId, signal)) {
        if (ev.status === 'ready') return ev
        if (ev.status in GUIDE_TERMINAL_ERROR_MESSAGES) {
          const err = new Error(GUIDE_TERMINAL_ERROR_MESSAGES[ev.status])
          err.terminal_status = ev.status
          throw err
        }
      }
      throw new Error('가이드 생성이 완료되지 않았어요. 잠시 후 다시 시도해주세요.')
    },
    onSuccess: (ready, { profileId }) => {
      // ready 가이드가 list 에 들어가야 하니 list invalidate.
      // 챌린지 캐시도 영향 (가이드와 함께 BE 가 INSERT) 이므로 함께 invalidate.
      qc.invalidateQueries({ queryKey: qk.lifestyleGuides.list(profileId) })
      qc.invalidateQueries({ queryKey: qk.challenges.all() })
      qc.invalidateQueries({ queryKey: qk.lifestyleGuides.challenges(ready.id) })
    },
  })
}

// "추천 챌린지 더 보기" — 단일 UPDATE +5, LLM 호출 X.
export function useRevealMoreChallenges() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (guideId) => {
      const { data } = await api.post(`/api/v1/lifestyle-guides/${guideId}/reveal-more-challenges`)
      return data
    },
    onSuccess: (updated, guideId) => {
      // 응답이 가이드 그 자체라 detail 직접 갱신 + list/challenges 무효화로 stale 제거.
      qc.setQueryData(qk.lifestyleGuides.detail(guideId), updated)
      qc.invalidateQueries({ queryKey: qk.lifestyleGuides.all() })
      qc.invalidateQueries({ queryKey: qk.challenges.all() })
    },
  })
}

export function useDeleteLifestyleGuide() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (guideId) => {
      await api.delete(`/api/v1/lifestyle-guides/${guideId}`)
      return guideId
    },
    onSuccess: (guideId) => {
      qc.removeQueries({ queryKey: qk.lifestyleGuides.detail(guideId) })
      qc.removeQueries({ queryKey: qk.lifestyleGuides.challenges(guideId) })
      qc.invalidateQueries({ queryKey: qk.lifestyleGuides.all() })
      // 가이드 삭제 시 미시작 챌린지 soft delete + 활성/완료는 guide_id=None 분리 →
      // 챌린지 list 도 stale.
      qc.invalidateQueries({ queryKey: qk.challenges.all() })
    },
  })
}

// SSE 자동 재연결 wrapper — terminal 까지 status update 를 yield.
async function* _watchGuideStatus(guideId, signal) {
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
