// 브라우저 OCR 자산 준비 — 고정·대조 규칙 회귀 테스트 (node --test)
// 받는 모델이 «측정에 쓴 바로 그 파일» 인지를 이 규칙들이 보증한다.

import { test } from 'node:test'
import assert from 'node:assert/strict'
import { existsSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

import {
  MODEL_REVISION,
  MODELS,
  ORT_RUNTIME_FILES,
  assertDigest,
  assertPinnedVersion,
  assertRuntimeReferences,
  downloadModel,
  ensureModel,
  fetchWithRetry,
  findRuntimeReferences,
  modelSources,
  modelUrl,
  sha256Hex,
} from './fetch-ocr-assets.mjs'

test('모델 리비전은 브랜치가 아니라 커밋 해시로 고정한다', () => {
  assert.match(MODEL_REVISION, /^[0-9a-f]{40}$/)
  for (const model of MODELS) {
    assert.ok(modelUrl(model).includes(`/resolve/${MODEL_REVISION}/`), model.file)
    assert.ok(!modelUrl(model).includes('/resolve/main/'), model.file)
  }
})

test('모델 3종 모두 SHA-256 기대값을 가진다', () => {
  assert.equal(MODELS.length, 3)
  for (const model of MODELS) assert.match(model.sha256, /^[0-9a-f]{64}$/, model.file)
})

test('assertDigest: 해시가 같으면 통과, 한 바이트라도 다르면 throw', () => {
  const bytes = Buffer.from('model-bytes')
  assert.doesNotThrow(() => assertDigest('m', bytes, sha256Hex(bytes)))
  assert.throws(
    () => assertDigest('m', Buffer.from('model-bytez'), sha256Hex(bytes)),
    /SHA-256 불일치/,
  )
})

test('assertPinnedVersion: 범위 표기(^)나 다른 판이면 throw', () => {
  assert.doesNotThrow(() => assertPinnedVersion('ort', '1.30.0', '1.30.0'))
  assert.throws(() => assertPinnedVersion('ort', '^1.30.0', '1.30.0'), /버전 불일치/)
  assert.throws(() => assertPinnedVersion('ort', '1.30.0', '1.31.0'), /버전 불일치/)
})

test('WASM 런타임은 로더(.mjs)와 바이너리(.wasm)를 함께 복사한다', () => {
  assert.deepEqual(ORT_RUNTIME_FILES.map((f) => f.split('.').pop()).sort(), ['mjs', 'wasm'])
})

test('findRuntimeReferences: 청크 글자에서 런타임 파일 이름을 중복 없이 뽑는다', () => {
  const chunk =
    'a="ort-wasm-simd-threaded.mjs";b="ort-wasm-simd-threaded.wasm";c="ort-wasm-simd-threaded.wasm"'
  assert.deepEqual(findRuntimeReferences(chunk), [
    'ort-wasm-simd-threaded.mjs',
    'ort-wasm-simd-threaded.wasm',
  ])
  assert.deepEqual(findRuntimeReferences('x="ort-wasm-simd-threaded.jsep.wasm"'), [
    'ort-wasm-simd-threaded.jsep.wasm',
  ])
})

test('assertRuntimeReferences: 복사본과 같으면 통과, JSEP 변형이나 참조 0개면 throw', () => {
  assert.doesNotThrow(() => assertRuntimeReferences([...ORT_RUNTIME_FILES]))
  assert.throws(
    () => assertRuntimeReferences(['ort-wasm-simd-threaded.jsep.mjs']),
    /복사하지 않은 런타임/,
  )
  assert.throws(() => assertRuntimeReferences([]), /0개/)
})

function reply(status, body = '', headers = {}) {
  return new Response(status === 200 ? body : null, { status, headers })
}

function sequence(...responses) {
  const calls = []
  const fetchFn = async (url) => {
    calls.push(url)
    const next = responses.shift()
    if (next instanceof Error) throw next
    return next
  }
  return { fetchFn, calls }
}

test('fetchWithRetry: 429 와 5xx, 네트워크 오류는 다시 시도하고 Retry-After 를 따른다', async () => {
  const waits = []
  const { fetchFn, calls } = sequence(
    reply(429, '', { 'retry-after': '7' }),
    new Error('reset'),
    reply(200, 'ok'),
  )
  const bytes = await fetchWithRetry('u', { fetchFn, sleep: async (ms) => waits.push(ms) })
  assert.equal(bytes.toString(), 'ok')
  assert.equal(calls.length, 3)
  assert.deepEqual(waits, [7000, 2000])
})

test('fetchWithRetry: 404 는 기다리지 않고 바로 실패한다', async () => {
  const { fetchFn, calls } = sequence(reply(404))
  await assert.rejects(fetchWithRetry('u', { fetchFn, sleep: async () => {} }), /HTTP 404/)
  assert.equal(calls.length, 1)
})

test('fetchWithRetry: 3번 실패하면 멈춘다', async () => {
  const { fetchFn, calls } = sequence(reply(503), reply(503), reply(503), reply(200, 'late'))
  await assert.rejects(fetchWithRetry('u', { fetchFn, sleep: async () => {} }), /HTTP 503/)
  assert.equal(calls.length, 3)
})

const fakeModel = (body) => ({ ...MODELS[0], file: 'm.onnx', sha256: sha256Hex(Buffer.from(body)) })

test('downloadModel: Release 가 먼저고, 실패하거나 해시가 다르면 예비 출처로 넘어간다', async () => {
  const model = fakeModel('good')
  const [release, fallback] = modelSources(model)
  assert.match(release, /github\.com\/.+\/releases\/download\/ocr-models-v1\/m\.onnx$/)
  assert.equal(fallback, modelUrl(model))

  const tampered = sequence(reply(200, 'evil'), reply(200, 'good'))
  const bytes = await downloadModel(model, { fetchFn: tampered.fetchFn, sleep: async () => {} })
  assert.equal(bytes.toString(), 'good')
  assert.deepEqual(tampered.calls, [release, fallback])
})

test('downloadModel: 모든 출처가 틀리면 파일을 돌려주지 않고 사유를 모아 throw', async () => {
  const model = fakeModel('good')
  const { fetchFn } = sequence(reply(200, 'evil'), reply(404))
  await assert.rejects(
    downloadModel(model, { fetchFn, sleep: async () => {} }),
    /m\.onnx 받기 실패.*SHA-256 불일치.*HTTP 404/,
  )
})

test('ensureModel: 받은 뒤에는 빌드 캐시로 채우고 네트워크를 쓰지 않는다', async () => {
  const model = fakeModel('good')
  const first = mkdtempSync(join(tmpdir(), 'ocr-public-'))
  const second = mkdtempSync(join(tmpdir(), 'ocr-public-'))
  const cache = mkdtempSync(join(tmpdir(), 'ocr-cache-'))
  const { fetchFn, calls } = sequence(reply(200, 'good'))
  const options = { fetchFn, sleep: async () => {} }

  assert.equal(await ensureModel(model, first, cache, options), 'downloaded')
  assert.equal(await ensureModel(model, first, cache, options), 'public')
  assert.equal(await ensureModel(model, second, cache, options), 'build-cache')
  assert.equal(readFileSync(join(second, 'm.onnx'), 'utf8'), 'good')
  assert.equal(calls.length, 1)
})

test('ensureModel: 캐시 사본이 손상되면 쓰지 않고 다시 받는다', async () => {
  const model = fakeModel('good')
  const pub = mkdtempSync(join(tmpdir(), 'ocr-public-'))
  const cache = mkdtempSync(join(tmpdir(), 'ocr-cache-'))
  writeFileSync(join(cache, model.sha256), 'broken')
  const { fetchFn } = sequence(reply(200, 'good'))
  assert.equal(await ensureModel(model, pub, cache, { fetchFn }), 'downloaded')
  assert.ok(existsSync(join(pub, 'm.onnx')))
  assert.equal(readFileSync(join(cache, model.sha256), 'utf8'), 'good')
})
