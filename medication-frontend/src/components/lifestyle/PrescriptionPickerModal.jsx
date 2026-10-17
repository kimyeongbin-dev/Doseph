'use client'

// 처방전 선택 바텀시트 모달 — "+ 새 가이드" 클릭 시 노출.
// PrescriptionGroupContext 의 active 그룹 list 를 카드 형태로 보여주고
// 선택된 group_id 를 onConfirm 으로 넘긴다. 활성 약 없는 그룹은 선택 불가.

import { useEffect } from 'react'

import { usePrescriptionGroup } from '@/contexts/PrescriptionGroupContext'

function formatDispensedLabel(iso) {
  if (!iso) return '처방일 미상'
  const d = String(iso).slice(0, 10).split('-')
  if (d.length !== 3) return iso
  return `${d[0]}.${d[1]}.${d[2]}`
}

export default function PrescriptionPickerModal({ onConfirm, onClose, isLoading = false }) {
  const { groups, isLoading: groupsLoading } = usePrescriptionGroup()

  // 가이드는 *활성 약물 보유 처방전* 에서만 만들 수 있다 (BE 가 NO_ACTIVE_MEDICATIONS
  // 로 차단하지만 UX 상 미리 disable 처리해 헛클릭 방지).
  const candidates = (groups || []).filter((g) => g.has_active_medication)

  // 모달 열릴 때 body 스크롤 잠금
  useEffect(() => {
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = ''
    }
  }, [])

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-end lg:items-center justify-center bg-black/40"
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="bg-surface w-full lg:max-w-lg rounded-t-3xl lg:rounded-3xl shadow-2xl max-h-[80vh] flex flex-col"
      >
        {/* 헤더 */}
        <div className="px-5 pt-5 pb-3 border-b border-line">
          <p className="text-base font-black text-ink">처방전 선택</p>
          <p className="text-xs text-muted mt-1 break-keep">
            가이드는 처방전 단위로 만들어져요. 가이드를 받을 처방전을 선택해주세요.
          </p>
        </div>

        {/* 목록 */}
        <div className="px-3 py-3 overflow-y-auto flex-1">
          {groupsLoading ? (
            <div className="space-y-2 animate-pulse">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-16 bg-surface-2 rounded-xl" />
              ))}
            </div>
          ) : candidates.length === 0 ? (
            <div className="text-center text-sm text-muted py-10 px-4 break-keep">
              가이드를 만들 수 있는 처방전이 없어요.
              <br />
              먼저 처방전을 등록하거나 복용 중인 약을 확인해주세요.
            </div>
          ) : (
            <div className="space-y-2">
              {candidates.map((g) => (
                <button
                  key={g.id}
                  type="button"
                  disabled={isLoading}
                  onClick={() => onConfirm(g.id)}
                  className={`w-full text-left px-4 py-3 rounded-xl border transition-colors ${
                    isLoading
                      ? 'bg-surface-2 border-line cursor-wait'
                      : 'bg-surface border-line hover:border-accent hover:bg-surface-2 cursor-pointer'
                  }`}
                >
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-sm font-bold text-ink truncate">
                        {g.hospital_name || '병원 미상'}
                      </p>
                      <p className="text-[11px] text-muted mt-0.5">
                        {g.department || '진료과 미상'} · {formatDispensedLabel(g.dispensed_date)}
                      </p>
                    </div>
                    <div className="shrink-0 text-right">
                      <p className="text-[11px] font-bold text-ink">
                        복용 중 {g.active_medications_count ?? 0}건 / 약 {g.medications_count || 0}
                        개
                      </p>
                    </div>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* 푸터 */}
        <div className="px-5 py-3 border-t border-line">
          <button
            type="button"
            onClick={onClose}
            disabled={isLoading}
            className={`w-full py-3 rounded-xl text-sm font-bold transition-colors ${
              isLoading
                ? 'bg-surface-2 text-muted cursor-wait'
                : 'bg-surface-2 text-ink hover:bg-surface-2 cursor-pointer'
            }`}
          >
            취소
          </button>
        </div>
      </div>
    </div>
  )
}
