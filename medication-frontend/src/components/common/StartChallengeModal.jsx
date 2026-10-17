'use client'
// 챌린지 시작 전 난이도·기간 선택 바텀시트 모달
// AI가 추천한 값을 기본 선택으로 표시하고, 사용자가 직접 조정 후 시작할 수 있음
// Props:
//   challenge  - 시작할 챌린지 객체 (title, description, difficulty, target_days 포함)
//   onConfirm  - (difficulty, targetDays) → void : 확인 버튼 클릭 시 호출
//   onClose    - () → void : 취소 / 오버레이 클릭 시 호출
//   isLoading  - 확인 버튼 처리 중 여부 (버튼 비활성화)
import { useState, useEffect } from 'react'

const DIFFICULTIES = ['쉬움', '보통', '어려움']
const DIFFICULTY_META = {
  쉬움: {
    color: 'bg-blue-500 text-accent-ink border-blue-500',
    idle: 'bg-surface text-blue-500 border-blue-200 hover:border-blue-400',
  },
  보통: {
    color: 'bg-green-500 text-accent-ink border-green-500',
    idle: 'bg-surface text-green-500 border-green-200 hover:border-green-400',
  },
  어려움: {
    color: 'bg-red-500 text-accent-ink border-red-500',
    idle: 'bg-surface text-red-500 border-red-200 hover:border-red-400',
  },
}
const BASE_DURATIONS = [7, 14, 21, 30]

// AI 추천 기간이 표준 옵션에 없으면 목록에 추가
function buildDurationOptions(aiTargetDays) {
  if (!aiTargetDays || BASE_DURATIONS.includes(aiTargetDays)) return BASE_DURATIONS
  const merged = [...BASE_DURATIONS, aiTargetDays].sort((a, b) => a - b)
  return merged
}

export default function StartChallengeModal({ challenge, onConfirm, onClose, isLoading = false }) {
  const [difficulty, setDifficulty] = useState(challenge.difficulty || '보통')
  const [targetDays, setTargetDays] = useState(challenge.target_days || 14)

  const durationOptions = buildDurationOptions(challenge.target_days)
  const aiDifficulty = challenge.difficulty
  const aiTargetDays = challenge.target_days

  // 모달 열릴 때 body 스크롤 잠금
  useEffect(() => {
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = ''
    }
  }, [])

  const handleConfirm = () => {
    if (isLoading) return
    onConfirm(difficulty, targetDays)
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      {/* 딤 처리 오버레이 */}
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />

      {/* 바텀시트 */}
      <div className="relative w-full max-w-lg bg-surface rounded-t-3xl px-5 pt-5 pb-8 shadow-2xl">
        {/* 핸들 바 */}
        <div className="w-10 h-1 bg-surface-2 rounded-full mx-auto mb-5" />

        {/* 챌린지 정보 */}
        <div className="mb-5">
          <p className="text-[10px] font-bold text-muted uppercase tracking-wide mb-1">
            시작할 챌린지
          </p>
          <p className="text-base font-black text-ink leading-snug">{challenge.title}</p>
          {challenge.description && (
            <p className="text-xs text-muted mt-1 leading-relaxed">{challenge.description}</p>
          )}
        </div>

        <div className="h-px bg-surface-2 mb-5" />

        {/* 난이도 선택 */}
        <div className="mb-5">
          <div className="flex items-center gap-1.5 mb-2.5">
            <p className="text-xs font-black text-ink">난이도</p>
            {aiDifficulty && (
              <span className="text-[10px] text-muted">AI 추천: {aiDifficulty}</span>
            )}
          </div>
          <div className="grid grid-cols-3 gap-2">
            {DIFFICULTIES.map((d) => {
              const meta = DIFFICULTY_META[d]
              const isSelected = difficulty === d
              return (
                <button
                  key={d}
                  onClick={() => setDifficulty(d)}
                  className={`py-2.5 rounded-xl text-sm font-bold border-2 transition-all cursor-pointer ${
                    isSelected ? meta.color : meta.idle
                  }`}
                >
                  {d}
                  {d === aiDifficulty && !isSelected && (
                    <span className="block text-[9px] font-normal opacity-60">AI 추천</span>
                  )}
                  {d === aiDifficulty && isSelected && (
                    <span className="block text-[9px] font-normal opacity-80">AI 추천</span>
                  )}
                </button>
              )
            })}
          </div>
        </div>

        {/* 기간 선택 */}
        <div className="mb-6">
          <div className="flex items-center gap-1.5 mb-2.5">
            <p className="text-xs font-black text-ink">목표 기간</p>
            {aiTargetDays && (
              <span className="text-[10px] text-muted">AI 추천: {aiTargetDays}일</span>
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            {durationOptions.map((days) => {
              const isSelected = targetDays === days
              const isAi = days === aiTargetDays
              return (
                <button
                  key={days}
                  onClick={() => setTargetDays(days)}
                  className={`px-4 py-2 rounded-xl text-sm font-bold border-2 transition-all cursor-pointer ${
                    isSelected
                      ? 'bg-accent text-accent-ink border-accent'
                      : 'bg-surface text-muted border-line hover:border-line'
                  }`}
                >
                  {days}일{isAi ? ' ★' : ''}
                </button>
              )
            })}
          </div>
        </div>

        {/* 확인 버튼 */}
        <button
          onClick={handleConfirm}
          disabled={isLoading}
          className={`w-full py-3.5 rounded-2xl text-sm font-black transition-all ${
            isLoading
              ? 'bg-surface-2 text-muted cursor-wait'
              : 'bg-accent text-accent-ink hover:brightness-110 active:scale-[0.98] cursor-pointer'
          }`}
        >
          {isLoading ? '시작하는 중...' : `${difficulty} · ${targetDays}일로 시작하기`}
        </button>

        {/* 취소 */}
        <button
          onClick={onClose}
          className="w-full mt-2 py-2 text-xs text-muted hover:text-muted transition-colors cursor-pointer"
        >
          취소
        </button>
      </div>
    </div>
  )
}
