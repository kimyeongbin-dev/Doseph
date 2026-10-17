'use client'

import { useRouter } from 'next/navigation'
import { Check, Activity, User, Heart, Loader2, X, Activity as ActivityIcon } from 'lucide-react'
import { useForm, Controller } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import toast from 'react-hot-toast'

import api, { handleApiError } from '@/lib/api'
import { useProfile } from '@/contexts/ProfileContext'
import { healthSurveySchema } from '@/schemas'
import FormError from '@/components/form/FormError'

const CONDITION_OPTIONS = [
  '고혈압',
  '당뇨',
  '고지혈증',
  '심장질환',
  '뇌졸중',
  '천식',
  '신장질환',
  '갑상선질환',
  '없음',
]
const ALLERGY_OPTIONS = ['페니실린', '아스피린', '항생제', '소염제', '없음']

const btnSelected = 'bg-accent text-accent-ink border-accent shadow-lg'
const btnUnselected = 'bg-surface text-muted border-line hover:border-line'
const chipSelected = 'bg-accent text-accent-ink border-accent shadow-md'
const chipUnselected = 'bg-surface text-muted border-line hover:border-line'

// "없음" 선택 시 다른 항목과 mutual exclusion.
function toggleChip(list, item) {
  if (item === '없음') return list.includes('없음') ? [] : ['없음']
  const without = list.filter((v) => v !== '없음')
  return without.includes(item) ? without.filter((v) => v !== item) : [...without, item]
}

export default function SurveyPage() {
  const router = useRouter()
  const { refetchProfiles } = useProfile()

  const {
    register,
    handleSubmit,
    control,
    formState: { errors, isSubmitting },
  } = useForm({
    resolver: zodResolver(healthSurveySchema),
    mode: 'onChange',
    defaultValues: {
      age: '',
      gender: 'MALE',
      height: '',
      weight: '',
      is_smoking: null,
      is_drinking: null,
      conditions: [],
      allergies: [],
    },
  })

  const handleSkip = () => router.push('/main')

  // submit — 검증 통과 후 BE 저장. handleApiError 가 toast 까지 수행.
  const onSubmit = async (values) => {
    try {
      const healthSurvey = {
        age: values.age ?? null,
        gender: values.gender ?? null,
        height: values.height ?? null,
        weight: values.weight ?? null,
        is_smoking: values.is_smoking,
        is_drinking: values.is_drinking,
        conditions: values.conditions?.length ? values.conditions : null,
        allergies: values.allergies?.length ? values.allergies : null,
      }
      const res = await api.get('/api/v1/profiles')
      const selfProfile = res.data.find((p) => p.relation_type === 'SELF')
      if (selfProfile) {
        await api.patch(`/api/v1/profiles/${selfProfile.id}`, { health_survey: healthSurvey })
      }
      toast.success('건강 프로필이 등록되었습니다!')
      if (refetchProfiles) await refetchProfiles()
      router.push('/main')
    } catch (err) {
      handleApiError(err)
    }
  }

  // 실시간 검증 실패 시 submit 차단 + toast — handleSubmit 의 invalid 콜백.
  const onInvalid = (formErrors) => {
    const first = Object.values(formErrors)[0]
    const message = first?.message || '입력값을 다시 확인해주세요.'
    toast.error(message)
  }

  return (
    <div className="min-h-screen bg-surface-2 flex items-center justify-center p-6 relative">
      {isSubmitting && (
        <div className="fixed inset-0 bg-surface/60 backdrop-blur-sm z-[200] flex flex-col items-center justify-center animate-in fade-in duration-300">
          <div className="w-20 h-20 bg-accent rounded-[32px] flex items-center justify-center shadow-2xl mb-6 animate-bounce">
            <ActivityIcon size={40} className="text-accent-ink animate-pulse" />
          </div>
          <p className="text-xl font-black text-ink">건강 프로필을 분석하고 있어요</p>
          <p className="text-muted font-bold mt-2">잠시만 기다려 주세요...</p>
        </div>
      )}

      <form
        onSubmit={handleSubmit(onSubmit, onInvalid)}
        className={`max-w-2xl w-full bg-surface rounded-[40px] shadow-2xl overflow-hidden border border-line transition-all duration-500 ${
          isSubmitting ? 'scale-95 opacity-50' : 'scale-100 opacity-100'
        }`}
      >
        {/* Header */}
        <div className="flex justify-between items-center p-8 border-b border-line">
          <div>
            <h3 className="text-xl font-black text-ink">건강 정보 입력</h3>
            <p className="text-xs font-bold text-muted mt-1">
              맞춤형 관리를 위해 정보를 입력해주세요
            </p>
          </div>
          <button
            type="button"
            onClick={handleSkip}
            className="flex items-center gap-1 text-xs font-black text-muted hover:text-ink transition-all"
          >
            건너뛰기 <X size={14} />
          </button>
        </div>

        <div className="p-8 space-y-8 max-h-[70vh] overflow-y-auto custom-scrollbar">
          {/* 1. 기본 정보 */}
          <div className="space-y-4">
            <h4 className="text-sm font-black text-ink flex items-center gap-2">
              <User size={16} /> 기본 정보
            </h4>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-[10px] font-black text-muted mb-1.5 block ml-1">나이</label>
                <input
                  type="text"
                  inputMode="numeric"
                  placeholder="예: 30"
                  {...register('age')}
                  className="w-full px-5 py-3.5 bg-surface-2 rounded-2xl outline-none font-bold text-ink border-2 border-transparent focus:border-accent transition-all text-sm"
                />
                <FormError name="age" errors={errors} />
              </div>
              <div>
                <label className="text-[10px] font-black text-muted mb-1.5 block ml-1">성별</label>
                <Controller
                  control={control}
                  name="gender"
                  render={({ field }) => (
                    <div className="flex gap-2">
                      {['MALE', 'FEMALE'].map((g) => (
                        <button
                          key={g}
                          type="button"
                          onClick={() => field.onChange(g)}
                          className={`flex-1 py-3.5 rounded-2xl font-bold text-xs border-2 transition-all ${
                            field.value === g ? btnSelected : btnUnselected
                          }`}
                        >
                          {g === 'MALE' ? '남성' : '여성'}
                        </button>
                      ))}
                    </div>
                  )}
                />
                <FormError name="gender" errors={errors} />
              </div>
            </div>
          </div>

          {/* 2. 신체 정보 */}
          <div className="space-y-4">
            <h4 className="text-sm font-black text-ink flex items-center gap-2">
              <Activity size={16} /> 신체 정보
            </h4>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-[10px] font-black text-muted mb-1.5 block ml-1">
                  키 (cm)
                </label>
                <input
                  type="text"
                  inputMode="decimal"
                  placeholder="예: 170"
                  {...register('height')}
                  className="w-full px-5 py-3.5 bg-surface-2 rounded-2xl outline-none font-bold text-ink border-2 border-transparent focus:border-accent transition-all text-sm"
                />
                <FormError name="height" errors={errors} />
              </div>
              <div>
                <label className="text-[10px] font-black text-muted mb-1.5 block ml-1">
                  몸무게 (kg)
                </label>
                <input
                  type="text"
                  inputMode="decimal"
                  placeholder="예: 65.5"
                  {...register('weight')}
                  className="w-full px-5 py-3.5 bg-surface-2 rounded-2xl outline-none font-bold text-ink border-2 border-transparent focus:border-accent transition-all text-sm"
                />
                <FormError name="weight" errors={errors} />
              </div>
            </div>
          </div>

          {/* 3. 생활 습관 */}
          <div className="space-y-4">
            <h4 className="text-sm font-black text-ink flex items-center gap-2">
              <Heart size={16} /> 생활 습관
            </h4>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-[10px] font-black text-muted mb-1.5 block ml-1">
                  흡연 여부
                </label>
                <Controller
                  control={control}
                  name="is_smoking"
                  render={({ field }) => (
                    <div className="flex gap-2">
                      {[true, false].map((v) => (
                        <button
                          key={String(v)}
                          type="button"
                          onClick={() => field.onChange(v)}
                          className={`flex-1 py-3.5 rounded-2xl font-bold text-xs border-2 transition-all ${
                            field.value === v ? btnSelected : btnUnselected
                          }`}
                        >
                          {v ? '흡연' : '비흡연'}
                        </button>
                      ))}
                    </div>
                  )}
                />
              </div>
              <div>
                <label className="text-[10px] font-black text-muted mb-1.5 block ml-1">
                  음주 여부
                </label>
                <Controller
                  control={control}
                  name="is_drinking"
                  render={({ field }) => (
                    <div className="flex gap-2">
                      {[true, false].map((v) => (
                        <button
                          key={String(v)}
                          type="button"
                          onClick={() => field.onChange(v)}
                          className={`flex-1 py-3.5 rounded-2xl font-bold text-xs border-2 transition-all ${
                            field.value === v ? btnSelected : btnUnselected
                          }`}
                        >
                          {v ? '음주' : '비음주'}
                        </button>
                      ))}
                    </div>
                  )}
                />
              </div>
            </div>
          </div>

          {/* 4. 질환 및 알레르기 */}
          <div className="space-y-6">
            <div>
              <label className="text-xs font-black text-muted mb-3 block ml-1">보유 질환</label>
              <Controller
                control={control}
                name="conditions"
                render={({ field }) => (
                  <div className="flex flex-wrap gap-2">
                    {CONDITION_OPTIONS.map((item) => (
                      <button
                        key={item}
                        type="button"
                        onClick={() => field.onChange(toggleChip(field.value || [], item))}
                        className={`px-4 py-2 rounded-full text-[11px] font-black transition-all border-2 ${
                          (field.value || []).includes(item) ? chipSelected : chipUnselected
                        }`}
                      >
                        {item}
                      </button>
                    ))}
                  </div>
                )}
              />
            </div>
            <div>
              <label className="text-xs font-black text-muted mb-3 block ml-1">알레르기</label>
              <Controller
                control={control}
                name="allergies"
                render={({ field }) => (
                  <div className="flex flex-wrap gap-2">
                    {ALLERGY_OPTIONS.map((item) => (
                      <button
                        key={item}
                        type="button"
                        onClick={() => field.onChange(toggleChip(field.value || [], item))}
                        className={`px-4 py-2 rounded-full text-[11px] font-black transition-all border-2 ${
                          (field.value || []).includes(item) ? chipSelected : chipUnselected
                        }`}
                      >
                        {item}
                      </button>
                    ))}
                  </div>
                )}
              />
            </div>
          </div>
        </div>

        {/* Footer Action */}
        <div className="p-8 bg-surface-2 border-t border-line">
          <button
            type="submit"
            disabled={isSubmitting}
            className="w-full py-5 rounded-2xl bg-accent text-accent-ink font-black hover:brightness-110 transition-all shadow-xl flex items-center justify-center gap-2 disabled:opacity-50"
          >
            {isSubmitting ? (
              <div className="flex items-center gap-2">
                <Loader2 className="animate-spin" size={20} /> 처리 중...
              </div>
            ) : (
              <div className="flex items-center gap-2 text-lg">
                시작하기 <Check size={22} />
              </div>
            )}
          </button>
        </div>
      </form>
    </div>
  )
}
