// 처방전 업로드 요청 — 서버로 나가는 것은 «약 줄 글자» 하나뿐이다
//
// 이 테스트가 «사진이 기기 밖으로 나가지 않는다» 의 FE 쪽 잠금이다.
//    본문에 다른 키가 붙거나 FormData·Blob 이 실리면 실패한다.

import { beforeEach, describe, expect, it, vi } from 'vitest'

import api from '@/lib/api'
import { submitOcrText } from '@/lib/ocrApi'

vi.mock('@/lib/api', () => ({
  default: { post: vi.fn() },
}))

const TEXT = '642200380 판토복정 40밀리그램 1 3 1\n용법 식후30분에 복용하십시오.'

describe('submitOcrText', () => {
  beforeEach(() => {
    api.post.mockReset()
    api.post.mockResolvedValue({ data: { draft_id: 'draft-1', medicines: [] } })
  })

  it('JSON 본문 {text} 만 보내고 draft_id 를 돌려준다', async () => {
    const draftId = await submitOcrText({ text: TEXT, profileId: 'prof-1' })

    expect(draftId).toBe('draft-1')
    const [url, body, options] = api.post.mock.calls[0]
    expect(url).toBe('/api/v1/ocr/extract')
    expect(body).toEqual({ text: TEXT })
    expect(Object.keys(body)).toEqual(['text'])
    expect(body).not.toBeInstanceOf(FormData)
    expect(options.params).toEqual({ profile_id: 'prof-1' })
  })

  it('프로필이 없으면 query 를 붙이지 않는다', async () => {
    await submitOcrText({ text: TEXT })

    const [, , options] = api.post.mock.calls[0]
    expect(options?.params).toBeUndefined()
  })
})
