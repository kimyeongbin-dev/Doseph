/**
 * 기기 안 OCR — 처방전 사진을 브라우저에서 글자로 읽는다. 사진은 기기를 떠나지 않는다.
 *
 * 엔진(onnxruntime-web + ppu-paddle-ocr)과 모델(약 18MB)은 무거워서 읽을 때마다 워커를 띄우고,
 * 끝나면 종료해 메모리를 돌려받는다. 이유와 엔진 설정은 ocr.worker.js 에 있다.
 */

export class OcrEngineLoadError extends Error {}

function createOcrWorker() {
  return new Worker(new URL('./ocr.worker.js', import.meta.url))
}

// ── 사진 한 장 읽기 ───────────────────────────────────────────────────
// 흐름: onStage 'loading' -> 워커 시작·사진 전달 -> 워커의 단계 알림 전달 -> 결과 반환
//       -> 성공·실패와 상관없이 워커 종료
// 준비 단계의 실패와 워커 자체를 못 띄운 실패는 OcrEngineLoadError 로 구별한다.
/**
 * @param {File} file
 * @param {{onStage?: (stage: 'loading' | 'reading') => void}} [options]
 */
export function recognizePrescription(file, { onStage } = {}) {
  onStage?.('loading')
  return new Promise((resolve, reject) => {
    let worker
    try {
      worker = createOcrWorker()
    } catch (error) {
      reject(new OcrEngineLoadError('OCR 엔진을 불러오지 못했습니다.', { cause: error }))
      return
    }
    const finish = (settle, value) => {
      worker.terminate()
      settle(value)
    }
    worker.onerror = (event) => {
      finish(reject, new OcrEngineLoadError('OCR 엔진을 불러오지 못했습니다.', { cause: event }))
    }
    worker.onmessage = ({ data }) => {
      if (data.type === 'stage') {
        onStage?.(data.stage)
      } else if (data.type === 'result') {
        finish(resolve, data.result)
      } else if (data.stage === 'loading') {
        finish(reject, new OcrEngineLoadError('OCR 엔진을 불러오지 못했습니다.'))
      } else {
        finish(reject, new Error('처방전을 읽지 못했습니다.'))
      }
    }
    worker.postMessage({ file })
  })
}
