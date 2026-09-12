'use client'

// /ocr/result — OCR 결과 확인 + 수정 + 저장 (react-hook-form + zod 표준 적용).
import { useEffect, Suspense, useState, useRef } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { Trash2 } from 'lucide-react'
import { Controller, useFieldArray, useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import toast from 'react-hot-toast'

import BottomNav from '@/components/layout/BottomNav'
import api from '@/lib/api'
import { streamSSE } from '@/lib/sseClient'
import { useProfile } from '@/contexts/ProfileContext'
import { useMedication } from '@/contexts/MedicationContext'
import { useOcrDraft } from '@/contexts/OcrDraftContext'
import { medicationEditPatchSchema } from '@/schemas'
import FormError from '@/components/form/FormError'
import MedicineNameAutocomplete from '@/components/medication/MedicineNameAutocomplete'

const TERMINAL_ERROR_MESSAGES = {
  no_text: '이미지에서 텍스트를 찾지 못했어요.',
  no_candidates: '약품 정보를 인식하지 못했어요.',
  failed: '처리 중 오류가 발생했어요.',
}

const ocrConfirmSchema = z.object({
  prescription_date: z.string().optional().or(z.literal('')),
  prescription_hospital: z.string().max(128, '최대 128자까지 가능해요').optional().or(z.literal('')).nullable(),
  prescription_department: z.string().max(64, '최대 64자까지 가능해요').optional().or(z.literal('')).nullable(),
  meds: z.array(medicationEditPatchSchema).min(1, '약품을 최소 1개 입력해주세요'),
})

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
    if (!timedOut) return
  }
}

function ResultSkeleton() {
  return (
    <div className="min-h-screen bg-surface-2 pb-32 animate-pulse">
      <div className="h-48 bg-surface border-b border-line" />
      <div className="max-w-3xl mx-auto px-6 py-12">
        <div className="flex justify-between items-center mb-8 px-1">
          <div className="h-6 w-32 bg-surface-2 rounded-lg" />
          <div className="h-6 w-20 bg-surface-2 rounded-lg" />
        </div>
        <div className="space-y-6">
          {[1, 2].map((i) => (
            <div key={i} className="h-48 bg-surface rounded-3xl border border-line shadow-sm" />
          ))}
        </div>
        <div className="mt-12 flex gap-4">
          <div className="flex-1 h-16 bg-surface border border-line rounded-2xl" />
          <div className="flex-1 h-16 bg-blue-100 rounded-2xl" />
        </div>
      </div>
    </div>
  )
}

const EMPTY_MED = {
  medicine_name: '',
  dose_per_intake: '',
  daily_intake_count: '',
  total_intake_days: '',
  intake_instruction: '식후 30분',
  category: '',
}

function OcrResultContent() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const draftId = searchParams.get('draft_id')
  const { selectedProfileId } = useProfile()
  const { refetchMedications } = useMedication()
  const { removeDraftLocally, refetchDrafts } = useOcrDraft()

  // 💡 스트림 제어와 재시도 쿨다운을 위한 상태 추가
  const streamControllerRef = useRef(null)
  const [isRetaking, setIsRetaking] = useState(false)

  // 커스텀 UI 에러 관리
  const [customErrors, setCustomErrors] = useState({})

  const {
    control,
    register,
    handleSubmit,
    reset,
    setValue,
    formState: { errors, isSubmitting },
  } = useForm({
    resolver: zodResolver(ocrConfirmSchema),
    mode: 'onChange',
    defaultValues: {
      prescription_date: new Date().toISOString().split('T')[0],
      prescription_hospital: '',
      prescription_department: '',
      meds: [],
    },
  })
  const { fields, append, remove } = useFieldArray({ control, name: 'meds' })

  const initialized = fields.length > 0 || draftId === 'manual'

  useEffect(() => {
    if (!draftId) {
      router.push('/ocr')
      return
    }
    if (draftId === 'manual') {
      reset({
        prescription_date: new Date().toISOString().split('T')[0],
        prescription_hospital: '',
        prescription_department: '',
        meds: [{ ...EMPTY_MED }],
      })
      return
    }

    const abortController = new AbortController()
    streamControllerRef.current = abortController // 💡 외부 차단용 Ref 연결

    const consumeStream = async () => {
      try {
        for await (const payload of watchDraftStatus(draftId, selectedProfileId, abortController.signal)) {
          const { status, medicines } = payload
          if (status === 'ready') {
            const firstDept = medicines?.find?.((m) => m?.department)?.department || ''
            reset({
              prescription_date:
                medicines?.[0]?.dispensed_date || new Date().toISOString().split('T')[0],
              prescription_hospital: '',
              prescription_department: firstDept,
              meds: (medicines || []).map((m) => ({
                medicine_name: m.medicine_name || '',
                dose_per_intake: m.dose_per_intake || '',
                daily_intake_count: m.daily_intake_count ?? '',
                total_intake_days: m.total_intake_days ?? '',
                intake_instruction: m.intake_instruction || '식후 30분',
                category: m.category || '',
              })),
            })
            return
          }
          if (status in TERMINAL_ERROR_MESSAGES) {
            toast.error(`${TERMINAL_ERROR_MESSAGES[status]} 다시 촬영해주세요.`)
            router.push('/ocr')
            return
          }
        }
      } catch (err) {
        if (abortController.signal.aborted) return // 💡 강제 차단 시 에러 무시
        toast.error('데이터가 만료되었거나 불러올 수 없습니다. 다시 촬영해주세요.')
        router.push('/ocr')
      }
    }
    consumeStream()

    return () => {
      abortController.abort()
      streamControllerRef.current = null
    }
  }, [draftId, router, selectedProfileId, reset])

  // 💡 악의적 연타 및 좀비 스트림 차단 로직 적용
  const handleRetake = async () => {
    const now = Date.now()
    const lastRetakeTime = sessionStorage.getItem('last_retake_time')
    const COOLDOWN_MS = 5000 // 5초 쿨다운

    if (lastRetakeTime && now - parseInt(lastRetakeTime, 10) < COOLDOWN_MS) {
      const remainSec = Math.ceil((COOLDOWN_MS - (now - parseInt(lastRetakeTime, 10))) / 1000)
      toast.error(`너무 잦은 재시도입니다. ${remainSec}초 후 다시 시도해주세요.`)
      return
    }

    // 화면에 옛날 데이터가 덮어씌워지지 않도록 스트림의 숨통을 즉시 끊음
    if (streamControllerRef.current) {
      streamControllerRef.current.abort()
    }

    setIsRetaking(true)
    sessionStorage.setItem('last_retake_time', now.toString())

    if (draftId && draftId !== 'manual') {
      try {
        await api.delete(`/api/v1/ocr/draft/${draftId}`, {
          params: selectedProfileId ? { profile_id: selectedProfileId } : undefined,
        })
      } catch {
        // 무시
      }
    }
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination -- OCR 재촬영: 전체 리로드로 진행 상태 초기화 의도
    window.location.href = '/ocr'
  }

  const onInvalid = (formErrors) => {
    const dig = (obj) => {
      if (!obj) return null
      if (typeof obj === 'object' && 'message' in obj && obj.message) return obj.message
      for (const v of Object.values(obj)) {
        const r = dig(v)
        if (r) return r
      }
      return null
    }
    toast.error(dig(formErrors) || '입력값을 다시 확인해주세요.')
  }

  const onSubmit = async (values) => {
    if (Object.keys(customErrors).length > 0) {
      toast.error('입력된 값을 다시 확인해주세요.')
      return
    }

    if (draftId === 'manual' && !selectedProfileId) {
      toast.error('프로필을 선택한 후 다시 시도해주세요.')
      return
    }

    const toIntOrNull = (v) => {
      if (v === '' || v === null || v === undefined) return null
      const n = parseInt(v, 10)
      return Number.isNaN(n) ? null : n
    }

    const toStrOrNull = (v) => {
      if (v === null || v === undefined) return null;
      if (typeof v === 'string' && v.trim() === '') return null;
      return typeof v === 'string' ? v.trim() : v;
    }

    const confirmedMedicines = values.meds.map((med) => ({
      ...med,
      medicine_name: med.medicine_name?.trim() ?? '',
      dose_per_intake: toStrOrNull(med.dose_per_intake),
      daily_intake_count: toIntOrNull(med.daily_intake_count),
      total_intake_days: toIntOrNull(med.total_intake_days),
      intake_instruction: toStrOrNull(med.intake_instruction),
      category: toStrOrNull(med.category),
      department: toStrOrNull(values.prescription_department),
      dispensed_date: values.prescription_date || null,
    }))

    try {
      if (draftId === 'manual') {
        let succeeded = 0
        for (const med of confirmedMedicines) {
          const dailyCount = parseInt(med.daily_intake_count, 10) || 1
          const days = parseInt(med.total_intake_days, 10) || 1
          const startDate = med.dispensed_date || new Date().toISOString().split('T')[0]

          let intakeTimes = []
          if (dailyCount === 1) intakeTimes = ['08:00']
          else if (dailyCount === 2) intakeTimes = ['08:00', '19:00']
          else if (dailyCount === 3) intakeTimes = ['08:00', '13:00', '19:00']
          else {
            const step = 14 / (dailyCount - 1)
            intakeTimes = Array.from({ length: dailyCount }, (_, i) => {
              const hour = Math.round(8 + i * step)
              return `${String(hour).padStart(2, '0')}:00`
            })
          }

          try {
            await api.post('/api/v1/medications', {
              ...med,
              profile_id: selectedProfileId,
              start_date: startDate,
              total_intake_count: dailyCount * days,
              intake_times: intakeTimes,
            })
            succeeded += 1
          } catch (err) {
            const remaining = confirmedMedicines.length - succeeded
            toast.error(
              `${succeeded}개 저장 후 실패했습니다. 남은 ${remaining}개는 저장되지 않았습니다.`,
            )
            throw err
          }
        }
      } else {
        await api.post(
          '/api/v1/ocr/confirm',
          {
            draft_id: draftId,
            confirmed_medicines: confirmedMedicines,
            hospital_name: toStrOrNull(values.prescription_hospital),
            department: toStrOrNull(values.prescription_department),
          },
          {
            timeout: 60000,
            params: selectedProfileId ? { profile_id: selectedProfileId } : undefined,
          },
        )
        sessionStorage.setItem('ocr_consumed_draft_id', draftId)
      }

      // confirm 직후 draft cache 즉시 정리 — useOcrEntryNavigator 가 다음 진입 시
      // stale 한 옛 draft 로 보내는 회귀 차단. sessionStorage marker 는 다음
      // OcrDraftProvider 마운트 시점 백업이므로 여기서 immediate cleanup 우선.
      if (draftId) removeDraftLocally(draftId)
      refetchDrafts()
      await refetchMedications()
      toast.success('저장 완료! 복약 목록에서 확인해보세요.')
      router.push('/medication')
    } catch {
      toast.error('저장 중 오류가 발생했습니다.')
    }
  }

  const handleCustomError = (key, message) => {
    setCustomErrors(prev => ({ ...prev, [key]: message }))
  }
  const clearCustomError = (key) => {
    setCustomErrors(prev => {
      const newErrors = { ...prev }
      delete newErrors[key]
      return newErrors
    })
  }

  if (!initialized) return <ResultSkeleton />

  return (
    <main className="min-h-screen bg-surface-2 pb-24">
      <form onSubmit={handleSubmit(onSubmit, onInvalid)}>
        <div className="bg-surface border-b border-line px-10 py-4 flex items-center gap-4">
          <button
            type="button"
            onClick={() => router.push('/main')}
            className="text-muted hover:text-black cursor-pointer text-xl"
            aria-label="메인으로 이동"
          >
            ←
          </button>
          <div>
            <h1 className="font-bold text-ink">처방전 확인 및 수정</h1>
            <p className="text-xs text-muted">오탈자가 있다면 직접 수정해주세요</p>
          </div>
        </div>

        <div className="max-w-3xl mx-auto px-10 py-8 space-y-4">
          <div className="bg-blue-50 rounded-2xl p-4 flex items-center gap-3">
            <span className="text-2xl">!</span>
            <div>
              <p className="font-semibold text-blue-800 text-sm">확인해주세요!</p>
              <p className="text-blue-600 text-xs">AI가 인식한 결과입니다. 틀린 글자는 터치해서 고칠 수 있어요.</p>
            </div>
          </div>

          <div className="bg-surface rounded-2xl p-5 border border-line flex items-center justify-between gap-4">
            <div>
              <p className="text-sm font-bold text-ink">처방일</p>
              <p className="text-xs text-muted mt-0.5">처방전에 적힌 날짜를 확인해주세요</p>
            </div>
            <input
              type="date"
              {...register('prescription_date')}
              className="text-base font-bold text-ink border border-line rounded-xl px-3 py-2 focus:outline-none focus:border-blue-400 focus:ring-1 focus:ring-blue-100 bg-surface-2"
            />
          </div>

          <div className="bg-surface rounded-2xl p-5 border border-line flex items-center justify-between gap-4">
            <div>
              <p className="text-sm font-bold text-ink">병원</p>
              <p className="text-xs text-muted mt-0.5">비워두면 &lsquo;미상&rsquo; 으로 등록됩니다</p>
            </div>
            <div>
              <input
                type="text"
                {...register('prescription_hospital')}
                onChange={(e) => {
                  const rawValue = e.target.value;
                  const hasError = /[^a-zA-Z가-힣ㄱ-ㅎㅏ-ㅣ\s]/.test(rawValue);

                  if (hasError) {
                    handleCustomError('prescription_hospital', '숫자와 특수문자는 불가합니다.');
                  } else {
                    clearCustomError('prescription_hospital');
                  }

                  const sanitizedValue = rawValue.replace(/[^a-zA-Z가-힣ㄱ-ㅎㅏ-ㅣ\s]/g, '');
                  e.target.value = sanitizedValue;
                  setValue('prescription_hospital', sanitizedValue, { shouldDirty: true });
                }}
                placeholder="예: 서울내과의원"
                maxLength={128}
                className="text-base font-bold text-ink border border-line rounded-xl px-3 py-2 focus:outline-none focus:border-blue-400 focus:ring-1 focus:ring-blue-100 bg-surface-2 w-56"
              />
              <div className="mt-1 h-4">
                {customErrors['prescription_hospital'] ? (
                  <p className="text-red-500 text-xs font-bold">{customErrors['prescription_hospital']}</p>
                ) : (
                  <FormError name="prescription_hospital" errors={errors} className="text-red-500 text-xs font-bold" />
                )}
              </div>
            </div>
          </div>

          <div className="bg-surface rounded-2xl p-5 border border-line flex items-center justify-between gap-4">
            <div>
              <p className="text-sm font-bold text-ink">진료과</p>
              <p className="text-xs text-muted mt-0.5">비워두면 &lsquo;미상&rsquo; 으로 등록됩니다</p>
            </div>
            <div>
              <input
                type="text"
                {...register('prescription_department')}
                onChange={(e) => {
                  const rawValue = e.target.value;
                  const hasError = /[^a-zA-Z가-힣ㄱ-ㅎㅏ-ㅣ\s]/.test(rawValue);

                  if (hasError) {
                    handleCustomError('prescription_department', '숫자와 특수문자는 불가합니다.');
                  } else {
                    clearCustomError('prescription_department');
                  }

                  const sanitizedValue = rawValue.replace(/[^a-zA-Z가-힣ㄱ-ㅎㅏ-ㅣ\s]/g, '');
                  e.target.value = sanitizedValue;
                  setValue('prescription_department', sanitizedValue, { shouldDirty: true });
                }}
                placeholder="예: 내과"
                maxLength={64}
                className="text-base font-bold text-ink border border-line rounded-xl px-3 py-2 focus:outline-none focus:border-blue-400 focus:ring-1 focus:ring-blue-100 bg-surface-2 w-40"
              />
              <div className="mt-1 h-4">
                {customErrors['prescription_department'] ? (
                  <p className="text-red-500 text-xs font-bold">{customErrors['prescription_department']}</p>
                ) : (
                  <FormError name="prescription_department" errors={errors} className="text-red-500 text-xs font-bold" />
                )}
              </div>
            </div>
          </div>

          <div className="space-y-4 mb-4">
            {fields.map((field, i) => (
              <div
                key={field.id}
                className="bg-surface rounded-2xl p-6 shadow-sm border border-line animate-in fade-in slide-in-from-bottom-2 duration-300"
              >
                <div className="flex justify-between items-start mb-4 gap-4">
                  <div className="flex-1">
                    <Controller
                      control={control}
                      name={`meds.${i}.medicine_name`}
                      render={({ field }) => (
                        <MedicineNameAutocomplete
                          value={field.value}
                          onChange={field.onChange}
                          placeholder="약품명 입력"
                          inputClassName="font-bold text-lg text-ink border-b-2 border-transparent hover:border-blue-200 focus:border-blue-500 focus:outline-none bg-transparent w-full transition-colors"
                        />
                      )}
                    />
                    <FormError name={`meds.${i}.medicine_name`} errors={errors} />
                  </div>
                  <button
                    type="button"
                    onClick={() => remove(i)}
                    className="text-muted hover:text-red-400 mt-1 cursor-pointer"
                  >
                    <Trash2 size={20} />
                  </button>
                </div>

                <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                  <div className="bg-surface-2 p-2 rounded-xl border border-line">
                    <p className="text-[10px] text-muted mb-1 px-1">1회 복용량</p>
                    <input
                      type="text"
                      {...register(`meds.${i}.dose_per_intake`)}
                      onChange={(e) => {
                        let val = e.target.value.replace(/[^0-9.]/g, '');
                        const parts = val.split('.');
                        if (parts.length > 2) val = parts[0] + '.' + parts.slice(1).join('');

                        const numVal = parseFloat(val);

                        if (!isNaN(numVal) && numVal > 100) {
                           e.target.value = '';
                           setValue(`meds.${i}.dose_per_intake`, '', { shouldDirty: true });
                           handleCustomError(`dose_${i}`, '최대 100까지 가능합니다.');
                        } else {
                           clearCustomError(`dose_${i}`);
                           e.target.value = val;
                           setValue(`meds.${i}.dose_per_intake`, val, { shouldDirty: true });
                        }
                      }}
                      className="text-sm font-bold text-ink bg-transparent w-full focus:outline-none focus:text-blue-600 px-1"
                      placeholder="예: 1"
                    />
                    <div className="mt-1 px-1 h-4">
                      {customErrors[`dose_${i}`] ? (
                        <p className="text-red-500 text-xs font-bold">{customErrors[`dose_${i}`]}</p>
                      ) : (
                        <FormError name={`meds.${i}.dose_per_intake`} errors={errors} className="text-red-500 text-xs font-bold" />
                      )}
                    </div>
                  </div>

                  <div className="bg-surface-2 p-2 rounded-xl border border-line">
                    <p className="text-[10px] text-muted mb-1 px-1">1일 복용 횟수</p>
                    <input
                      type="text"
                      inputMode="numeric"
                      {...register(`meds.${i}.daily_intake_count`)}
                      onChange={(e) => {
                        let val = e.target.value.replace(/[^0-9]/g, '');
                        const numVal = parseInt(val, 10);

                        if (!isNaN(numVal) && numVal > 24) {
                          e.target.value = '';
                          setValue(`meds.${i}.daily_intake_count`, '', { shouldDirty: true });
                          handleCustomError(`freq_${i}`, '최대 24회까지 가능합니다.');
                        } else {
                          clearCustomError(`freq_${i}`);
                          e.target.value = val;
                          setValue(`meds.${i}.daily_intake_count`, val, { shouldDirty: true });
                        }
                      }}
                      className="text-sm font-bold text-ink bg-transparent w-full focus:outline-none focus:text-blue-600 px-1"
                      placeholder="예: 3"
                    />
                    <div className="mt-1 px-1 h-4">
                      {customErrors[`freq_${i}`] ? (
                        <p className="text-red-500 text-xs font-bold">{customErrors[`freq_${i}`]}</p>
                      ) : (
                        <FormError name={`meds.${i}.daily_intake_count`} errors={errors} className="text-red-500 text-xs font-bold" />
                      )}
                    </div>
                  </div>

                  <div className="bg-surface-2 p-2 rounded-xl border border-line">
                    <p className="text-[10px] text-muted mb-1 px-1">총 복용 일수</p>
                    <input
                      type="text"
                      inputMode="numeric"
                      {...register(`meds.${i}.total_intake_days`)}
                      onChange={(e) => {
                        let val = e.target.value.replace(/[^0-9]/g, '');
                        const numVal = parseInt(val, 10);

                        if (!isNaN(numVal) && numVal > 365) {
                          e.target.value = '';
                          setValue(`meds.${i}.total_intake_days`, '', { shouldDirty: true });
                          handleCustomError(`days_${i}`, '최대 365일까지 가능합니다.');
                        } else {
                          clearCustomError(`days_${i}`);
                          e.target.value = val;
                          setValue(`meds.${i}.total_intake_days`, val, { shouldDirty: true });
                        }
                      }}
                      className="text-sm font-bold text-ink bg-transparent w-full focus:outline-none focus:text-blue-600 px-1"
                      placeholder="예: 5"
                    />
                    <div className="mt-1 px-1 h-4">
                      {customErrors[`days_${i}`] ? (
                        <p className="text-red-500 text-xs font-bold">{customErrors[`days_${i}`]}</p>
                      ) : (
                        <FormError name={`meds.${i}.total_intake_days`} errors={errors} className="text-red-500 text-xs font-bold" />
                      )}
                    </div>
                  </div>

                  <div className="bg-surface-2 p-2 rounded-xl border border-line">
                    <p className="text-[10px] text-muted mb-1 px-1">복용 방법</p>
                    <select
                      {...register(`meds.${i}.intake_instruction`)}
                      className="text-sm font-bold text-ink bg-transparent w-full focus:outline-none focus:text-blue-600 px-1 cursor-pointer"
                    >
                      <option value="" disabled hidden>선택해주세요</option>
                      <option value="식후 30분">식후 30분</option>
                      <option value="식전 30분">식전 30분</option>
                      <option value="식사 직후">식사 직후</option>
                      <option value="공복">공복</option>
                      <option value="취침 전">취침 전</option>
                      <option value="필요 시">필요 시</option>
                      <option value="기타">기타</option>
                    </select>
                  </div>
                </div>
              </div>
            ))}

            <div className="mt-6 mb-2 bg-blue-50 rounded-2xl p-4 flex items-center gap-3 shadow-sm border border-blue-100">
              <span className="text-2xl">💡</span>
              <div className="flex-1">
                <p className="font-bold text-blue-800 text-sm mb-1">인식되지 않은 약이 있나요?</p>
                <p className="text-blue-700 text-xs">
                  누락된 약품이 있다면 아래의 <span className="font-bold text-blue-800">+ 직접 약품 추가하기</span> 버튼을 눌러 꼭 입력해 주세요!
                </p>
              </div>
            </div>

            <button
              type="button"
              onClick={() => append({ ...EMPTY_MED })}
              className="w-full bg-surface rounded-2xl p-4 border-2 border-dashed border-blue-300 text-blue-500 font-bold hover:bg-blue-50 hover:border-blue-400 transition-colors flex items-center justify-center gap-2 cursor-pointer shadow-sm mb-10"
            >
              <span className="text-xl">+</span> 직접 약품 추가하기
            </button>
          </div>

          <div className="flex gap-3 pb-10">
            {/* 💡 버튼 상태 연결 및 로딩 문구 처리 */}
            <button
              type="button"
              onClick={handleRetake}
              disabled={isRetaking}
              className="flex-1 bg-surface border border-line py-4 rounded-xl text-muted text-sm font-bold cursor-pointer hover:bg-surface-2 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isRetaking ? '정리 중...' : '다시 촬영'}
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="flex-1 bg-accent text-accent-ink py-4 rounded-xl font-semibold transition-all active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed enabled:hover:brightness-110 enabled:cursor-pointer"
            >
              {isSubmitting ? '저장 중...' : '수정 완료 및 저장'}
            </button>
          </div>
        </div>
      </form>

      <BottomNav />
    </main>
  )
}

export default function OcrResultPage() {
  return (
    <Suspense fallback={<ResultSkeleton />}>
      <OcrResultContent />
    </Suspense>
  )
}
