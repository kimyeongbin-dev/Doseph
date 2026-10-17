'use client'

// /medication/detail?id= — 약품 상세 페이지 (모바일 또는 직접 URL 진입 시).
// 데스크탑에서 처방전 drill-down 으로 진입한 경우는 그 페이지의 우측 panel
// 에서 ``MedicationDetailPanel`` 을 그대로 inline 으로 보여주므로 본 페이지는
// 단독 진입 케이스의 wrapper 만 담당한다.
//
// 정적 export 대응: 동적 세그먼트 [id] 대신 쿼리 파라미터(?id=)를 사용하며,
// useSearchParams 는 <Suspense> 경계 안에서만 호출한다(CSR bailout 규정).

import { Suspense } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'

import BottomNav from '@/components/layout/BottomNav'
import MedicationDetailPanel from '@/components/medication/MedicationDetailPanel'

// ── 약품 상세 본문 (useSearchParams 사용부) ─────────────────────────
// 흐름: URL ?id= 파싱 -> MedicationDetailPanel 렌더 -> 삭제 시 /medication 복귀
function MedicationDetailContent() {
  const router = useRouter()
  const id = useSearchParams().get('id')

  return (
    <main className="min-h-screen bg-surface-2 pb-24">
      <header className="sticky top-0 z-20 bg-surface border-b border-line">
        <div className="max-w-2xl mx-auto px-4 py-3 flex items-center gap-2">
          <button
            onClick={() => router.back()}
            className="p-2 rounded-lg hover:bg-surface-2 cursor-pointer text-ink"
            aria-label="뒤로"
          >
            ←
          </button>
          <h1 className="font-bold text-ink">약품 상세</h1>
        </div>
      </header>

      <div className="max-w-2xl mx-auto px-4 py-6">
        <MedicationDetailPanel medicationId={id} onDeleted={() => router.push('/medication')} />
      </div>

      <BottomNav />
    </main>
  )
}

export default function MedicationDetailPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-surface-2" />}>
      <MedicationDetailContent />
    </Suspense>
  )
}
