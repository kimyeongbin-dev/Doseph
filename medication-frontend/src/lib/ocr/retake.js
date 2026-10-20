/**
 * 재촬영 판정 — 평균 신뢰도가 낮으면 «권하고», 보낼 약 줄이 없으면 «막는다».
 *
 * 기준값은 S2 측정(합성 처방전 36장)에서 나왔다. 표본이 작아 낮은 신뢰도는 막지 않고
 * 권하기만 한다(사용자가 «그래도 진행» 할 수 있다). 진행해도 약 줄 고르기는 그대로 돈다.
 */

export const RETAKE_CONFIDENCE = 0.8

/**
 * @param {{meanConfidence: number, drugLineCount: number}} summary
 * @returns {'ok' | 'suggest' | 'block'}
 */
export function judgeRetake({ meanConfidence, drugLineCount }) {
  if (drugLineCount === 0) return 'block'
  if (meanConfidence < RETAKE_CONFIDENCE) return 'suggest'
  return 'ok'
}
