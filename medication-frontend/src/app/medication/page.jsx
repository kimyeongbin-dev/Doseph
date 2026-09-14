'use client'

// /medication (복용 가이드) — 처방전 카드 list
//
// 흐름: 사용자 -> 처방전 카드 list (날짜/진료과 정렬 + 약품 검색 + 복용 중/완료 탭)
//       -> 카드 클릭 시 /medication/group?group_id= drill-down 으로 이동
//       -> 그 페이지에서 약품 클릭 시 /medication/detail?id= 약품 상세 페이지
//
// 정렬 / 검색 / 탭 셋 다 독립적이며 동시 사용 가능. 상태는 PrescriptionGroupContext 가 단일 진실.

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { Search, X, ChevronRight, Plus, Building2, Calendar, Hospital, Trash2 } from 'lucide-react'
import toast from 'react-hot-toast'

import BottomNav from '@/components/layout/BottomNav'
import EmptyState from '@/components/common/EmptyState'
import { showError } from '@/lib/api'
import { useConfirm } from '@/components/common/ConfirmDialog'
import {
  PRESCRIPTION_SORT,
  PRESCRIPTION_STATUS,
  usePrescriptionGroup,
} from '@/contexts/PrescriptionGroupContext'
import { useProfile } from '@/contexts/ProfileContext'

const SORT_LABELS = {
  [PRESCRIPTION_SORT.DATE_DESC]: '날짜: 최신 먼저',
  [PRESCRIPTION_SORT.DATE_ASC]: '날짜: 오래된 먼저',
  [PRESCRIPTION_SORT.HOSPITAL_ASC]: '병원: ㄱ → ㅎ',
  [PRESCRIPTION_SORT.HOSPITAL_DESC]: '병원: ㅎ → ㄱ',
}

const STATUS_TABS = [
  { key: PRESCRIPTION_STATUS.ALL, label: '전체' },
  { key: PRESCRIPTION_STATUS.ACTIVE, label: '복용 중' },
  { key: PRESCRIPTION_STATUS.COMPLETED, label: '복용 완료' },
]

function formatDate(isoStr) {
  if (!isoStr) return '날짜 미상'
  const [yyyy, mm, dd] = isoStr.split('-')
  return `${yyyy}년 ${parseInt(mm, 10)}월 ${parseInt(dd, 10)}일`
}

function GroupCardSkeleton() {
  return (
    <div className="bg-surface rounded-2xl border border-line p-4 animate-pulse space-y-3">
      <div className="h-4 bg-surface-2 rounded w-32" />
      <div className="h-3 bg-surface-2 rounded w-24" />
      <div className="h-8 bg-surface-2 rounded w-full" />
    </div>
  )
}

function PrescriptionCard({ group, onClick, onDelete, isDeleting }) {
  const dateLabel = formatDate(group.dispensed_date)
  const hospital = group.hospital_name || '병원 미상'
  const dept = group.department || '진료과 미상'
  const statusLabel = group.has_active_medication ? '복용 중' : '복용 완료'
  const statusStyle = group.has_active_medication
    ? 'bg-blue-50 text-blue-600 border-blue-100'
    : 'bg-surface-2 text-muted border-line'

  // 카드 전체를 <button> 으로 두면 그 안에 삭제 <button> 을 넣을 수 없다 (nested button
  // HTML 위반). 카드 wrapper 는 div role="button" + keyboard handler 로 대체.
  const handleKeyDown = (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      onClick()
    }
  }

  return (
    <div
      role="button"
      tabIndex={0}
      data-testid="prescription-card"
      onClick={onClick}
      onKeyDown={handleKeyDown}
      aria-busy={isDeleting || undefined}
      className={`w-full text-left bg-surface rounded-2xl border border-line hover:border-line transition-colors p-4 flex items-center gap-3 cursor-pointer ${
        isDeleting ? 'opacity-50 pointer-events-none' : ''
      }`}
    >
      <div className="flex-1 min-w-0 space-y-1.5">
        <div className="flex items-center gap-2 text-xs">
          <Calendar size={14} className="text-muted shrink-0" />
          <span className="font-bold text-ink">{dateLabel}</span>
        </div>
        <div className="flex items-center gap-2 text-xs text-ink">
          <Hospital size={14} className="shrink-0 text-muted" />
          <span className={group.hospital_name ? 'font-bold' : 'text-muted'}>{hospital}</span>
        </div>
        <div className="flex items-center gap-2 text-xs text-muted">
          <Building2 size={14} className="shrink-0" />
          <span>{dept}</span>
        </div>
        <div className="flex items-center gap-2 pt-1">
          <span className={`text-[11px] font-bold px-2 py-0.5 rounded-full border ${statusStyle}`}>{statusLabel}</span>
          <span className="text-[11px] text-muted">
            {group.has_active_medication
              ? `복용 중 ${group.active_medications_count ?? 0}개 / 총 ${group.medications_count}개`
              : `약 ${group.medications_count}개`}
          </span>
        </div>
      </div>

      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation()
          onDelete()
        }}
        disabled={isDeleting}
        title="처방전 삭제"
        aria-label="처방전 삭제"
        className={`shrink-0 w-9 h-9 flex items-center justify-center rounded-lg transition-colors ${
          isDeleting
            ? 'text-muted cursor-wait'
            : 'text-muted hover:text-red-500 hover:bg-red-50 cursor-pointer'
        }`}
      >
        <Trash2 size={16} />
      </button>
      <ChevronRight size={18} className="text-muted shrink-0" />
    </div>
  )
}

export default function MedicationPage() {
  const router = useRouter()
  const confirm = useConfirm()
  const { selectedProfileId } = useProfile()
  const {
    groups,
    isLoading,
    sort,
    search,
    statusFilter,
    setSort,
    setSearch,
    setStatusFilter,
    refetchGroups,
    deleteGroup,
  } = usePrescriptionGroup()
  // 처방전 그룹 mutation 의 onSuccess 가 가이드/챌린지 도메인 키를 함께 invalidate
  // 하므로 호출자 측에서 refetchGuides / refetchChallenges 를 부를 필요 없음.

  // 검색 input toggle + 입력 버퍼 (즉시 적용보다 사용자 경험 위해 enter 또는 blur 시 적용)
  // 확정 검색어(search)는 Context 에 살아남고 이 페이지 state 는 재진입 시 초기화되므로,
  // 버퍼의 초깃값을 확정 검색어로 잡는다. 이후 두 값은 아래 핸들러에서만 함께 움직인다
  // (effect 로 뒤늦게 맞추면 렌더 -> effect -> 재렌더로 한 번 더 돈다).
  const [isSearchOpen, setIsSearchOpen] = useState(false)
  const [searchDraft, setSearchDraft] = useState(search)
  // 삭제 중 카드 비활성용 — 동시 클릭 방지.
  const [deletingId, setDeletingId] = useState(null)

  // 처방전 삭제 — confirm 후 deleteGroup. BE 가 그룹 + medication + 가이드 cascade 처리.
  // 챌린지는 가이드 cascade 정책에 따라 활성/완료는 보존, 미시작은 soft delete.
  const handleDeleteGroup = async (group) => {
    const dateLabel = group.dispensed_date ? formatDate(group.dispensed_date) : '이 처방전'
    const hospitalLabel = group.hospital_name ? ` · ${group.hospital_name}` : ''
    const ok = await confirm({
      title: '처방전 삭제',
      message:
        `${dateLabel}${hospitalLabel} 처방전을 삭제할까요?\n\n` +
        '이 처방전의 약품과 연결된 가이드도 함께 정리됩니다.\n' +
        '진행 중·완료된 챌린지는 그대로 보존됩니다.',
      confirmLabel: '삭제',
      danger: true,
    })
    if (!ok) return
    setDeletingId(group.id)
    try {
      await deleteGroup(group.id)
      toast.success('처방전이 삭제되었습니다. 연결된 가이드도 정리됐어요.')
    } catch (err) {
      if (err.response?.status !== 401) {
        showError(err.parsed?.message || '처방전 삭제에 실패했습니다.')
      }
    } finally {
      setDeletingId(null)
    }
  }

  // 페이지 진입마다 최신 list 보장 — 다른 화면 (OCR confirm 등) 에서 새 처방전이
  // 등록된 직후 /medication 으로 이동 시 stale 방지. Context 의 list query 는
  // Provider 가 앱 전역에 마운트된 채라 이 페이지 진입만으로는 refetch 되지 않고,
  // staleTime(기본 60초) 안이면 캐시를 그대로 쓴다.
  useEffect(() => {
    if (selectedProfileId) refetchGroups()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // 확정 검색어는 trim 된 값 — 버퍼도 같은 값으로 맞춰 두 state 가 어긋나지 않게 한다.
  const applySearch = () => {
    const next = searchDraft.trim()
    setSearchDraft(next)
    setSearch(next)
  }
  const clearSearch = () => {
    setSearchDraft('')
    setSearch('')
    setIsSearchOpen(false)
  }

  return (
    <main className="min-h-screen bg-surface-2 pb-24">
      {/* ── 상단 헤더 ── */}
      <header className="sticky top-0 z-20 bg-surface border-b border-line">
        <div className="max-w-4xl mx-auto px-4 py-3 flex items-center gap-3">
          <h1 className="flex-1 text-base font-bold text-ink">복용 가이드</h1>
          <button
            type="button"
            onClick={() => setIsSearchOpen((v) => !v)}
            className="p-2 rounded-lg hover:bg-surface-2 cursor-pointer"
            aria-label="약품 검색"
          >
            <Search size={18} className={isSearchOpen ? 'text-blue-500' : 'text-muted'} />
          </button>
          <button
            type="button"
            onClick={() => router.push('/ocr')}
            className="p-2 rounded-lg hover:bg-surface-2 cursor-pointer"
            aria-label="처방전 추가"
          >
            <Plus size={18} className="text-ink" />
          </button>
        </div>

        {/* 검색 input — toggle 시에만 표시 */}
        {isSearchOpen && (
          <div className="max-w-4xl mx-auto px-4 pb-3">
            <div className="flex items-center gap-2 bg-surface-2 border border-line rounded-xl px-3 py-2">
              <Search size={16} className="text-muted shrink-0" />
              <input
                type="text"
                value={searchDraft}
                onChange={(e) => setSearchDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') applySearch()
                }}
                onBlur={applySearch}
                placeholder="약품 이름으로 검색"
                className="flex-1 bg-transparent text-sm outline-none"
                autoFocus
              />
              {searchDraft && (
                <button
                  type="button"
                  onClick={clearSearch}
                  className="p-0.5 rounded hover:bg-surface-2 cursor-pointer"
                  aria-label="검색 지우기"
                >
                  <X size={14} className="text-muted" />
                </button>
              )}
            </div>
            {search && (
              <p className="text-[11px] text-muted mt-1.5 px-1">
                <span className="font-bold text-muted">{search}</span> 약품을 포함하는 처방전을 보여드려요.
              </p>
            )}
          </div>
        )}

        {/* 탭: 전체 / 복용 중 / 복용 완료 */}
        <div className="max-w-4xl mx-auto px-2 pb-1 flex gap-1 overflow-x-auto scrollbar-hide">
          {STATUS_TABS.map((tab) => (
            <button
              key={tab.key}
              type="button"
              onClick={() => setStatusFilter(tab.key)}
              className={`px-3 py-2 text-xs font-bold whitespace-nowrap border-b-2 transition-colors cursor-pointer ${
                statusFilter === tab.key
                  ? 'border-accent text-ink'
                  : 'border-transparent text-muted hover:text-ink'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </header>

      <div className="max-w-4xl mx-auto px-4 py-4 space-y-3">
        {/* 정렬 dropdown — 헤더 아래 */}
        <div className="flex items-center justify-end">
          <label className="text-[11px] text-muted mr-2">정렬</label>
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value)}
            className="text-xs font-bold border border-line rounded-lg px-2.5 py-1.5 bg-surface cursor-pointer"
          >
            {Object.entries(SORT_LABELS).map(([key, label]) => (
              <option key={key} value={key}>{label}</option>
            ))}
          </select>
        </div>

        {/* 카드 list */}
        {isLoading ? (
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <GroupCardSkeleton key={i} />
            ))}
          </div>
        ) : !selectedProfileId ? (
          <EmptyState title="프로필을 선택해주세요" message="프로필을 선택하면 처방전이 표시됩니다." />
        ) : groups.length === 0 ? (
          <EmptyState
            title={search ? '검색 결과가 없어요' : '등록된 처방전이 없어요'}
            message={search ? `'${search}' 약품을 포함하는 처방전을 찾지 못했어요.` : '처방전을 등록해 보세요.'}
          />
        ) : (
          <div className="space-y-3">
            {groups.map((g) => (
              <PrescriptionCard
                key={g.id}
                group={g}
                onClick={() => router.push(`/medication/group?group_id=${g.id}`)}
                onDelete={() => handleDeleteGroup(g)}
                isDeleting={deletingId === g.id}
              />
            ))}
          </div>
        )}
      </div>

      <BottomNav />
    </main>
  )
}
