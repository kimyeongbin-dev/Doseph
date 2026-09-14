// 복약 체크 기록(intake-logs) 도메인 — 오늘 기록 / 연속 복약(streak).
//
// 왜 훅으로 모으나: 같은 queryKey 를 여러 화면이 관찰할 때 **각자 다른 queryFn 을
// 넘기면 마지막에 등록된 fn 이 쓰여** 렌더 순서에 동작이 좌우된다(처방전 그룹 상세에서
// 실제로 겪은 함정). 키와 fn 을 한 곳에 묶어 그 비결정성을 원천 제거한다.

import { useCallback } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'

import api from '@/lib/api'
import { qk, STALE } from '@/queries/keys'

// 로컬 기준 오늘 날짜(YYYY-MM-DD). 키와 요청 파라미터에 함께 쓴다.
export function getTodayKey() {
  return new Date().toISOString().split('T')[0]
}

// ── 오늘 복약 기록 조회 ──────────────────────────────────────────────
// 흐름: profileId 확정 -> 오늘 날짜로 조회 -> 캐시 보관 -> 체크/해제 후 invalidate
export function useTodayIntakeLogs(profileId) {
  const today = getTodayKey()
  return useQuery({
    queryKey: qk.intakeLogs.byDate(profileId, today),
    enabled: !!profileId,
    staleTime: STALE.intakeLogs,
    queryFn: async () => {
      const { data } = await api.get('/api/v1/intake-logs', {
        params: { profile_id: profileId, target_date: today },
      })
      return data || []
    },
  })
}

// ── 연속 복약(streak) 조회 ───────────────────────────────────────────
// 흐름: profileId 확정 -> /intake-logs/streak 조회 -> streak_days 숫자만 노출
export function useIntakeStreak(profileId) {
  return useQuery({
    queryKey: qk.intakeLogs.streak(profileId),
    enabled: !!profileId,
    staleTime: STALE.intakeLogs,
    queryFn: async () => {
      const { data } = await api.get('/api/v1/intake-logs/streak', {
        params: { profile_id: profileId },
      })
      return data?.streak_days ?? 0
    },
  })
}

// ── 오늘 기록 무효화 헬퍼 ────────────────────────────────────────────
// 흐름: 체크/해제 후 호출 -> 오늘 기록 키 무효화 -> 관찰 중인 화면이 재조회
// 참조가 고정돼야 호출 측 useCallback 의존성을 흔들지 않는다.
// (streak 은 여기서 건드리지 않는다 — 기존 동작 유지. 오늘 첫 복약이 연속 일수를
//  바꾸므로 함께 무효화하는 편이 더 정확하지만, 동작 변경이라 이 리팩터에 섞지 않는다.)
export function useInvalidateTodayIntakeLogs(profileId) {
  const qc = useQueryClient()
  const today = getTodayKey()
  return useCallback(
    () => qc.invalidateQueries({ queryKey: qk.intakeLogs.byDate(profileId, today) }),
    [qc, profileId, today],
  )
}
