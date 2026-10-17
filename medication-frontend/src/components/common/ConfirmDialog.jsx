'use client'

// 공용 확인 다이얼로그 + Promise-based hook.
//
// 기존 native `window.confirm()` / `confirm()` 호출을 대체. 톤앤매너가 다른
// 모바일 native dialog 대신 프로젝트 공통 모달 (StartChallengeModal /
// PrescriptionPickerModal) 과 동일 스타일 사용.
//
// 사용:
//   const confirm = useConfirm()
//   const ok = await confirm({
//     title: '처방전 삭제',
//     message: '이 처방전을 삭제할까요? 약품과 가이드도 함께 정리됩니다.',
//     confirmLabel: '삭제',
//     danger: true,
//   })
//   if (!ok) return
//
// Provider 는 layout 최상위에 한 번만 mount. 내부 state 가 한 dialog 인스턴스를
// 직렬화 (한 번에 하나만 노출), Promise resolver 를 ref 에 저장 → 사용자가
// 확인/취소 누르면 resolve(boolean).

import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'

const ConfirmContext = createContext(null)

const DEFAULT_OPTS = {
  title: '확인',
  message: '',
  confirmLabel: '확인',
  cancelLabel: '취소',
  danger: false,
}

export function ConfirmProvider({ children }) {
  const [opts, setOpts] = useState(null)
  const resolverRef = useRef(null)

  const confirm = useCallback((options) => {
    return new Promise((resolve) => {
      resolverRef.current = resolve
      setOpts({ ...DEFAULT_OPTS, ...(options || {}) })
    })
  }, [])

  const close = useCallback((value) => {
    resolverRef.current?.(value)
    resolverRef.current = null
    setOpts(null)
  }, [])

  // ESC = 취소, Enter = 확인 (focus 가 confirm 버튼이라 자연 동작)
  useEffect(() => {
    if (!opts) return
    const onKey = (e) => {
      if (e.key === 'Escape') close(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [opts, close])

  // body 스크롤 잠금
  useEffect(() => {
    if (!opts) return
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = prev
    }
  }, [opts])

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      {opts && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="confirm-dialog-title"
          className="fixed inset-0 z-[100] flex items-center justify-center bg-black/40 px-4"
          onClick={() => close(false)}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="bg-surface rounded-2xl shadow-2xl w-full max-w-sm overflow-hidden"
          >
            <div className="px-6 pt-6 pb-3">
              <h3 id="confirm-dialog-title" className="text-base font-black text-ink">
                {opts.title}
              </h3>
              {opts.message && (
                <p className="mt-2 text-sm text-muted leading-relaxed break-keep whitespace-pre-line">
                  {opts.message}
                </p>
              )}
            </div>
            <div className="flex border-t border-line">
              <button
                type="button"
                onClick={() => close(false)}
                className="flex-1 py-3.5 text-sm font-bold text-muted hover:bg-surface-2 cursor-pointer transition-colors"
              >
                {opts.cancelLabel}
              </button>
              <button
                type="button"
                autoFocus
                onClick={() => close(true)}
                className={`flex-1 py-3.5 text-sm font-bold cursor-pointer transition-colors border-l border-line ${
                  opts.danger ? 'text-red-500 hover:bg-red-50' : 'text-ink hover:bg-surface-2'
                }`}
              >
                {opts.confirmLabel}
              </button>
            </div>
          </div>
        </div>
      )}
    </ConfirmContext.Provider>
  )
}

export function useConfirm() {
  const ctx = useContext(ConfirmContext)
  if (!ctx) throw new Error('useConfirm must be used within ConfirmProvider')
  return ctx
}
