'use client'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { CheckCircle, X } from 'lucide-react'
import toast from 'react-hot-toast'

import api from '@/lib/api'
import { streamSSE } from '@/lib/sseClient'
import { useProfile } from '@/contexts/ProfileContext'

const STEPS = [
  '처방전 이미지를 읽고 있어요...',
  'AI가 약품 정보를 분석하고 있어요...',
  '복용 방법을 정리하고 있어요...',
  '거의 다 됐어요!',
]

const TERMINAL_ERROR_MESSAGES = {
  no_text: '이미지에서 텍스트를 찾지 못했어요.',
  no_candidates: '약품 정보를 인식하지 못했어요.',
  failed: '처리 중 오류가 발생했어요.',
}

/**
 * SSE 연결을 ready/terminal 까지 자동 재연결하며 await for-of 로 소비한다.
 * timeout event 가 오면 새 연결을 열어 계속 대기 — 사용자가 끄거나 ready
 * 도달 전까지 무한 재연결.
 *
 * @yields {{status: string, medicines?: any[]}}  draft poll payload
 */
async function* watchDraftStatus(draftId, profileId, signal) {
  const path = profileId
    ? `/api/v1/ocr/draft/${draftId}/stream?profile_id=${profileId}`
    : `/api/v1/ocr/draft/${draftId}/stream`
  while (true) {
    let timedOut = false
    for await (const ev of streamSSE(path, { signal })) {
      if (ev.event === 'update') yield ev.data
      else if (ev.event === 'timeout') {
        timedOut = true
        break
      } else if (ev.event === 'error') throw new Error(ev.data?.detail || 'sse error')
    }
    if (!timedOut) return // 정상 close (terminal 도달)
  }
}

function MedCardSkeleton({ delay = 0 }) {
  return (
    <div
      className="bg-surface rounded-2xl p-6 shadow-sm border border-line animate-pulse"
      style={{ animationDelay: `${delay}ms` }}
    >
      <div className="flex justify-between items-center mb-5">
        <div className="h-5 w-40 bg-surface-2 rounded-lg" />
        <div className="w-5 h-5 bg-surface-2 rounded" />
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        {[0, 1, 2, 3].map((j) => (
          <div key={j} className="bg-surface-2 p-2 rounded-xl border border-line">
            <div className="h-2.5 w-12 bg-surface-2 rounded mb-2" />
            <div className="h-3.5 w-10 bg-surface-2 rounded" />
          </div>
        ))}
      </div>
    </div>
  )
}

function SuccessOverlay() {
  return (
    <div className="fixed inset-0 bg-surface flex flex-col items-center justify-center z-50 animate-in fade-in duration-300">
      <div className="w-20 h-20 bg-accent rounded-full flex items-center justify-center mb-6">
        <CheckCircle size={36} className="text-accent-ink" strokeWidth={1.5} />
      </div>
      <h2 className="text-xl font-bold text-ink mb-2">분석 완료!</h2>
      <p className="text-sm text-muted">처방전 내용을 확인해주세요</p>
    </div>
  )
}

function PrescriptionSkeleton({ step }) {
  const progress = ((step + 1) / STEPS.length) * 100

  return (
    <div className="min-h-screen bg-surface-2 pb-32">
      {/* 헤더 */}
      <div className="bg-surface border-b border-line px-10 py-4 flex items-center gap-4 animate-pulse">
        <div className="w-6 h-6 bg-surface-2 rounded-full" />
        <div className="flex-1">
          <div className="h-4 w-36 bg-surface-2 rounded-lg mb-2" />
          <div className="h-3 w-48 bg-surface-2 rounded-lg" />
        </div>
      </div>

      {/* 진행 상태 안내 */}
      <div className="bg-surface border-b border-line px-10 py-3">
        <div className="max-w-3xl mx-auto">
          <div className="flex justify-between items-center mb-2">
            <p className="text-xs font-medium text-muted">{STEPS[step]}</p>
            <p className="text-xs text-muted">
              {step + 1} / {STEPS.length}
            </p>
          </div>
          <div className="w-full bg-surface-2 rounded-full h-1 overflow-hidden">
            <div
              className="h-1 rounded-full bg-surface-2 transition-all duration-700 ease-out"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>
      </div>

      <div className="max-w-3xl mx-auto px-10 py-8 space-y-4">
        {/* 안내 배너 */}
        <div className="bg-blue-50 rounded-2xl p-4 flex items-center gap-3 animate-pulse">
          <div className="w-8 h-8 bg-blue-100 rounded-full shrink-0" />
          <div className="flex-1">
            <div className="h-3.5 w-24 bg-blue-100 rounded mb-2" />
            <div className="h-3 w-52 bg-blue-100 rounded" />
          </div>
        </div>

        {/* 약품 카드 3개 */}
        <MedCardSkeleton delay={0} />
        <MedCardSkeleton delay={150} />
        <MedCardSkeleton delay={300} />

        {/* 하단 버튼 */}
        <div className="flex gap-3 pt-2 animate-pulse">
          <div className="flex-1 h-14 bg-surface border border-line rounded-xl" />
          <div className="flex-1 h-14 bg-surface-2 rounded-xl" />
        </div>
      </div>
    </div>
  )
}

export default function OcrLoadingPage() {
  const router = useRouter()
  const { selectedProfileId } = useProfile()
  const [step, setStep] = useState(0)
  const [done, setDone] = useState(false)

  useEffect(() => {
    const abortController = new AbortController()
    let stepTicker = null

    stepTicker = setInterval(() => {
      setStep((prev) => (prev < STEPS.length - 1 ? prev + 1 : prev))
    }, 1500)

    // SSE 로 ai-worker 진행 상태를 받아오는 메인 루프.
    // ready -> SuccessOverlay -> result push, terminal -> 안내 + /ocr 복귀.
    const consumeStream = async (draftId) => {
      try {
        for await (const payload of watchDraftStatus(
          draftId,
          selectedProfileId,
          abortController.signal,
        )) {
          const status = payload.status
          if (status === 'ready') {
            clearInterval(stepTicker)
            setDone(true)
            setTimeout(() => router.push(`/ocr/result?draft_id=${draftId}`), 1200)
            return
          }
          if (status in TERMINAL_ERROR_MESSAGES) {
            clearInterval(stepTicker)
            toast.error(`${TERMINAL_ERROR_MESSAGES[status]} 다시 촬영해주세요.`)
            router.push('/ocr')
            return
          }
          // status='pending' — STEPS 진행 (별도 ticker), 다음 SSE event 대기
        }
        // generator 종료 (no more events) — 이론상 ready/terminal 에서 return 으로 빠짐
      } catch (err) {
        if (abortController.signal.aborted) return
        clearInterval(stepTicker)
        const msg = err?.message || '분석 중 오류가 발생했습니다.'
        router.push(`/ocr?error=${encodeURIComponent(msg)}`)
      }
    }

    const run = async () => {
      try {
        const fileData = sessionStorage.getItem('ocrFileData')
        const fileName = sessionStorage.getItem('ocrFileName')
        const fileType = sessionStorage.getItem('ocrFileType')
        if (!fileData) {
          router.push('/ocr')
          return
        }

        const blob = await (await fetch(fileData)).blob()
        const file = new File([blob], fileName, { type: fileType })
        const formData = new FormData()
        formData.append('file', file)

        // 현재 선택된 프로필로 처방전 등록 — selectedProfileId 가 없으면 BE 가 SELF default
        const response = await api.post('/api/v1/ocr/extract', formData, {
          headers: { 'Content-Type': 'multipart/form-data' },
          timeout: 60000,
          params: selectedProfileId ? { profile_id: selectedProfileId } : undefined,
        })

        sessionStorage.removeItem('ocrFileData')
        sessionStorage.removeItem('ocrFileName')
        sessionStorage.removeItem('ocrFileType')

        if (abortController.signal.aborted) return
        await consumeStream(response.data.draft_id)
      } catch (err) {
        clearInterval(stepTicker)
        const msg =
          err.parsed?.message || err.response?.data?.detail || '분석 중 오류가 발생했습니다.'
        router.push(
          `/ocr?error=${encodeURIComponent(typeof msg === 'string' ? msg : JSON.stringify(msg))}`,
        )
      }
    }

    run()
    return () => {
      abortController.abort()
      clearInterval(stepTicker)
    }
  }, [router, selectedProfileId])

  // 우측상단 닫기 X — 사용자가 main 으로 빠져나갈 수 있도록.
  // 처리 자체는 ai-worker 가 백그라운드로 계속 수행 -> main 의 활성 draft 카드로 회수 가능.
  const handleClose = () => router.push('/main')

  if (done) return <SuccessOverlay />
  return (
    <>
      <button
        onClick={handleClose}
        className="fixed top-4 right-4 z-30 w-10 h-10 bg-surface border border-line rounded-full flex items-center justify-center shadow-sm hover:bg-surface-2 cursor-pointer"
        aria-label="닫고 메인으로 이동"
      >
        <X size={18} className="text-muted" />
      </button>
      <PrescriptionSkeleton step={step} />
    </>
  )
}
