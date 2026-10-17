'use client'

// 공통 건강 설문 모달.
// - 첫 로그인 시 메인 페이지에서 호출 (showSkip=true, title='건강 정보 입력')
// - 마이페이지의 "건강 프로필 수정" 에서도 호출 (showSkip=false, title='건강 프로필 수정')
// 두 곳에서 같은 칩 옵션·검증·UI 를 공유하기 위해 단일 컴포넌트로 통합.
//
// onSave(values) 콜백만 호출 — createProfile/updateProfile 분기는 호출 측에서.

import { Controller, useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { X } from 'lucide-react'
import FormError from '@/components/form/FormError'
import { healthSurveySchema } from '@/schemas'

// 기저질환·알레르기 칩 옵션 — 두 진입점에서 동일하게 사용.
// 각 칩은 BE 에서 free-form 문자열로 health_survey.conditions/allergies JSONField 에 저장.
const CONDITION_OPTIONS = [
  '고혈압',
  '당뇨',
  '고지혈증',
  '심장질환',
  '뇌졸중',
  '천식',
  '신장질환',
  '간질환',
  '갑상선질환',
  '없음',
]
const ALLERGY_OPTIONS = ['페니실린', '아스피린', '항생제', '소염제', '없음']

const btnSelected = 'bg-accent text-accent-ink border-accent'
const btnUnselected = 'bg-surface text-muted border-line hover:border-line'
const chipSelected = 'bg-accent text-accent-ink border-accent'
const chipUnselected = 'bg-surface text-muted border-line hover:border-line'

// "없음" 칩과 다른 항목의 mutually-exclusive 토글.
function toggleChip(list, item) {
  if (item === '없음') return list.includes('없음') ? [] : ['없음']
  const without = list.filter((v) => v !== '없음')
  return without.includes(item) ? without.filter((v) => v !== item) : [...without, item]
}

export default function HealthSurveyModal({
  info,
  onClose,
  onSave,
  onSkip,
  title = '건강 프로필 수정',
  subtitle,
  showSkip = false,
  saveLabel = '저장하기',
  skipLabel = '건너뛰기',
  cancelLabel = '취소',
  isSubmitting = false,
}) {
  const {
    register,
    control,
    handleSubmit,
    formState: { errors, isValid },
  } = useForm({
    resolver: zodResolver(healthSurveySchema),
    mode: 'onChange',
    defaultValues: {
      age: info?.age?.toString() || '',
      gender: info?.gender || 'MALE',
      height: info?.height?.toString() || '',
      weight: info?.weight?.toString() || '',
      is_smoking: info?.is_smoking ?? null,
      is_drinking: info?.is_drinking ?? null,
      conditions: info?.conditions || [],
      allergies: info?.allergies || [],
    },
  })

  const onSubmit = (values) => onSave(values)

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-[100] flex items-center justify-center p-4">
      <div className="bg-surface rounded-[40px] w-full max-w-lg max-h-[90vh] overflow-hidden shadow-2xl flex flex-col animate-in fade-in zoom-in duration-200">
        {/* 헤더 */}
        <div className="flex justify-between items-start p-8 border-b border-line shrink-0">
          <div>
            <h3 className="text-xl font-black text-ink">{title}</h3>
            {subtitle && <p className="text-muted text-sm mt-1">{subtitle}</p>}
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-surface-2 rounded-full transition-colors cursor-pointer"
          >
            <X size={24} className="text-muted" />
          </button>
        </div>

        {/* 본문 */}
        <div className="flex-1 overflow-y-auto p-8 space-y-6">
          {/* 기본 정보 */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-xs font-black text-muted mb-2 block ml-1">나이</label>
              <input
                type="text"
                inputMode="numeric"
                placeholder="예: 30"
                {...register('age')}
                className={`w-full px-6 py-4 bg-surface-2 rounded-2xl outline-none font-bold text-ink border transition-colors ${
                  errors.age ? 'border-red-500' : 'border-transparent focus:border-line'
                }`}
              />
              <FormError name="age" errors={errors} />
            </div>
            <div>
              <label className="text-xs font-black text-muted mb-2 block ml-1">성별</label>
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
                        className={`flex-1 py-4 rounded-2xl text-sm font-bold border transition-all cursor-pointer ${
                          field.value === g ? btnSelected : btnUnselected
                        }`}
                      >
                        {g === 'MALE' ? '남성' : '여성'}
                      </button>
                    ))}
                  </div>
                )}
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-xs font-black text-muted mb-2 block ml-1">키 (cm)</label>
              <input
                type="text"
                inputMode="decimal"
                placeholder="예: 170"
                {...register('height')}
                className={`w-full px-6 py-4 bg-surface-2 rounded-2xl outline-none font-bold text-ink border transition-colors ${
                  errors.height ? 'border-red-500' : 'border-transparent focus:border-line'
                }`}
              />
              <FormError name="height" errors={errors} />
            </div>
            <div>
              <label className="text-xs font-black text-muted mb-2 block ml-1">몸무게 (kg)</label>
              <input
                type="text"
                inputMode="decimal"
                placeholder="예: 65.5"
                {...register('weight')}
                className={`w-full px-6 py-4 bg-surface-2 rounded-2xl outline-none font-bold text-ink border transition-colors ${
                  errors.weight ? 'border-red-500' : 'border-transparent focus:border-line'
                }`}
              />
              <FormError name="weight" errors={errors} />
            </div>
          </div>

          {/* 생활 습관 */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-xs font-black text-muted mb-2 block ml-1">흡연 여부</label>
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
                        className={`flex-1 py-4 rounded-2xl text-sm font-bold border transition-all cursor-pointer ${
                          field.value === v ? btnSelected : btnUnselected
                        }`}
                      >
                        {v ? '예' : '아니오'}
                      </button>
                    ))}
                  </div>
                )}
              />
            </div>
            <div>
              <label className="text-xs font-black text-muted mb-2 block ml-1">음주 여부</label>
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
                        className={`flex-1 py-4 rounded-2xl text-sm font-bold border transition-all cursor-pointer ${
                          field.value === v ? btnSelected : btnUnselected
                        }`}
                      >
                        {v ? '예' : '아니오'}
                      </button>
                    ))}
                  </div>
                )}
              />
            </div>
          </div>

          {/* 기저질환 */}
          <div>
            <label className="text-xs font-black text-muted mb-3 block ml-1">기저질환</label>
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
                      className={`px-4 py-2 rounded-full text-xs font-bold transition-all border cursor-pointer ${
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

          {/* 알레르기 */}
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
                      className={`px-4 py-2 rounded-full text-xs font-bold transition-all border cursor-pointer ${
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

        {/* 하단 버튼 */}
        <div className="p-8 pt-4 flex gap-3 border-t border-line shrink-0">
          <button
            type="button"
            onClick={showSkip ? onSkip : onClose}
            disabled={isSubmitting}
            className="flex-1 py-4 rounded-2xl bg-surface-2 text-muted font-bold hover:bg-surface-2 transition-all cursor-pointer disabled:opacity-50"
          >
            {showSkip ? skipLabel : cancelLabel}
          </button>
          <button
            type="button"
            onClick={handleSubmit(onSubmit)}
            disabled={!isValid || isSubmitting}
            className="flex-1 py-4 rounded-2xl bg-accent text-accent-ink font-black hover:brightness-110 transition-all shadow-lg cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isSubmitting ? '저장 중...' : saveLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
