/**
 * 기기 안 OCR 워커 — 사진 한 장을 읽고 결과를 돌려준다. 페이지가 끝나면 이 워커를 종료한다.
 *
 * 워커에 두는 이유: WebAssembly 메모리는 줄어들지 않아 엔진을 해제(destroy)해도 300MB 넘게 남는다.
 * 워커를 종료해야 그 메모리를 통째로 돌려받는다. 읽는 동안 화면이 멈추지 않는 것은 덤이다.
 * 모델과 WASM 은 같은 출처(/ocr/)에서 받는다 — 빌드 때 scripts/fetch-ocr-assets.mjs 가 해시로 대조해 둔 파일이다.
 * 경로의 버전을 바꾸면 그 스크립트의 MODEL_VERSION 도 함께 바꾼다.
 */

const MODEL_BASE = '/ocr/models/v1'

// S2 측정과 같은 조건 — 긴 변 2000px 로 줄여 읽는다(휴대폰 원본 4000px 대비 속도·메모리 절약).
const MAX_SIDE = 2000

// ── OCR 엔진 준비 ─────────────────────────────────────────────────────
// 흐름: 엔진 모듈 동적 import -> WASM 경로·단일 스레드 지정 -> 모델 받기·초기화
// 단일 스레드인 이유: 멀티스레드는 교차 출처 격리(COOP/COEP)가 필요하고 지금 사이트는 그걸 켜지 않았다.
// wasm 을 직접 지정하는 이유: 번들은 WASM 전용이라 엔진 기본값(webgpu 먼저)은 실패한 뒤 되돌아오기만 한다.
async function loadOcrService() {
  const [ort, { PaddleOcrService }] = await Promise.all([
    import('onnxruntime-web'),
    import('ppu-paddle-ocr/web'),
  ])
  ort.env.wasm.wasmPaths = `/ocr/ort/${ort.env.versions.web}/`
  ort.env.wasm.numThreads = 1
  const service = new PaddleOcrService({
    model: {
      detection: `${MODEL_BASE}/PP-OCRv5_mobile_det_infer.onnx`,
      recognition: `${MODEL_BASE}/korean_PP-OCRv5_mobile_rec_infer.onnx`,
      charactersDictionary: `${MODEL_BASE}/ppocrv5_korean_dict.txt`,
    },
    processing: { engine: 'canvas-native' },
    session: { executionProviders: ['wasm'], graphOptimizationLevel: 'all' },
  })
  await service.initialize()
  return service
}

// ── 사진 -> canvas ───────────────────────────────────────────────────
// 흐름: EXIF 방향 보정 -> 긴 변 MAX_SIDE 로 축소 -> OffscreenCanvas 에 그림
async function toCanvas(file) {
  const bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' })
  const scale = Math.min(1, MAX_SIDE / Math.max(bitmap.width, bitmap.height))
  const canvas = new OffscreenCanvas(
    Math.round(bitmap.width * scale),
    Math.round(bitmap.height * scale),
  )
  canvas.getContext('2d').drawImage(bitmap, 0, 0, canvas.width, canvas.height)
  bitmap.close()
  return canvas
}

// ── 메시지 처리 ───────────────────────────────────────────────────────
// 흐름: 엔진 준비 -> reading 알림 -> 사진 읽기 -> 결과 전송
// 어느 단계에서 실패했는지 함께 보낸다 — 페이지가 안내 문구를 고르는 기준이다.
// 신뢰도 거르기는 하지 않는다(minimumConfidence 0) — summarizeOcrResult 가 한 곳에서 한다.
self.onmessage = async ({ data: { file } }) => {
  let stage = 'loading'
  try {
    const service = await loadOcrService()
    stage = 'reading'
    self.postMessage({ type: 'stage', stage })
    const canvas = await toCanvas(file)
    const result = await service.recognize(canvas, { minimumConfidence: 0, noCache: true })
    self.postMessage({ type: 'result', result })
  } catch (error) {
    self.postMessage({ type: 'error', stage, message: String(error?.message ?? error) })
  }
}
