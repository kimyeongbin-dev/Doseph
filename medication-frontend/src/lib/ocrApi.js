/**
 * OCR 업로드 요청.
 *
 * 화면(`app/ocr/loading`)에서 요청 모양을 떼어 낸 자리다 — 무엇을 서버로 보내는지를
 * 한 함수가 정하므로, 테스트가 이 함수 하나를 겨눠 «무엇이 나가는가» 를 단언할 수 있다.
 */

import api from '@/lib/api'

// ── 처방전 OCR 업로드 ─────────────────────────────────────────────────
// 흐름: sessionStorage 의 dataURL -> Blob -> File -> multipart POST /ocr/extract
//       -> draft_id 반환 (결과는 호출자가 SSE 로 받는다)
// profileId 가 없으면 query 를 빼고, BE 가 SELF 프로필로 처리한다.
/**
 * @param {object} upload
 * @param {string} upload.fileData  sessionStorage 에 넣어 둔 dataURL
 * @param {string} upload.fileName
 * @param {string} upload.fileType
 * @param {string} [upload.profileId]
 * @returns {Promise<string>} draft_id
 */
export async function submitOcrUpload({ fileData, fileName, fileType, profileId }) {
  const blob = await (await fetch(fileData)).blob()
  const file = new File([blob], fileName, { type: fileType })
  const formData = new FormData()
  formData.append('file', file)

  const response = await api.post('/api/v1/ocr/extract', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 60000,
    params: profileId ? { profile_id: profileId } : undefined,
  })
  return response.data.draft_id
}
