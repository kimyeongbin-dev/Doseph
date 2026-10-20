/**
 * 기기 안 OCR — 처방전 사진을 브라우저에서 글자로 읽는다. 사진은 기기를 떠나지 않는다.
 *
 * 엔진(onnxruntime-web + ppu-paddle-ocr)과 모델(약 18MB)은 무거워서 이 함수를 처음 부를 때
 * 불러온다. 모델은 같은 출처(/ocr/)에서 받는다 — 빌드 때 scripts/fetch-ocr-assets.mjs 가
 * 고정 리비전에서 받아 해시로 대조해 둔 파일이다.
 */

const ASSET_BASE = '/ocr'

const MODEL = {
  detection: `${ASSET_BASE}/models/PP-OCRv5_mobile_det_infer.onnx`,
  recognition: `${ASSET_BASE}/models/korean_PP-OCRv5_mobile_rec_infer.onnx`,
  charactersDictionary: `${ASSET_BASE}/models/ppocrv5_korean_dict.txt`,
}

// S2 측정과 같은 조건 — 긴 변 2000px 로 줄여 읽는다(휴대폰 원본 4000px 대비 속도·메모리 절약).
const MAX_SIDE = 2000

let servicePromise = null

// ── OCR 엔진 준비 (한 번만) ───────────────────────────────────────────
// 흐름: 엔진 모듈 동적 import -> WASM 경로·단일 스레드 지정 -> 모델 받기·초기화
// 실패하면 다음 호출에서 다시 시도하도록 캐시를 비운다.
// 단일 스레드인 이유: 멀티스레드는 교차 출처 격리(COOP/COEP)가 필요하고 지금 사이트는 그걸 켜지 않았다.
function loadOcrService() {
  if (!servicePromise) {
    servicePromise = (async () => {
      const [ort, { PaddleOcrService }] = await Promise.all([
        import('onnxruntime-web'),
        import('ppu-paddle-ocr/web'),
      ])
      ort.env.wasm.wasmPaths = `${ASSET_BASE}/ort/`
      ort.env.wasm.numThreads = 1
      const service = new PaddleOcrService({
        model: MODEL,
        processing: { engine: 'canvas-native' },
      })
      await service.initialize()
      return service
    })().catch((error) => {
      servicePromise = null
      throw error
    })
  }
  return servicePromise
}

// ── 사진 -> canvas ───────────────────────────────────────────────────
// 흐름: EXIF 방향 보정 -> 긴 변 MAX_SIDE 로 축소 -> canvas 에 그림
async function toCanvas(file) {
  const bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' })
  const scale = Math.min(1, MAX_SIDE / Math.max(bitmap.width, bitmap.height))
  const canvas = document.createElement('canvas')
  canvas.width = Math.round(bitmap.width * scale)
  canvas.height = Math.round(bitmap.height * scale)
  canvas.getContext('2d').drawImage(bitmap, 0, 0, canvas.width, canvas.height)
  bitmap.close()
  return canvas
}

export class OcrEngineLoadError extends Error {}

// ── 사진 한 장 읽기 ───────────────────────────────────────────────────
// 흐름: 엔진 준비(onStage 'loading') -> 사진 읽기(onStage 'reading') -> 줄별 글자·신뢰도 반환
// 신뢰도 거르기는 하지 않는다(minimumConfidence 0) — summarizeOcrResult 가 한 곳에서 한다.
/**
 * @param {File} file
 * @param {{onStage?: (stage: 'loading' | 'reading') => void}} [options]
 */
export async function recognizePrescription(file, { onStage } = {}) {
  onStage?.('loading')
  let service
  try {
    service = await loadOcrService()
  } catch (error) {
    throw new OcrEngineLoadError('OCR 엔진을 불러오지 못했습니다.', { cause: error })
  }
  onStage?.('reading')
  const canvas = await toCanvas(file)
  return service.recognize(canvas, { minimumConfidence: 0, noCache: true })
}
