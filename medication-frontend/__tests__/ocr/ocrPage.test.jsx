// 처방전 등록 화면 — 기기 안 OCR 결과를 «보낼지·무엇을 보낼지» 로 엮는 곳
//
// 순수 함수(ocrLines · retake · ocrApi)는 각자 잠겨 있다. 이 파일은 화면이 그것들을
// 올바르게 엮는지 잠근다: 막으면 안 보내고, 권유를 거절하면 안 보내고, 진행해도 개인정보
// 줄은 빠지고, 사진은 어떤 경우에도 브라우저 저장소에 들어가지 않는다.
// OCR 엔진 자체는 무거운 WASM 이라 가짜로 바꾼다 — 실제 엔진은 빌드 산출물로 따로 확인한다.

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import toast from 'react-hot-toast'

import OcrPage from '@/app/ocr/page'
import { OcrEngineLoadError, recognizePrescription } from '@/lib/ocr/browserOcr'
import { submitOcrText } from '@/lib/ocrApi'

const push = vi.fn()
const confirm = vi.fn()

vi.mock('next/navigation', () => ({ useRouter: () => ({ push }) }))
vi.mock('@/components/common/ConfirmDialog', () => ({ useConfirm: () => confirm }))
vi.mock('@/contexts/ProfileContext', () => ({
  useProfile: () => ({ selectedProfileId: 'prof-1' }),
}))
vi.mock('@/components/layout/Header', () => ({ default: () => null }))
vi.mock('react-hot-toast', () => ({ default: { error: vi.fn() } }))
vi.mock('@/lib/ocrApi', () => ({ submitOcrText: vi.fn() }))
vi.mock('@/lib/ocr/browserOcr', () => ({
  OcrEngineLoadError: class OcrEngineLoadError extends Error {},
  recognizePrescription: vi.fn(),
}))

const DRUG = '642900110 코대원포르테시럽 10 3 3'
const DOSAGE = '용법 식후30분에 복용하십시오.'
const PATIENT = '환자 성명 정테스트 주민등록번호 920707-1456789'

const ocrResult = (confidence, texts) => ({
  lines: texts.map((text) => [{ text, confidence, box: { x: 0, y: 0, width: 1, height: 1 } }]),
})

async function pickPhotoAndAnalyze() {
  const user = userEvent.setup()
  const { container } = render(<OcrPage />)
  const input = await waitFor(
    () => {
      const el = container.querySelector('input[type="file"]')
      if (!el) throw new Error('업로드 입력이 아직 없다')
      return el
    },
    { timeout: 3000 },
  )
  await user.upload(input, new File(['photo'], 'rx.jpg', { type: 'image/jpeg' }))
  await user.click(screen.getByRole('button', { name: '분석 시작하기' }))
}

beforeEach(() => {
  vi.clearAllMocks()
  sessionStorage.clear()
  URL.createObjectURL = vi.fn(() => 'blob:preview')
  submitOcrText.mockResolvedValue('draft-1')
})

afterEach(() => {
  // 어떤 경로로 끝나든 사진(이나 그 글자)을 브라우저 저장소에 남기지 않는다.
  expect(sessionStorage.length).toBe(0)
})

describe('처방전 등록 화면', () => {
  it('신뢰도가 충분하면 약 줄만 보내고 진행 화면으로 간다', async () => {
    recognizePrescription.mockResolvedValue(ocrResult(0.95, [PATIENT, DRUG, DOSAGE]))

    await pickPhotoAndAnalyze()

    await waitFor(() => expect(push).toHaveBeenCalledWith('/ocr/loading?draft_id=draft-1'))
    expect(submitOcrText).toHaveBeenCalledWith({ text: `${DRUG}\n${DOSAGE}`, profileId: 'prof-1' })
    expect(confirm).not.toHaveBeenCalled()
  })

  it('신뢰도가 낮으면 재촬영을 권하고, «다시 찍기» 면 보내지 않는다', async () => {
    recognizePrescription.mockResolvedValue(ocrResult(0.7, [DRUG]))
    confirm.mockResolvedValue(false)

    await pickPhotoAndAnalyze()

    await waitFor(() => expect(confirm).toHaveBeenCalledTimes(1))
    expect(confirm.mock.calls[0][0]).toMatchObject({
      confirmLabel: '그래도 진행',
      cancelLabel: '다시 찍기',
    })
    expect(submitOcrText).not.toHaveBeenCalled()
    expect(push).not.toHaveBeenCalled()
  })

  it('«그래도 진행» 해도 개인정보 줄은 빠진 채로 보낸다', async () => {
    recognizePrescription.mockResolvedValue(ocrResult(0.7, [PATIENT, DRUG]))
    confirm.mockResolvedValue(true)

    await pickPhotoAndAnalyze()

    await waitFor(() => expect(submitOcrText).toHaveBeenCalledTimes(1))
    expect(submitOcrText.mock.calls[0][0].text).toBe(DRUG)
    expect(submitOcrText.mock.calls[0][0].text).not.toContain('920707')
  })

  it('보낼 약 줄이 없으면 막고 재촬영·직접 입력을 안내한다', async () => {
    recognizePrescription.mockResolvedValue(ocrResult(0.95, [PATIENT]))

    await pickPhotoAndAnalyze()

    expect(await screen.findByRole('alert')).toHaveTextContent('약 정보를 찾지 못했어요')
    expect(submitOcrText).not.toHaveBeenCalled()
    expect(confirm).not.toHaveBeenCalled()
  })

  it('OCR 엔진을 못 불러오면 연결 확인을 안내하고 보내지 않는다', async () => {
    recognizePrescription.mockRejectedValue(new OcrEngineLoadError('load failed'))

    await pickPhotoAndAnalyze()

    await waitFor(() => expect(toast.error).toHaveBeenCalledTimes(1))
    expect(toast.error.mock.calls[0][0]).toContain('인터넷 연결')
    expect(submitOcrText).not.toHaveBeenCalled()
  })
})
