/**
 * OCR 업로드 요청.
 *
 * 무엇을 서버로 보내는지를 한 함수가 정하므로, 테스트가 이 함수 하나를 겨눠
 * «무엇이 나가는가» 를 단언할 수 있다. 사진은 기기를 떠나지 않고, 나가는 것은
 * 기기에서 OCR 후 고른 약 줄 글자뿐이다.
 */

import api from '@/lib/api'

// ── 약 줄 글자 업로드 ─────────────────────────────────────────────────
// 흐름: 약 줄 글자 -> JSON POST /ocr/extract -> draft_id 반환 (결과는 호출자가 SSE 로 받는다)
// profileId 가 없으면 query 를 빼고, BE 가 SELF 프로필로 처리한다.
/**
 * @param {object} upload
 * @param {string} upload.text  selectDrugLines 가 고른 줄을 줄바꿈으로 이은 글자
 * @param {string} [upload.profileId]
 * @returns {Promise<string>} draft_id
 */
export async function submitOcrText({ text, profileId }) {
  const response = await api.post(
    '/api/v1/ocr/extract',
    { text },
    { params: profileId ? { profile_id: profileId } : undefined },
  )
  return response.data.draft_id
}
