/**
 * 브라우저 OCR 결과 -> 서버로 보낼 «약 줄» 고르기.
 *
 * 사진은 기기를 떠나지 않는다. 서버(그리고 그 뒤의 LLM)가 받는 것은 이 파일이 고른 줄뿐이다.
 * 규칙은 S2 측정(합성 처방전 36장)에서 정했다 — 약 61/61 · 보험코드 55/55 를 보내고
 * 개인정보 줄은 0건 보냈다. 틀려도 «덜 보내는» 쪽으로 기울게 짰다: 버린 약은 사용자가
 * 결과 화면에서 직접 더할 수 있지만, 보낸 주민번호는 되돌릴 수 없다.
 */

// OCR 이 이 아래로 확신하는 글자는 버린다(ppu-paddle-ocr 의 기본값과 같다).
const MIN_ITEM_CONFIDENCE = 0.5

// ── 버리는 줄 ─────────────────────────────────────────────────────────
// 표지어는 공백을 지운 글자에서 찾는다 — OCR 이 «성 명» 처럼 띄워 읽는다.
// «명청» 은 «명칭» 의 실측 오독이다.
const IDENTITY_LABEL = /(성명|주민|등록번호|의료기관|명칭|명청|전화|면허|교부|발행|환자)/
// 주민번호: 하이픈형, 그리고 하이픈이 공백·점·물결로 바뀐 형(측정에서 OCR 이 실제로 그렇게 읽었다)
const RRN_HYPHEN = /\d{6}\s*-\s*\d/
const RRN_SEPARATED = /(?<!\d)\d{6}[\s.~-]{1,3}\d{7}(?!\d)/
// 하이픈이 사라져 붙은 주민번호(13자리)·전화번호(10~11자리). 보험코드는 9자리라 걸리지 않는다.
const LONG_DIGIT_RUN = /\d{11,}/
const PHONE = /\d{2,3}\s*-\s*\d{3,4}\s*-\s*\d/

// ── 보내는 줄 (넷 중 하나) ───────────────────────────────────────────
// 보험코드로 시작: 앞에 OCR 잡음 두 글자까지 허용, 코드 자리를 잃은 7자리까지
const CODE_AT_START = /^\s*\D{0,2}\d{7,10}(?!\d)/
// 한글 바로 뒤 제형어 — «가정의학과» 의 «정» 이나 성씨 «정» 은 뒤 글자에서 걸러진다
const FORM_WORD =
  /[가-힣](정|캡슐|연질캡슐|시럽|과립|연고|크림|겔|패취|패치|현탁액|점안액)(?=\d|밀리|마이크로|\(|\/|\s|$)/
const UNIT = /(밀리그램|마이크로그램|mg|㎎|mL|㎖)/i
const DOSAGE_PHRASE = /(식후|식전|취침|복용하)/

// ── OCR 결과 요약 ─────────────────────────────────────────────────────
// 흐름: 줄별 글자 -> 신뢰도 0.5 미만 버림 -> 공백으로 이음 -> 빈 줄 버림
//       -> 남은 글자의 평균 신뢰도(재촬영 판정 입력)
/**
 * @param {{lines?: Array<Array<{text: string, confidence: number}>>}} result  ppu-paddle-ocr 의 recognize() 결과
 * @returns {{lines: string[], meanConfidence: number}}
 */
export function summarizeOcrResult(result) {
  const lines = []
  let confidenceSum = 0
  let itemCount = 0
  for (const line of result?.lines ?? []) {
    const kept = line.filter((item) => item.confidence >= MIN_ITEM_CONFIDENCE)
    if (kept.length === 0) continue
    lines.push(kept.map((item) => item.text).join(' '))
    for (const item of kept) confidenceSum += item.confidence
    itemCount += kept.length
  }
  return { lines, meanConfidence: itemCount ? confidenceSum / itemCount : 0 }
}

function isIdentityLine(line) {
  if (IDENTITY_LABEL.test(line.replace(/\s+/g, ''))) return true
  return (
    RRN_HYPHEN.test(line) ||
    RRN_SEPARATED.test(line) ||
    LONG_DIGIT_RUN.test(line) ||
    PHONE.test(line)
  )
}

function looksLikeDrugLine(line) {
  return (
    CODE_AT_START.test(line) || FORM_WORD.test(line) || UNIT.test(line) || DOSAGE_PHRASE.test(line)
  )
}

// ── 약 줄 고르기 ──────────────────────────────────────────────────────
// 흐름: 개인정보 모양이 하나라도 있으면 버림 -> 약 줄 모양이 하나라도 있으면 보냄
// 버리는 검사가 먼저다 — 약 이름과 주민번호가 한 줄에 붙어 읽혀도 그 줄은 나가지 않는다.
/**
 * @param {string[]} lines
 * @returns {string[]}
 */
export function selectDrugLines(lines) {
  return lines.filter((line) => !isIdentityLine(line) && looksLikeDrugLine(line))
}
