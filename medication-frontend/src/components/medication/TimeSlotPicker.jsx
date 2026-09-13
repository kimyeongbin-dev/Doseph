'use client'
import { useState } from 'react'
import api from '@/lib/api'
import { useMedication } from '@/contexts/MedicationContext'

// ── 복약 시간대 슬롯 정의 ─────────────────────────────────────────────────────
// 각 슬롯은 canonical time 값으로 저장 (DB intake_times 배열과 1:1 대응)
const TIME_SLOTS = [
  { key: 'morning',   label: '아침', time: '08:00' },
  { key: 'afternoon', label: '점심', time: '13:00' },
  { key: 'evening',   label: '저녁', time: '19:00' },
  { key: 'bedtime',   label: '취침', time: '21:00' },
]

// HH:MM 또는 HH:MM:SS 형식을 HH:MM으로 정규화
function normalizeTime(t) {
  return t.substring(0, 5)
}

// ── 복약 시간대 토글 피커 ──────────────────────────────────────────────────────
// 흐름: 슬롯 탭 → 낙관적 상태 업데이트 → PATCH /medications/{id}
//       → MedicationContext 갱신 (홈 화면 즉시 반영)
export default function TimeSlotPicker({ medication }) {
  const { refetchMedications } = useMedication()
  const [currentTimes, setCurrentTimes] = useState(() =>
    (medication.intake_times || []).map(normalizeTime),
  )
  const [saving, setSaving] = useState(false)

  // ── 다른 약 선택 시 시간대 재동기화 ───────────────────────────────────
  // 흐름: medication.id 변화 감지 -> 그 약의 intake_times 로 로컬 상태 재설정
  // effect 가 아니라 React 공식 "prop 변화에 맞춰 렌더 중 state 조정" 패턴.
  // 추가 커밋/재렌더 왕복 없이 같은 렌더에서 즉시 반영된다.
  const [syncedMedicationId, setSyncedMedicationId] = useState(medication.id)
  if (medication.id !== syncedMedicationId) {
    setSyncedMedicationId(medication.id)
    setCurrentTimes((medication.intake_times || []).map(normalizeTime))
  }

  const isActive = (slotTime) => currentTimes.includes(slotTime)

  const toggleSlot = async (slotTime) => {
    if (saving) return

    // 낙관적 업데이트: 서버 응답 전 즉시 UI 반영
    const prev = currentTimes
    const next = isActive(slotTime)
      ? currentTimes.filter((t) => t !== slotTime)
      : [...currentTimes, slotTime].sort()

    setCurrentTimes(next)
    setSaving(true)
    try {
      await api.patch(`/api/v1/medications/${medication.id}`, {
        intake_times: next,
      })
      // 홈 화면 TodaySchedule 즉시 반영을 위해 Context 재조회
      await refetchMedications()
    } catch {
      // 실패 시 롤백
      setCurrentTimes(prev)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="flex items-center gap-1.5 flex-wrap">
      {TIME_SLOTS.map(({ key, label, time }) => (
        <button
          key={key}
          onClick={(e) => {
            e.stopPropagation()
            toggleSlot(time)
          }}
          disabled={saving}
          className={`px-2.5 py-1 rounded-lg text-[10px] font-bold transition-all cursor-pointer disabled:opacity-50 ${
            isActive(time)
              ? 'bg-accent text-accent-ink'
              : 'bg-surface-2 text-muted hover:bg-surface-2'
          }`}
        >
          {label}
        </button>
      ))}
    </div>
  )
}
