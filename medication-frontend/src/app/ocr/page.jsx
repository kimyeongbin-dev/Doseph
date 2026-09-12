'use client'
import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { Info, Camera } from 'lucide-react'

import Header from '@/components/layout/Header'
import { useConfirm } from '@/components/common/ConfirmDialog'

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
  const [isLoading, setIsLoading] = useState(true)
  const [preview, setPreview] = useState(null)
  const [file, setFile] = useState(null)

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
    }
  }

  const handleAnalyze = () => {
    if (!file) return
    sessionStorage.setItem('ocrFileName', file.name)
    sessionStorage.setItem('ocrFileType', file.type)
    const reader = new FileReader()
    reader.onload = (e) => {
      sessionStorage.setItem('ocrFileData', e.target.result)
      router.push('/ocr/loading')
    }
    reader.readAsDataURL(file)
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
              '처방전 사진을 업로드하세요',
              'AI가 약품 정보를 자동으로 인식해요',
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
            <input
              type="file"
              accept="image/*"
              onChange={handleFileChange}
              className="hidden"
            />
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

        {/* [신규 추가] 직접 입력 안내 배너 */}
        <div className="mt-8 bg-blue-50 rounded-2xl p-4 flex items-center gap-3 shadow-sm border border-blue-100">
          <span className="text-2xl">💡</span>
          <div className="flex-1">
            <p className="font-bold text-blue-800 text-sm mb-1">사진 촬영이 어렵다면?</p>
            <p className="text-blue-700 text-xs">처방전이 없거나 인식이 어려운 약품은 아래 버튼을 눌러 직접 입력할 수 있어요.</p>
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
            disabled={!preview}
            className={`flex-1 py-4 rounded-xl text-sm font-bold transition-all active:scale-[0.98] cursor-pointer
              ${preview
                ? 'bg-accent text-accent-ink hover:brightness-110'
                : 'bg-surface-2 text-muted cursor-not-allowed'
              }`}
          >
            분석 시작하기
          </button>
        </div>
      </div>
    </main>
  )
}
