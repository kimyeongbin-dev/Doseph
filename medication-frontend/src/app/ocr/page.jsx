'use client'
import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { Info, Camera, AlertTriangle } from 'lucide-react'
import toast from 'react-hot-toast'

import Header from '@/components/layout/Header'
import { useConfirm } from '@/components/common/ConfirmDialog'
import { useProfile } from '@/contexts/ProfileContext'
import { OcrEngineLoadError, recognizePrescription } from '@/lib/ocr/browserOcr'
import { selectDrugLines, summarizeOcrResult } from '@/lib/ocr/ocrLines'
import { judgeRetake } from '@/lib/ocr/retake'
import { submitOcrText } from '@/lib/ocrApi'

const STAGE_LABELS = {
  loading: '글자 인식 준비 중... (처음 한 번은 시간이 걸려요)',
  reading: '기기 안에서 처방전을 읽고 있어요...',
  sending: '약 정보를 보내고 있어요...',
}

function OCRSkeleton() {
  return (
    <div className="min-h-screen bg-surface-2 pb-32 animate-pulse">
      <div className="h-48 bg-surface border-b border-line" />
      <div className="max-w-3xl mx-auto px-6 py-12">
        <div className="h-40 bg-surface-2 rounded-3xl mb-12 shadow-sm border border-line" />
        <div className="h-[400px] bg-surface rounded-[40px] border border-line shadow-sm" />
        <div className="mt-12 flex gap-4">
          <div className="flex-1 h-16 bg-surface-2 rounded-2xl" />
          <div className="flex-1 h-16 bg-surface-2 rounded-2xl" />
        </div>
      </div>
    </div>
  )
}

export default function OcrPage() {
  const router = useRouter()
  const confirm = useConfirm()
  const { selectedProfileId } = useProfile()
  const [isLoading, setIsLoading] = useState(true)
  const [preview, setPreview] = useState(null)
  const [file, setFile] = useState(null)
  const [stage, setStage] = useState(null)
  const [noDrugLines, setNoDrugLines] = useState(false)

  useEffect(() => {
    setTimeout(() => setIsLoading(false), 800)
  }, [])

  if (isLoading) return <OCRSkeleton />

  const handleCancel = async () => {
    const ok = await confirm({
      title: '작성 취소',
      message: '작성 중인 내용이 사라집니다. 정말 나가시겠습니까?',
      confirmLabel: '나가기',
      danger: true,
    })
    if (ok) router.push('/main')
  }

  const handleFileChange = (e) => {
    const selected = e.target.files[0]
    if (selected) {
      setFile(selected)
      setPreview(URL.createObjectURL(selected))
      setNoDrugLines(false)
    }
  }

  // 신뢰도가 낮을 때 — 막지 않고 권한다. 진행해도 약 줄 고르기는 그대로 적용된다.
  const confirmLowConfidence = () =>
    confirm({
      title: '사진이 조금 흐릿해요',
      message:
        '확실히 읽지 못한 글자가 있어요. 밝은 곳에서 처방전이 화면에 꽉 차게 다시 찍으면 더 정확해요.',
      confirmLabel: '그래도 진행',
      cancelLabel: '다시 찍기',
    })

  // ── 처방전 분석 ─────────────────────────────────────────────────────
  // 흐름: 기기 안 OCR -> 신뢰도 0.5 미만 버림 -> 약 줄만 고름 -> 재촬영 판정
  //       -> block: 안내 / suggest: 권유(진행 가능) / ok
  //       -> 약 줄 글자만 서버로 -> draft_id 로 진행 화면
  // 사진은 기기 밖으로 나가지 않고, 저장소(sessionStorage)에도 넣지 않는다.
  const handleAnalyze = async () => {
    if (!file || stage) return
    setNoDrugLines(false)
    try {
      const result = await recognizePrescription(file, { onStage: setStage })
      const { lines, meanConfidence } = summarizeOcrResult(result)
      const drugLines = selectDrugLines(lines)
      const verdict = judgeRetake({ meanConfidence, drugLineCount: drugLines.length })
      if (verdict === 'block') {
        setNoDrugLines(true)
        setStage(null)
        return
      }
      if (verdict === 'suggest' && !(await confirmLowConfidence())) {
        setStage(null)
        return
      }
      setStage('sending')
      const draftId = await submitOcrText({
        text: drugLines.join('\n'),
        profileId: selectedProfileId,
      })
      router.push(`/ocr/loading?draft_id=${encodeURIComponent(draftId)}`)
    } catch (error) {
      setStage(null)
      toast.error(
        error instanceof OcrEngineLoadError
          ? '글자 인식 준비에 실패했어요. 인터넷 연결을 확인하고 다시 시도하거나 직접 입력해 주세요.'
          : '처방전을 분석하지 못했어요. 다시 시도해 주세요.',
      )
    }
  }

  return (
    <main className="min-h-screen bg-surface-2 pb-32">
      <Header
        title="처방전 등록"
        subtitle="사진을 찍어 약을 등록하세요"
        showBack={true}
        onBack={handleCancel}
      />

      <div className="max-w-3xl mx-auto px-6 py-8">
        {/* 안내 카드 */}
        <div className="bg-surface-2 rounded-2xl p-6 mb-8 border border-line">
          <h2 className="font-bold text-ink text-sm mb-4 flex items-center gap-2">
            <Info size={14} className="text-muted" />
            처방전 등록 방법
          </h2>
          <div className="space-y-4">
            {[
              '처방전 사진을 찍으세요 — 사진은 기기 밖으로 나가지 않아요',
              '기기 안에서 글자를 읽고, 약 정보가 적힌 줄만 보내요',
              '인식된 정보를 확인하고 저장하세요',
            ].map((text, i) => (
              <div key={i} className="flex gap-3">
                <span className="bg-accent text-accent-ink w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold shrink-0">
                  {i + 1}
                </span>
                <p className="text-sm text-muted">{text}</p>
              </div>
            ))}
          </div>
        </div>

        {/* 업로드 영역 */}
        <div className="bg-surface rounded-3xl shadow-sm p-4 border border-line">
          <label className="block w-full border-2 border-dashed border-line rounded-2xl py-20 text-center cursor-pointer hover:border-line hover:bg-surface-2/50 transition-all">
            <input type="file" accept="image/*" onChange={handleFileChange} className="hidden" />
            {preview ? (
              <div className="px-4">
                {/* eslint-disable-next-line @next/next/no-img-element -- 정적 export(unoptimized) + 클라 미리보기(dataURL)라 next/image 이점 없음 */}
                <img src={preview} alt="미리보기" className="w-full rounded-xl shadow-md" />
                <p className="text-muted text-xs font-bold mt-4">클릭하여 사진 교체</p>
              </div>
            ) : (
              <div className="animate-in fade-in zoom-in duration-300">
                <div className="w-16 h-16 bg-surface-2 rounded-full flex items-center justify-center mx-auto mb-4">
                  <Camera size={28} className="text-muted" />
                </div>
                <p className="text-ink font-bold mb-1">처방전 사진 찍기</p>
                <p className="text-muted text-xs">JPG, PNG 파일 지원</p>
              </div>
            )}
          </label>
        </div>

        {/* 약 줄을 하나도 못 찾았을 때 — 보낼 것이 없으므로 진행을 막고 재촬영·직접 입력을 안내 */}
        {noDrugLines && (
          <div
            role="alert"
            className="mt-6 bg-red-50 rounded-2xl p-4 flex items-start gap-3 border border-red-100"
          >
            <AlertTriangle size={18} className="text-red-600 shrink-0 mt-0.5" />
            <div>
              <p className="font-bold text-red-800 text-sm mb-1">약 정보를 찾지 못했어요</p>
              <p className="text-red-700 text-xs">
                밝은 곳에서 처방전이 화면에 꽉 차게 다시 찍거나, 아래에서 직접 입력해 주세요.
              </p>
            </div>
          </div>
        )}

        {/* 분석 진행 단계 */}
        {stage && (
          <p role="status" aria-live="polite" className="mt-6 text-center text-sm text-muted">
            {STAGE_LABELS[stage]}
          </p>
        )}

        {/* [신규 추가] 직접 입력 안내 배너 */}
        <div className="mt-8 bg-blue-50 rounded-2xl p-4 flex items-center gap-3 shadow-sm border border-blue-100">
          <span className="text-2xl">💡</span>
          <div className="flex-1">
            <p className="font-bold text-blue-800 text-sm mb-1">사진 촬영이 어렵다면?</p>
            <p className="text-blue-700 text-xs">
              처방전이 없거나 인식이 어려운 약품은 아래 버튼을 눌러 직접 입력할 수 있어요.
            </p>
          </div>
        </div>

        {/* 직접 약품 추가하기 버튼 */}
        <button
          onClick={() => router.push('/ocr/result?draft_id=manual')}
          className="w-full mt-3 bg-surface rounded-2xl p-4 border-2 border-dashed border-blue-300 text-blue-500 font-bold hover:bg-blue-50 hover:border-blue-400 transition-colors flex items-center justify-center gap-2 cursor-pointer shadow-sm"
        >
          <span className="text-xl">+</span> 직접 약품 추가하기
        </button>

        {/* 하단 버튼 */}
        <div className="mt-8 flex gap-3">
          <button
            onClick={handleCancel}
            className="flex-1 bg-surface border border-line py-4 rounded-xl text-muted text-sm font-bold cursor-pointer hover:bg-surface-2 transition-all active:scale-[0.98]"
          >
            취소
          </button>
          <button
            onClick={handleAnalyze}
            disabled={!preview || Boolean(stage)}
            className={`flex-1 py-4 rounded-xl text-sm font-bold transition-all active:scale-[0.98] cursor-pointer
              ${
                preview && !stage
                  ? 'bg-accent text-accent-ink hover:brightness-110'
                  : 'bg-surface-2 text-muted cursor-not-allowed'
              }`}
          >
            {stage ? '분석 중...' : '분석 시작하기'}
          </button>
        </div>
      </div>
    </main>
  )
}
