'use client'

// 일일 증상 트래킹 폼 — /lifestyle-guide 의 "증상 트래킹" 탭에서 mount.
//
// react-hook-form + zod (PR-B 표준 패턴):
//   - 실시간 onChange 검증 (note 길이 제한 등)
//   - 검증 실패 시 빨간 helper + submit 차단 + toast
//   - 성공 시 toast.success + form 리셋

import { useEffect, useState } from 'react'
import { useForm, Controller } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import toast from 'react-hot-toast'

import api, { showError } from '@/lib/api'
import { dailyLogCreateSchema } from '@/schemas'
import FormError from '@/components/form/FormError'

const MAX_CUSTOM_SYMPTOM_LEN = 20

// 사용자 정의 증상 입력 — preset 외의 자유 텍스트. Enter 또는 추가 버튼.
function CustomSymptomInput({ onAdd }) {
  const [draft, setDraft] = useState('')
  const submit = () => {
    const v = draft.trim()
    if (!v) return
    onAdd(v)
    setDraft('')
  }
  return (
    <div className="flex gap-2">
      <input
        type="text"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') {
            e.preventDefault()
            submit()
          }
        }}
        placeholder="증상 직접 입력 (Enter 또는 추가)"
        maxLength={MAX_CUSTOM_SYMPTOM_LEN}
        className="flex-1 text-sm border border-line rounded-xl px-3 py-2 focus:outline-none focus:border-orange-300"
      />
      <button
        type="button"
        onClick={submit}
        disabled={!draft.trim()}
        className="px-4 rounded-xl text-xs font-bold bg-surface-2 text-ink hover:bg-surface-2 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
      >
        추가
      </button>
    </div>
  )
}

const PRESET_SYMPTOMS = [
  '어지러움', '두통', '구역질', '복통', '설사', '변비',
  '피로감', '수면 장애', '식욕 부진', '발진', '심계항진',
]

// 사용자 정의 칩 (preset 목록에 없는 증상). reset 후에도 유지되도록
// useForm 외부에 보관.
function pickPresetSubset(list) {
  return (list || []).filter((s) => PRESET_SYMPTOMS.includes(s))
}
function pickCustomSubset(list) {
  return (list || []).filter((s) => !PRESET_SYMPTOMS.includes(s))
}

export default function SymptomLogForm({ profileId, initialSymptoms, initialNote, onSaved }) {
  const today = new Date().toISOString().split('T')[0]

  const {
    register,
    handleSubmit,
    control,
    reset,
    formState: { errors, isSubmitting },
  } = useForm({
    resolver: zodResolver(dailyLogCreateSchema),
    mode: 'onChange',
    defaultValues: {
      log_date: today,
      symptoms: initialSymptoms || [],
      note: initialNote || '',
    },
  })

  // 부모가 fetchTodaySymptoms 로 prop 을 갱신할 때마다 form 동기화 — 사용자가
  // 같은 페이지에서 누적 기록 (저장 → 결과 카드 갱신 → 새 기록 추가) 흐름
  // 유지. JSON.stringify dep 으로 ref 변경이 아닌 실제 값 변경에만 반응.
  useEffect(() => {
    reset({
      log_date: today,
      symptoms: initialSymptoms || [],
      note: initialNote || '',
    })
  }, [JSON.stringify(initialSymptoms || []), initialNote || ''])

  const onSubmit = async (values) => {
    if (!profileId) {
      showError('프로필을 먼저 선택해주세요.')
      return
    }
    try {
      await api.post('/api/v1/daily-logs', {
        profile_id: profileId,
        log_date: today,
        symptoms: values.symptoms || [],
        note: values.note || null,
      })
      toast.success('증상 기록이 저장되었습니다.')
      // BE upsert 후 부모가 fetchTodaySymptoms 로 최신 상태를 다시 받아오면
      // 다음 mount 시 prop 으로 반영됨. 명시적 reset 은 폼을 빈 상태로 만들어
      // 누적 UX (이미 저장된 증상을 보면서 추가) 를 깨뜨리므로 호출하지 않음.
      onSaved?.()
    } catch (err) {
      if (err.response?.status === 409) {
        showError('오늘 기록이 이미 있습니다.')
      } else {
        showError('저장에 실패했습니다.')
      }
    }
  }

  const onInvalid = (formErrors) => {
    const first = formErrors.note?.message || formErrors.symptoms?.message
    toast.error(first || '입력값을 다시 확인해주세요.')
  }

  return (
    <form onSubmit={handleSubmit(onSubmit, onInvalid)} className="mt-4 space-y-4">
      <div>
        <p className="text-xs font-bold text-muted mb-2">오늘의 증상 선택</p>
        <Controller
          control={control}
          name="symptoms"
          render={({ field }) => {
            const selected = field.value || []
            const customSelected = pickCustomSubset(selected)
            return (
              <div className="space-y-3">
                {/* preset 칩 — 토글 식 선택/해제 */}
                <div className="flex flex-wrap gap-2">
                  {PRESET_SYMPTOMS.map((s) => {
                    const isOn = selected.includes(s)
                    return (
                      <button
                        key={s}
                        type="button"
                        onClick={() =>
                          field.onChange(
                            isOn
                              ? selected.filter((v) => v !== s)
                              : [...selected, s],
                          )
                        }
                        className={`px-3 py-1.5 rounded-full text-xs font-bold border transition-all cursor-pointer ${
                          isOn
                            ? 'bg-orange-500 text-accent-ink border-orange-500'
                            : 'bg-surface text-muted border-line hover:border-orange-300'
                        }`}
                      >
                        {s}
                      </button>
                    )
                  })}
                </div>

                {/* 사용자 정의 증상 칩 — preset 외 입력값. x 버튼으로 삭제 */}
                {customSelected.length > 0 && (
                  <div className="flex flex-wrap gap-2">
                    {customSelected.map((s) => (
                      <span
                        key={s}
                        className="inline-flex items-center gap-1 pl-3 pr-1 py-1 rounded-full text-xs font-bold border bg-orange-500 text-accent-ink border-orange-500"
                      >
                        {s}
                        <button
                          type="button"
                          aria-label={`'${s}' 증상 삭제`}
                          onClick={() => field.onChange(selected.filter((v) => v !== s))}
                          className="w-5 h-5 flex items-center justify-center rounded-full hover:bg-surface/20 cursor-pointer"
                        >
                          ×
                        </button>
                      </span>
                    ))}
                  </div>
                )}

                {/* 사용자 정의 증상 추가 입력 */}
                <CustomSymptomInput
                  onAdd={(value) => {
                    if (!value) return
                    if (selected.includes(value)) return
                    field.onChange([...selected, value])
                  }}
                />
              </div>
            )
          }}
        />
        <FormError name="symptoms" errors={errors} />
      </div>

      <div>
        <p className="text-xs font-bold text-muted mb-1">메모 (선택)</p>
        <textarea
          {...register('note')}
          placeholder="오늘 몸 상태를 자유롭게 적어보세요"
          maxLength={512}
          rows={3}
          className="w-full text-sm border border-line rounded-xl px-3 py-2 resize-none focus:outline-none focus:border-orange-300"
        />
        <FormError name="note" errors={errors} />
      </div>

      <button
        type="submit"
        disabled={isSubmitting}
        className={`w-full py-3 rounded-xl text-sm font-bold transition-colors ${
          isSubmitting
            ? 'bg-surface-2 text-muted cursor-wait'
            : 'bg-orange-500 text-accent-ink hover:bg-orange-600 cursor-pointer'
        }`}
      >
        {isSubmitting ? '저장 중...' : '오늘 증상 기록하기'}
      </button>
    </form>
  )
}
