'use client'
import { AlertTriangle, RefreshCw } from 'lucide-react'
import PropTypes from 'prop-types'

import { HTTP_STATUS_MESSAGES, parseApiError } from '@/lib/errors'

const DEFAULT_TITLE = '불러오지 못했어요'
const DEFAULT_MESSAGE = '네트워크 상태를 확인하고 다시 시도해 주세요.'

// ── 에러 문구 결정 ───────────────────────────────────────────────────
// 흐름: 에러 유무 확인 -> 4xx 는 상태코드 표준 문구 -> 그 외는 parseApiError 문구
// 4xx 만 따로 다루는 이유: parseApiError 는 서버가 보낸 detail 원문을 그대로
// 메시지로 쓴다. 토스트는 몇 초 뒤 사라지지만 이 화면은 사용자가 떠날 때까지
// 남으므로, 서버 내부 문자열의 노출면을 넓히지 않는다(FE CLAUDE.md 5번).
function toUserMessage(error) {
  if (!error) return DEFAULT_MESSAGE
  const parsed = parseApiError(error)
  if (parsed.status >= 400 && parsed.status < 500) {
    return HTTP_STATUS_MESSAGES[parsed.status] || DEFAULT_MESSAGE
  }
  return parsed.message
}

// ── 조회 실패 상태 (EmptyState 의 형제) ───────────────────────────────
// 흐름: 쿼리 isError -> 이 컴포넌트 렌더 -> 사용자가 재시도 -> refetch
// EmptyState 와 같은 자리·같은 크기를 쓰되 **의미가 다르다**:
// EmptyState = "데이터가 없다(정상)", ErrorState = "데이터를 못 받았다(실패)".
// 이 둘을 구분하지 않으면 429/500 이 "등록된 게 없어요"로 보인다.
export default function ErrorState({ error, title, message, onRetry, isRetrying }) {
  const bodyMessage = message || toUserMessage(error)

  return (
    <div
      role="alert"
      data-testid="error-state"
      className="flex flex-col items-center justify-center py-12 px-6 text-center bg-surface rounded-2xl shadow-sm border border-line"
    >
      <div className="mb-4 text-muted">
        <AlertTriangle size={48} />
      </div>
      <h3 className="text-lg font-bold text-ink mb-1">{title || DEFAULT_TITLE}</h3>
      <p className="text-muted text-sm mb-6 max-w-[240px] leading-relaxed">{bodyMessage}</p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          disabled={isRetrying}
          className="flex items-center gap-2 bg-accent text-accent-ink px-8 py-3 rounded-xl font-black text-sm hover:brightness-110 transition-all shadow-lg cursor-pointer active:scale-95 disabled:bg-surface-2 disabled:text-muted disabled:cursor-wait"
        >
          <RefreshCw size={16} className={isRetrying ? 'animate-spin' : ''} />
          {isRetrying ? '다시 시도 중...' : '다시 시도'}
        </button>
      )}
    </div>
  )
}

ErrorState.propTypes = {
  // axios 에러 객체. 문구 결정에만 쓰이고 원문은 화면에 노출되지 않는다.
  error: PropTypes.object,
  title: PropTypes.string,
  // 직접 지정하면 error 기반 자동 문구를 대체한다.
  message: PropTypes.string,
  onRetry: PropTypes.func,
  isRetrying: PropTypes.bool,
}

ErrorState.defaultProps = {
  error: null,
  title: null,
  message: null,
  onRetry: null,
  isRetrying: false,
}
