// 브라우저 OCR 자산 준비 — 고정·대조 규칙 회귀 테스트 (node --test)
// 받는 모델이 «측정에 쓴 바로 그 파일» 인지를 이 규칙들이 보증한다.

import { test } from 'node:test'
import assert from 'node:assert/strict'

import {
  MODEL_REVISION,
  MODELS,
  ORT_RUNTIME_FILES,
  assertDigest,
  assertPinnedVersion,
  assertRuntimeReferences,
  findRuntimeReferences,
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
