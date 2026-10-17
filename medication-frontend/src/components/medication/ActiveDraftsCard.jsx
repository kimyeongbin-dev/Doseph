'use client'
import { useState } from 'react'
import { FileText, Loader2, X, Trash2 } from 'lucide-react'
import PropTypes from 'prop-types'

// 활성 OCR draft 카드 — main 우측하단 floating (챗봇 아이콘 위)
// 사용자가 X 로 카드 전체를 숨길 수 있고 (새로고침 시 다시 표시),
// 숨김은 그 프로필에만 걸린다 — 다른 프로필로 바꾸면 다시 보인다(QA-42).
// 각 항목 좌측의 휴지통으로 개별 draft 를 폐기할 수도 있다.
export default function ActiveDraftsCard({ drafts, profileId, onSelect, onDelete }) {
  const [dismissedFor, setDismissedFor] = useState(null)
  const dismissed = dismissedFor !== null && dismissedFor === profileId
  if (!drafts || drafts.length === 0 || dismissed) return null

  const formatTime = (iso) => {
    const d = new Date(iso)
    return d.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' })
  }
  const STATUS_LABEL = {
    pending: '처리 중',
    ready: '확인 대기',
    no_text: '텍스트 없음',
    no_candidates: '인식 실패',
    failed: '오류',
  }

  return (
    <div className="fixed right-6 bottom-44 z-40 w-72 bg-surface rounded-2xl border border-line shadow-[var(--shadow-pop)] p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <FileText size={16} className="text-muted" />
          <p className="font-bold text-sm text-ink">처방전 ({drafts.length}건)</p>
        </div>
        <button
          onClick={() => setDismissedFor(profileId)}
          className="text-muted hover:text-ink cursor-pointer"
          aria-label="카드 숨기기"
        >
          <X size={16} />
        </button>
      </div>
      <ul className="space-y-1 max-h-56 overflow-y-auto">
        {drafts.map((d) => (
          <li key={d.draft_id} className="flex items-center gap-1">
            <button
              onClick={() => onDelete(d.draft_id)}
              className="text-muted hover:text-critical cursor-pointer flex-shrink-0 p-2 rounded-lg hover:bg-critical/10 transition-colors"
              aria-label="처방전 폐기"
            >
              <Trash2 size={14} />
            </button>
            <button
              onClick={() => onSelect(d.draft_id)}
              className="flex-1 flex items-center justify-between gap-3 px-3 py-2 rounded-xl hover:bg-surface-2 cursor-pointer transition-colors text-left"
            >
              <div className="flex items-center gap-2 min-w-0">
                {d.status === 'pending' ? (
                  <Loader2 size={14} className="text-accent animate-spin flex-shrink-0" />
                ) : (
                  <span className="w-2 h-2 rounded-full bg-success flex-shrink-0" />
                )}
                <span className="text-sm font-bold text-ink truncate">
                  {formatTime(d.created_at)} 업로드
                </span>
              </div>
              <span className="text-xs text-muted flex-shrink-0">
                {STATUS_LABEL[d.status] || d.status}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}

ActiveDraftsCard.propTypes = {
  drafts: PropTypes.arrayOf(
    PropTypes.shape({
      draft_id: PropTypes.string.isRequired,
      status: PropTypes.string.isRequired,
      created_at: PropTypes.string.isRequired,
    }),
  ),
  profileId: PropTypes.oneOfType([PropTypes.string, PropTypes.number]),
  onSelect: PropTypes.func.isRequired,
  onDelete: PropTypes.func.isRequired,
}
