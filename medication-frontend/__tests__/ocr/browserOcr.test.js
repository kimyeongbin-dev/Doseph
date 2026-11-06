import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { OcrEngineLoadError, recognizePrescription } from '@/lib/ocr/browserOcr'

// 워커 안의 엔진은 브라우저 실측으로 검증한다. 여기서는 페이지 쪽 계약만 본다.
class FakeWorker {
  static last = null
  constructor() {
    this.terminate = vi.fn()
    this.postMessage = vi.fn()
    FakeWorker.last = this
  }
  send(data) {
    this.onmessage({ data })
  }
}

const file = new Blob(['photo'])

describe('recognizePrescription', () => {
  beforeEach(() => {
    vi.stubGlobal('Worker', FakeWorker)
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('사진을 워커로 넘기고 결과를 돌려준 뒤 워커를 종료한다', async () => {
    const stages = []
    const pending = recognizePrescription(file, { onStage: (s) => stages.push(s) })
    const worker = FakeWorker.last
    expect(worker.postMessage).toHaveBeenCalledWith({ file })
    worker.send({ type: 'stage', stage: 'reading' })
    expect(worker.terminate).not.toHaveBeenCalled()
    worker.send({ type: 'result', result: { lines: [] } })
    await expect(pending).resolves.toEqual({ lines: [] })
    expect(stages).toEqual(['loading', 'reading'])
    expect(worker.terminate).toHaveBeenCalledTimes(1)
  })

  it('준비 단계 실패는 OcrEngineLoadError 이고 워커를 종료한다', async () => {
    const pending = recognizePrescription(file)
    const worker = FakeWorker.last
    worker.send({ type: 'error', stage: 'loading', message: 'x' })
    await expect(pending).rejects.toBeInstanceOf(OcrEngineLoadError)
    expect(worker.terminate).toHaveBeenCalledTimes(1)
  })

  it('읽는 단계 실패는 엔진 오류로 분류하지 않고 워커를 종료한다', async () => {
    const pending = recognizePrescription(file)
    const worker = FakeWorker.last
    worker.send({ type: 'error', stage: 'reading', message: 'x' })
    const error = await pending.catch((e) => e)
    expect(error).toBeInstanceOf(Error)
    expect(error).not.toBeInstanceOf(OcrEngineLoadError)
    expect(worker.terminate).toHaveBeenCalledTimes(1)
  })

  it('워커 스크립트를 못 불러오면 OcrEngineLoadError 이고 워커를 종료한다', async () => {
    const pending = recognizePrescription(file)
    const worker = FakeWorker.last
    worker.onerror(new Event('error'))
    await expect(pending).rejects.toBeInstanceOf(OcrEngineLoadError)
    expect(worker.terminate).toHaveBeenCalledTimes(1)
  })

  it('워커를 만들 수 없는 환경도 OcrEngineLoadError 다', async () => {
    vi.stubGlobal('Worker', class { constructor() { throw new Error('no worker') } }) // prettier-ignore
    await expect(recognizePrescription(file)).rejects.toBeInstanceOf(OcrEngineLoadError)
  })
})
