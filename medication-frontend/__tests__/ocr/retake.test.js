// 재촬영 판정 — 평균 신뢰도가 낮으면 «권하고», 보낼 약 줄이 없으면 «막는다»
//
// 기준값은 S2 측정(합성 처방전 36장)에서 나왔다: 정답 약이 0개 읽힌 15장의 최고 신뢰도 0.758,
// 전부 읽힌 12장의 최저 0.822. 표본이 작아 «막기» 가 아니라 «권하기» 로 정했다(사용자 결정).

import { describe, expect, it } from 'vitest'

import { RETAKE_CONFIDENCE, judgeRetake } from '@/lib/ocr/retake'

describe('judgeRetake', () => {
  it('기준값은 0.80 이다', () => {
    expect(RETAKE_CONFIDENCE).toBe(0.8)
  })

  it.each([
    ['측정: 전부 읽힌 최저 신뢰도', 0.822, 'ok'],
    ['깨끗한 사진', 0.95, 'ok'],
    ['경계값은 통과', 0.8, 'ok'],
    ['경계 바로 아래', 0.799, 'suggest'],
    ['측정: 0개 읽힌 최고 신뢰도', 0.758, 'suggest'],
  ])('%s (%s) → %s', (_, meanConfidence, expected) => {
    expect(judgeRetake({ meanConfidence, drugLineCount: 3 })).toBe(expected)
  })

  it('보낼 약 줄이 0개면 신뢰도와 상관없이 막는다', () => {
    expect(judgeRetake({ meanConfidence: 0.95, drugLineCount: 0 })).toBe('block')
    expect(judgeRetake({ meanConfidence: 0.5, drugLineCount: 0 })).toBe('block')
  })
})
