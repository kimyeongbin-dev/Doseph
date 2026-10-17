'use client'

// 폼 필드 옆/아래 빨간 helper 메시지 — 모든 폼이 같은 톤 으로.
//
// 사용:
//   <input {...register('medicine_name')} />
//   <FormError name="medicine_name" errors={errors} />

import { fieldError } from '@/schemas'

export default function FormError({ name, errors, className = '' }) {
  const message = fieldError(errors, name)
  if (!message) return null
  return (
    <p role="alert" className={`mt-1 text-[11px] font-bold text-red-500 break-keep ${className}`}>
      {message}
    </p>
  )
}
