// 도메인 zod schema — react-hook-form + zodResolver 의 SSOT.
//
// 폼 4종이 같은 schema 를 공유:
//   1) /survey                 → healthSurveySchema
//   2) /ocr/result             → medicationCreateSchema (per row)
//   3) /medication/edit        → medicationCreateSchema (per row)
//   4) /lifestyle-guide 의 증상 트래킹 폼 → dailyLogCreateSchema
//   5) 처방전 detail 인라인 편집 → prescriptionGroupPatchSchema
//
// 메시지는 사용자 노출 한국어. zod resolver 가 react-hook-form 의 errors
// 객체로 매핑 → 폼 컴포넌트가 같은 helper 컴포넌트로 빨간 메시지 표시.

import { z } from 'zod'

// ── 공용 helper ──────────────────────────────────────────────────────────
// 빈 문자열을 undefined 로 정규화 (optional 필드의 ""·null·undefined 통일).
const emptyToUndef = (v) => (v === '' || v === null ? undefined : v)
const trimmed = (max) =>
  z
    .string()
    .transform((s) => s.trim())
    .pipe(z.string().min(1, '필수 입력 항목이에요').max(max, `최대 ${max}자까지 가능해요`))
const optionalTrimmed = (max) =>
  z.preprocess(emptyToUndef, z.string().trim().max(max, `최대 ${max}자까지 가능해요`).optional())

// ── 1. 건강 설문 (Profile.health_survey JSONField) ───────────────────────
// 모든 필드 optional — 사용자가 부분 입력 가능.
export const healthSurveySchema = z.object({
  age: z.preprocess(
    emptyToUndef,
    z.coerce
      .number({ invalid_type_error: '숫자만 입력해주세요' })
      .int('정수만 입력해주세요')
      .min(1, '나이는 1세 이상이에요')
      .max(120, '나이는 120세 이하예요')
      .optional(),
  ),
  gender: z.enum(['MALE', 'FEMALE'], { invalid_type_error: '성별을 선택해주세요' }).optional(),
  height: z.preprocess(
    emptyToUndef,
    z.coerce
      .number({ invalid_type_error: '숫자만 입력해주세요' })
      .min(50, '키는 50cm 이상이에요')
      .max(250, '키는 250cm 이하예요')
      .optional(),
  ),
  weight: z.preprocess(
    emptyToUndef,
    z.coerce
      .number({ invalid_type_error: '숫자만 입력해주세요' })
      .min(1, '몸무게는 1kg 이상이에요')
      .max(300, '몸무게는 300kg 이하예요')
      .optional(),
  ),
  is_smoking: z.boolean().nullable().optional(),
  is_drinking: z.boolean().nullable().optional(),
  conditions: z.array(z.string()).optional(),
  allergies: z.array(z.string()).optional(),
})

// ── 2. Medication (OCR result + 직접 등록 + edit 공용) ───────────────────
const intakeTimeEnum = z.enum(['BREAKFAST', 'LUNCH', 'DINNER', 'BEDTIME'], {
  invalid_type_error: '복약 시간 슬롯이 올바르지 않아요',
})

export const medicationCreateSchema = z
  .object({
    medicine_name: trimmed(64),
    dose_per_intake: optionalTrimmed(32),
    intake_instruction: optionalTrimmed(128),
    intake_times: z
      .array(intakeTimeEnum)
      .min(1, '복약 시간을 한 개 이상 선택해주세요')
      .max(4, '복약 시간은 최대 4개까지 가능해요'),
    total_intake_count: z.coerce
      .number({ invalid_type_error: '총 복약 횟수는 숫자만 가능해요' })
      .int('정수만 가능해요')
      .min(1, '총 복약 횟수는 1회 이상이에요'),
    remaining_intake_count: z.coerce
      .number({ invalid_type_error: '남은 복약 횟수는 숫자만 가능해요' })
      .int('정수만 가능해요')
      .min(0, '남은 복약 횟수는 0 이상이에요'),
    start_date: z.coerce.date({ invalid_type_error: '시작일을 입력해주세요' }),
    end_date: z.preprocess(emptyToUndef, z.coerce.date().optional()),
    dispensed_date: z.preprocess(emptyToUndef, z.coerce.date().optional()),
    expiration_date: z.preprocess(emptyToUndef, z.coerce.date().optional()),
  })
  .refine((v) => v.remaining_intake_count <= v.total_intake_count, {
    message: '남은 복약 횟수가 총 복약 횟수보다 클 수 없어요',
    path: ['remaining_intake_count'],
  })
  .refine((v) => !v.end_date || !v.start_date || v.end_date >= v.start_date, {
    message: '종료일은 시작일 이후여야 해요',
    path: ['end_date'],
  })

// ── 2-b. Medication edit (인라인 편집 — 부분 patch) ─────────────────────
// edit 페이지는 이미 등록된 medication 의 일부 필드만 수정. medicine_name 만
// 필수, 나머지는 optional. 음수/0 은 차단.
export const medicationEditPatchSchema = z.object({
  medicine_name: trimmed(64),
  dose_per_intake: optionalTrimmed(32),
  intake_instruction: optionalTrimmed(128),
  category: optionalTrimmed(64),
  daily_intake_count: z.preprocess(
    emptyToUndef,
    z.coerce
      .number({ invalid_type_error: '숫자만 입력해주세요' })
      .int('정수만 가능해요')
      .min(1, '1회 이상이어야 해요')
      .max(24, '하루 최대 24회까지 가능해요')
      .optional(),
  ),
  total_intake_days: z.preprocess(
    emptyToUndef,
    z.coerce
      .number({ invalid_type_error: '숫자만 입력해주세요' })
      .int('정수만 가능해요')
      .min(1, '1일 이상이어야 해요')
      .max(365, '1년 이내로 입력해주세요')
      .optional(),
  ),
})

// ── 3. 일일 증상 로그 ──────────────────────────────────────────────────
export const dailyLogCreateSchema = z.object({
  log_date: z.coerce.date({ invalid_type_error: '날짜를 입력해주세요' }),
  symptoms: z.array(z.string()).min(0).max(20, '증상은 최대 20개까지 선택할 수 있어요'),
  note: optionalTrimmed(512),
})

// ── 4. 처방전 그룹 부분 수정 (병원/진료과/처방일) ───────────────────────
// 모든 필드 optional — 인라인 편집에서 한 필드만 보낼 수 있게.
export const prescriptionGroupPatchSchema = z.object({
  hospital_name: optionalTrimmed(128),
  department: optionalTrimmed(64),
  dispensed_date: z.preprocess(emptyToUndef, z.coerce.date().optional()),
})

// ── 5. 닉네임 변경 (mypage BasicInfoModal) ──────────────────────────────
export const nicknameUpdateSchema = z.object({
  nickname: trimmed(32),
})

// ── 6. 가족 프로필 추가/수정 (mypage FamilyModal) ───────────────────────
// relation_type 은 RELATION_LABELS 7종 (SELF 제외). gender 는 nullable —
// OTHER 등 일부 case 는 미정 가능.
export const familyProfileSchema = z.object({
  name: trimmed(32),
  relation_type: z.enum(['FATHER', 'MOTHER', 'SON', 'DAUGHTER', 'HUSBAND', 'WIFE', 'OTHER']),
  gender: z.enum(['MALE', 'FEMALE']).nullable().optional(),
})

// ── 폼 helper — react-hook-form errors 객체에서 메시지 한 줄 추출 ───────
// `<FormError name="medicine_name" errors={errors} />` 같이 일관된 컴포넌트
// 하나에 매핑시키기 위한 path 정규화.
export function fieldError(errors, name) {
  if (!errors) return undefined
  const parts = String(name).split('.')
  let cur = errors
  for (const p of parts) {
    if (cur == null) return undefined
    cur = cur[p]
  }
  return cur?.message
}
