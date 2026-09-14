// 하루 증상 기록(daily-logs) 도메인 — 오늘 기록 조회 / 갱신.
//
// 조회 결과는 목록이지만 화면이 쓰는 건 "오늘 기록 1건"이라, 훅에서 오늘 날짜로
// 걸러 그 형태로 노출한다(각 화면이 같은 필터를 반복 구현하지 않게).

import { useCallback } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'

import api from '@/lib/api'
import { qk, STALE } from '@/queries/keys'

// ── 오늘 증상 기록 조회 ──────────────────────────────────────────────
// 흐름: profileId 확정 -> days=1 로 조회 -> 오늘 날짜 기록만 선별
// days=1 이어도 경계 시각에 어제 기록이 섞일 수 있어 날짜로 한 번 더 거른다.
export function useTodaySymptomLog(profileId) {
  return useQuery({
    queryKey: qk.dailyLogs.list(profileId),
    enabled: !!profileId,
    staleTime: STALE.dailyLogs,
    queryFn: async () => {
      const { data } = await api.get('/api/v1/daily-logs', {
        params: { profile_id: profileId, days: 1 },
      })
      const today = new Date().toISOString().split('T')[0]
      const todayLog = (data || []).find((log) => log.log_date === today)
      return { symptoms: todayLog?.symptoms ?? [], note: todayLog?.note ?? '' }
    },
  })
}

// ── 오늘 증상 기록 무효화 ────────────────────────────────────────────
// 흐름: 증상 저장 후 호출 -> 캐시 무효화 -> 관찰 중인 화면이 재조회
// 참조가 고정돼야 호출 측 의존성을 흔들지 않는다.
export function useInvalidateTodaySymptomLog(profileId) {
  const qc = useQueryClient()
  return useCallback(
    () => qc.invalidateQueries({ queryKey: qk.dailyLogs.list(profileId) }),
    [qc, profileId],
  )
}
