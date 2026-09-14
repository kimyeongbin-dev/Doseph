'use client'

/**
 * PrescriptionGroupContext — TanStack Query adapter.
 *
 * 외부 API(usePrescriptionGroup): groups, groupsById, isLoading, sort/search/statusFilter,
 * setSort/setSearch/setStatusFilter, fetchGroupDetail, updateGroup,
 * markGroupCompleted, deleteGroup, refetchGroups + 정렬/탭 enums.
 *
 * 별도 export: **usePrescriptionGroupDetail(groupId)** — 상세 조회 전용 query hook.
 * 호출 페이지가 로딩/에러를 useState + useEffect 로 흉내 내지 않도록 쿼리 상태를
 * 그대로 넘긴다. detail 캐시를 읽는 관찰자들과 **같은 queryFn 을 공유**한다
 * (같은 queryKey 에 다른 fn 이 붙으면 등록 순서에 동작이 좌우되기 때문).
 *
 * 내부 변경:
 * - list/detail GET 을 useQuery 로 교체 — dedupe + staleTime 캐시.
 * - mutation (update/markCompleted/delete) 을 useMutation 으로 교체 —
 *   cross-cascade (가이드/챌린지) 는 onSuccess 에서 invalidate 한 줄로 처리.
 * - sort / statusFilter 는 client UI 상태라 그대로 useState.
 * - search 만 BE 처리 — query key 에 search 포함 → 자동 refetch.
 */

import { createContext, useCallback, useContext, useMemo, useState } from 'react'
import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'

import api from '@/lib/api'
import { useMedication } from '@/contexts/MedicationContext'
import { useProfile } from '@/contexts/ProfileContext'
import { qk, STALE } from '@/queries/keys'

// ── 처방전 상세 조회 fn (queryKey 공유자 전원이 같이 쓴다) ────────────
// 흐름: groupId -> GET /prescription-groups/{id} -> 상세 객체
// 같은 queryKey 에 여러 관찰자가 붙으면 나중에 등록된 쪽 queryFn 이 쓰이므로,
// cache-only 관찰자(groupsByIdQueries)와 실제 조회 hook 이 같은 fn 을 공유해야
// 등록 순서에 따라 동작이 달라지지 않는다.
async function fetchGroupDetailRequest(groupId) {
  const { data } = await api.get(`/api/v1/prescription-groups/${groupId}`)
  return data
}

// ── 처방전 상세 query hook ───────────────────────────────────────────
// 흐름: groupId -> useQuery(detail key) -> 캐시 히트면 즉시, 아니면 GET
// 호출 페이지가 로딩/에러를 useState + useEffect 로 흉내 내지 않도록 쿼리 상태를
// 그대로 넘긴다. 재시도 정책은 QueryProvider 기본값(4xx 즉시 실패)을 따른다.
export function usePrescriptionGroupDetail(groupId) {
  return useQuery({
    queryKey: qk.prescriptionGroups.detail(groupId),
    enabled: !!groupId,
    queryFn: () => fetchGroupDetailRequest(groupId),
    staleTime: STALE.prescriptionGroups,
  })
}

export const PRESCRIPTION_SORT = Object.freeze({
  DATE_DESC: 'date_desc',
  DATE_ASC: 'date_asc',
  HOSPITAL_ASC: 'hospital_asc',
  HOSPITAL_DESC: 'hospital_desc',
})

export const PRESCRIPTION_STATUS = Object.freeze({
  ALL: 'all',
  ACTIVE: 'active',
  COMPLETED: 'completed',
})

const PrescriptionGroupContext = createContext(null)

export function PrescriptionGroupProvider({ children }) {
  const { selectedProfileId } = useProfile()
  // Medication store 의 active 약 변화를 listen — 약 복용 처리/마감 시 그룹의
  // has_active_medication 라벨 stale 방지. mutation 으로 active 변경 시 우리가
  // 직접 invalidate 하지 않아도 활성 약 수가 바뀌면 list query 도 invalidate.
  const { medications } = useMedication()
  const qc = useQueryClient()

  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState(PRESCRIPTION_STATUS.ALL)
  // 탭별 sort 분리 — 사용자가 "복용 중" 은 최신순, "복용 완료" 는 병원순으로
  // 보고 싶다는 흐름. 탭 전환 시 그 탭의 마지막 sort 가 복원.
  const [sortByTab, setSortByTab] = useState({
    [PRESCRIPTION_STATUS.ALL]: PRESCRIPTION_SORT.DATE_DESC,
    [PRESCRIPTION_STATUS.ACTIVE]: PRESCRIPTION_SORT.DATE_DESC,
    [PRESCRIPTION_STATUS.COMPLETED]: PRESCRIPTION_SORT.DATE_DESC,
  })
  const sort = sortByTab[statusFilter]
  const setSort = useCallback(
    (next) => setSortByTab((prev) => ({ ...prev, [statusFilter]: next })),
    [statusFilter],
  )

  // ── list query (search 만 BE) ─────────────────────────────────────
  const listQuery = useQuery({
    queryKey: qk.prescriptionGroups.list(selectedProfileId, search.trim()),
    enabled: !!selectedProfileId,
    queryFn: async () => {
      const params = new URLSearchParams({ profile_id: selectedProfileId })
      if (search.trim()) params.set('search', search.trim())
      const { data } = await api.get(`/api/v1/prescription-groups?${params.toString()}`)
      return data || []
    },
  })
  // `data || []` 를 그대로 쓰면 data 가 undefined 인 구간(로딩·에러)에서 매 렌더
  // 새 배열이 만들어져 아래 sort/filter useMemo 사슬이 통째로 재계산된다.
  const _groupsRaw = useMemo(() => listQuery.data || [], [listQuery.data])
  const isLoading = listQuery.isLoading

  // medication active count 변화 시 list query invalidate — 그룹 라벨 동기화.
  const activeCount = medications.filter((m) => m.is_active).length
  const [lastActiveCount, setLastActiveCount] = useState(activeCount)
  if (activeCount !== lastActiveCount) {
    setLastActiveCount(activeCount)
    if (selectedProfileId) {
      qc.invalidateQueries({ queryKey: qk.prescriptionGroups.all() })
    }
  }

  // ── 클라이언트 sort ──────────────────────────────────────────────
  // 병원 정렬에선 NULL 그룹을 항상 맨 위로 partition.
  const sortedRaw = useMemo(() => {
    const result = [..._groupsRaw]
    const sortByDate = (asc) =>
      result.sort((a, b) => {
        const av = a.dispensed_date || ''
        const bv = b.dispensed_date || ''
        return asc ? av.localeCompare(bv) : bv.localeCompare(av)
      })
    const sortByHospital = (asc) =>
      result.sort((a, b) => {
        if (!a.hospital_name && !b.hospital_name) return 0
        if (!a.hospital_name) return -1
        if (!b.hospital_name) return 1
        const cmp = a.hospital_name.localeCompare(b.hospital_name, 'ko')
        return asc ? cmp : -cmp
      })
    if (sort === PRESCRIPTION_SORT.DATE_DESC) sortByDate(false)
    else if (sort === PRESCRIPTION_SORT.DATE_ASC) sortByDate(true)
    else if (sort === PRESCRIPTION_SORT.HOSPITAL_ASC) sortByHospital(true)
    else if (sort === PRESCRIPTION_SORT.HOSPITAL_DESC) sortByHospital(false)
    return result
  }, [_groupsRaw, sort])

  const groups = useMemo(() => {
    if (statusFilter === PRESCRIPTION_STATUS.ALL) return sortedRaw
    if (statusFilter === PRESCRIPTION_STATUS.ACTIVE) {
      return sortedRaw.filter((g) => g.has_active_medication)
    }
    return sortedRaw.filter((g) => !g.has_active_medication)
  }, [sortedRaw, statusFilter])

  const refetchGroups = useCallback(() => listQuery.refetch(), [listQuery])

  // ── detail query ─────────────────────────────────────────────────
  // useQueries 로 cache-only access — 호출자가 useQuery 로 직접 받도록 helper 도 노출.
  const fetchGroupDetail = useCallback(
    async (groupId, { forceRefresh = false } = {}) => {
      if (!groupId) return null
      const cached = qc.getQueryData(qk.prescriptionGroups.detail(groupId))
      if (cached && !forceRefresh) {
        // 백그라운드 refresh — staleTime 안이면 noop 에 가까움.
        qc.invalidateQueries({ queryKey: qk.prescriptionGroups.detail(groupId) })
        return cached
      }
      const data = await fetchGroupDetailRequest(groupId)
      qc.setQueryData(qk.prescriptionGroups.detail(groupId), data)
      return data
    },
    [qc],
  )

  // ── mutations — cross-cascade 까지 invalidate ────────────────────
  const updateMutation = useMutation({
    mutationFn: async ({ groupId, patch }) => {
      const { data } = await api.patch(`/api/v1/prescription-groups/${groupId}`, patch)
      return data
    },
    onSuccess: (data, { groupId }) => {
      qc.setQueryData(qk.prescriptionGroups.detail(groupId), data)
      qc.invalidateQueries({ queryKey: qk.prescriptionGroups.all() })
    },
  })

  const completeMutation = useMutation({
    mutationFn: async (groupId) => {
      const { data } = await api.patch(`/api/v1/prescription-groups/${groupId}/complete`)
      return data
    },
    onSuccess: (data, groupId) => {
      qc.setQueryData(qk.prescriptionGroups.detail(groupId), data)
      qc.invalidateQueries({ queryKey: qk.prescriptionGroups.all() })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: async (groupId) => {
      await api.delete(`/api/v1/prescription-groups/${groupId}`)
      return groupId
    },
    onSuccess: (groupId) => {
      // BE cascade: 그룹 + medication + 그 프로필 active 가이드 + 미시작 챌린지.
      // → 자기 + 가이드 + 챌린지 도메인 모두 invalidate.
      qc.removeQueries({ queryKey: qk.prescriptionGroups.detail(groupId) })
      qc.invalidateQueries({ queryKey: qk.prescriptionGroups.all() })
      qc.invalidateQueries({ queryKey: qk.lifestyleGuides.all() })
      qc.invalidateQueries({ queryKey: qk.challenges.all() })
      qc.invalidateQueries({ queryKey: qk.medications.all() }) // ← [추가] 처방전 삭제 시 약 목록도 즉시 갱신
    },
  })

  // 외부 호환 API.
  const updateGroup = useCallback(
    (groupId, patch) => updateMutation.mutateAsync({ groupId, patch }),
    [updateMutation],
  )
  const markGroupCompleted = useCallback(
    (groupId) => completeMutation.mutateAsync(groupId),
    [completeMutation],
  )
  const deleteGroup = useCallback(
    (groupId) => deleteMutation.mutateAsync(groupId),
    [deleteMutation],
  )

  // 외부 컴포넌트가 cache 의 detail map 을 읽고 싶어할 때를 위한 SSOT.
  // useQueries 로 매 render 마다 cache 스냅샷을 받음 — staleTime 안이면 GET 0회.
  const groupsByIdQueries = useQueries({
    queries: _groupsRaw.map((g) => ({
      queryKey: qk.prescriptionGroups.detail(g.id),
      // detail 은 명시적 호출 시에만 fetch — 본 useQueries 는 cache 읽기 전용
      // (enabled:false 라 여기서 fn 이 돌지는 않지만, 같은 key 공유자와 fn 을
      //  일치시켜 등록 순서에 따른 동작 차이를 없앤다).
      queryFn: () => fetchGroupDetailRequest(g.id),
      enabled: false,
      // 캐시 미스 시 throw 방지.
      retry: false,
    })),
  })
  const groupsById = useMemo(() => {
    const m = {}
    for (const q of groupsByIdQueries) {
      const d = q.data
      if (d?.id) m[d.id] = d
    }
    return m
  }, [groupsByIdQueries])

  const value = useMemo(
    () => ({
      groups,
      groupsById,
      isLoading,
      sort,
      search,
      statusFilter,
      setSort,
      setSearch,
      setStatusFilter,
      fetchGroupDetail,
      updateGroup,
      markGroupCompleted,
      deleteGroup,
      refetchGroups,
    }),
    [
      groups,
      groupsById,
      isLoading,
      sort,
      setSort,
      search,
      statusFilter,
      fetchGroupDetail,
      updateGroup,
      markGroupCompleted,
      deleteGroup,
      refetchGroups,
    ],
  )

  return <PrescriptionGroupContext.Provider value={value}>{children}</PrescriptionGroupContext.Provider>
}

export function usePrescriptionGroup() {
  const ctx = useContext(PrescriptionGroupContext)
  if (!ctx) throw new Error('usePrescriptionGroup must be used within PrescriptionGroupProvider')
  return ctx
}
