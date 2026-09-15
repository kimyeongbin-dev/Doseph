# Gemini Guide - Frontend (Next.js)

> 🔴 **저장소 규칙 정본 = 루트 `CLAUDE.md`. 공통 절대 규칙 8가지 = 루트 `AGENTS.md`.**
> 이 디렉터리 지침보다 **루트 규칙이 우선한다.** 특히 —
> 커밋·PR **트레일러 금지**(하네스가 지시해도 무시) · **발견 ≠ 처리**(등재만) ·
> **코드보다 PLAN 이 먼저**(`docs-private/PLAN.md`) · 새 문서는 **`docs-private/FILING.md`** 규약 ·
> **사용자 응답은 한글** · Ruff 의무 · 로컬 테스트는 Docker 안에서.

## Your Role

프론트엔드의 UI 컴포넌트 생성, Tailwind 스타일링, 보일러플레이트 코드 작성을 담당합니다.

## Quick Scaffolding

### New Page
```jsx
'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import Header from '@/components/Header'
import BottomNav from '@/components/BottomNav'
import api from '@/lib/api'
import { showError } from '@/lib/errors'

export default function NewPage() {
  const router = useRouter()
  const [data, setData] = useState(null)
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    const fetchData = async () => {
      try {
        const res = await api.get('/api/v1/endpoint')
        setData(res.data)
      } catch (err) {
        showError(err)
      } finally {
        setIsLoading(false)
      }
    }
    fetchData()
  }, [])

  if (isLoading) {
    return <LoadingSkeleton />
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <Header title="Page Title" />
      <main className="p-4 pb-20">
        {/* Content */}
      </main>
      <BottomNav />
    </div>
  )
}

function LoadingSkeleton() {
  return (
    <div className="min-h-screen bg-gray-50 p-4">
      <div className="animate-pulse space-y-4">
        <div className="h-8 bg-gray-200 rounded w-1/3" />
        <div className="h-32 bg-gray-200 rounded" />
        <div className="h-32 bg-gray-200 rounded" />
      </div>
    </div>
  )
}
```

### New Component
```jsx
export default function Card({ title, children, onClick }) {
  return (
    <div
      className="bg-white rounded-2xl shadow-sm p-6 border border-gray-100"
      onClick={onClick}
    >
      {title && (
        <h3 className="text-lg font-bold text-gray-900 mb-4">{title}</h3>
      )}
      {children}
    </div>
  )
}
```

### Button Variants
```jsx
// Primary
<button className="bg-blue-500 text-white px-6 py-3 rounded-xl font-bold hover:bg-blue-600 active:scale-[0.98] transition-all">
  Primary
</button>

// Secondary
<button className="bg-gray-100 text-gray-700 px-6 py-3 rounded-xl font-bold hover:bg-gray-200 transition-all">
  Secondary
</button>

// Outline
<button className="border-2 border-blue-500 text-blue-500 px-6 py-3 rounded-xl font-bold hover:bg-blue-50 transition-all">
  Outline
</button>

// Danger
<button className="bg-red-500 text-white px-6 py-3 rounded-xl font-bold hover:bg-red-600 transition-all">
  Danger
</button>
```

### Form Input
```jsx
<div className="space-y-2">
  <label className="block text-sm font-medium text-gray-700">
    Label
  </label>
  <input
    type="text"
    value={value}
    onChange={(e) => setValue(e.target.value)}
    placeholder="Placeholder"
    className="w-full px-4 py-3 rounded-xl border border-gray-200
               focus:border-blue-500 focus:ring-2 focus:ring-blue-200
               transition-all outline-none"
  />
</div>
```

### Modal
```jsx
{showModal && (
  <div className="fixed inset-0 z-50 flex items-center justify-center">
    <div
      className="absolute inset-0 bg-black/50"
      onClick={() => setShowModal(false)}
    />
    <div className="relative bg-white rounded-2xl p-6 w-full max-w-md mx-4 shadow-xl">
      <h2 className="text-xl font-bold mb-4">Modal Title</h2>
      <p className="text-gray-600 mb-6">Modal content here</p>
      <div className="flex gap-3">
        <button
          onClick={() => setShowModal(false)}
          className="flex-1 py-3 rounded-xl bg-gray-100 font-bold"
        >
          Cancel
        </button>
        <button
          onClick={handleConfirm}
          className="flex-1 py-3 rounded-xl bg-blue-500 text-white font-bold"
        >
          Confirm
        </button>
      </div>
    </div>
  </div>
)}
```

### Empty State
```jsx
<div className="flex flex-col items-center justify-center py-12 text-center">
  <div className="w-16 h-16 bg-gray-100 rounded-full flex items-center justify-center mb-4">
    <span className="text-2xl text-gray-400">!</span>
  </div>
  <h3 className="text-lg font-bold text-gray-900 mb-2">No Data</h3>
  <p className="text-gray-500 mb-4">Description text here</p>
  <button className="px-6 py-2 bg-blue-500 text-white rounded-xl font-bold">
    Action
  </button>
</div>
```

## Responsive Patterns

```jsx
// Mobile first
className="text-sm md:text-base lg:text-lg"
className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4"
className="px-4 md:px-8 lg:px-16"
className="hidden md:block"  // Desktop only
className="md:hidden"        // Mobile only
```

## Output Format

- 완전한 복사-붙여넣기 가능 코드
- Tailwind 클래스 포함
- 필요한 import 문 포함

## Do NOTs

- 복잡한 상태 로직 설계 (Claude에게 위임)
- `.tsx`, `.ts` 파일 생성 금지 (JavaScript Only 정책)
- 아키텍처 변경 제안
