// ── 브라우저 OCR 자산 준비 (빌드·dev 전 단계) ─────────────────────────
// 흐름: 모델 3종 -> public 또는 빌드 캐시에 있으면 SHA-256 대조만 -> 없으면 Release·예비 출처에서 재시도하며 받기
//       -> 대조 실패면 빌드 중단 -> onnxruntime-web 설치본 버전 확인 -> WASM 런타임 2종을 버전 경로로 복사
// 전제: 결과물(public/ocr/)은 커밋하지 않는다(.gitignore) — 18MB 바이너리를 저장소에 넣지 않으려고.
//       같은 출처로 내보내므로 런타임에 제3자로 요청이 나가지 않는다.
//       경로에 버전이 있어 _headers 가 immutable 로 캐시한다. 파일을 바꾸면 MODEL_VERSION 을 올린다.

import { createHash } from 'node:crypto'
import {
  copyFileSync,
  existsSync,
  mkdirSync,
  readdirSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

// 1차 출처 = 우리 불변 Release. Hugging Face 는 IP 단위 제한이 있어 Cloudflare 빌드가 429 로 실패했다.
// 이 값과 ocr.worker.js 의 MODEL_BASE 는 같이 바꾼다.
export const MODEL_VERSION = 'v1'
const RELEASE_BASE = 'https://github.com/kimyeongbin-dev/Doseph/releases/download/ocr-models-v1'

// 예비 출처 — 모델 저장소의 커밋을 고정한다. main 을 가리키면 저쪽이 바뀔 때 조용히 다른 모델을 받는다.
export const MODEL_REVISION = 'bf1d5edb0335d3262be7caf13f766ba274b4cadd'
const MODEL_REPO = 'https://huggingface.co/snowfluke/ppu-paddle-ocr-models/resolve'

// 해시는 S2 측정(합성 처방전 36장)에 쓴 파일의 것이다. 바꾸면 측정을 다시 해야 한다.
export const MODELS = [
  {
    file: 'PP-OCRv5_mobile_det_infer.onnx',
    path: 'detection/PP-OCRv5_mobile_det_infer.onnx',
    sha256: 'd7fe3ea74652890722c0f4d02458b7261d9f5ae6c92904d05707c9eb155c7924',
  },
  {
    file: 'korean_PP-OCRv5_mobile_rec_infer.onnx',
    path: 'recognition/multi/korean/v5/korean_PP-OCRv5_mobile_rec_infer.onnx',
    sha256: 'ee0dfde503d787c91fd0455daae2eb85311b4b5bdcddf85a54d8c1e0adc157de',
  },
  {
    file: 'ppocrv5_korean_dict.txt',
    path: 'recognition/multi/korean/v5/ppocrv5_korean_dict.txt',
    sha256: 'a3792cbb41215a43e555e16ff4a7f7b18db5dd80cd058637098f0d872f2dd9d6',
  },
]

// onnxruntime-web 이 런타임에 불러오는 WASM 과 그 로더. 번들된 JS 와 같은 버전이어야 한다.
export const ORT_RUNTIME_FILES = ['ort-wasm-simd-threaded.mjs', 'ort-wasm-simd-threaded.wasm']

export function modelUrl(model, revision = MODEL_REVISION) {
  return `${MODEL_REPO}/${revision}/${model.path}`
}

export function modelSources(model) {
  return [`${RELEASE_BASE}/${model.file}`, modelUrl(model)]
}

export function sha256Hex(bytes) {
  return createHash('sha256').update(bytes).digest('hex')
}

// ── 해시 대조 ─────────────────────────────────────────────────────────
// 흐름: 받은 바이트 해시 -> 기대값과 다르면 throw (빌드를 멈춘다)
export function assertDigest(name, bytes, expected) {
  const actual = sha256Hex(bytes)
  if (actual !== expected) {
    throw new Error(`[fetch-ocr-assets] ${name} SHA-256 불일치: 기대 ${expected} · 실제 ${actual}`)
  }
}

// ── 런타임 버전 대조 ──────────────────────────────────────────────────
// 흐름: package.json 이 고정한 버전 vs 설치본 버전 -> 다르면 throw
// package.json 이 범위(^)로 적혀 있어도 막는다 — WASM 과 JS 가 다른 판이면 런타임에 깨진다.
export function assertPinnedVersion(name, declared, installed) {
  if (declared !== installed) {
    throw new Error(
      `[fetch-ocr-assets] ${name} 버전 불일치: package.json ${declared} · 설치본 ${installed} (정확한 버전으로 고정하고 npm ci)`,
    )
  }
}

const RETRY_ATTEMPTS = 3
const RETRY_BASE_MS = 1000
const RETRY_AFTER_MAX_MS = 30000

// 일시적 실패만 다시 시도한다. 404 같은 실패는 기다려도 안 바뀌니 바로 다음 출처로 넘어간다.
function isTransient(status) {
  return status === 429 || status >= 500
}

function retryDelayMs(response, attempt) {
  const seconds = Number(response?.headers?.get('retry-after'))
  if (seconds > 0) return Math.min(seconds * 1000, RETRY_AFTER_MAX_MS)
  return RETRY_BASE_MS * 2 ** attempt
}

// ── 한 출처에서 받기 ──────────────────────────────────────────────────
// 흐름: 요청 -> 성공이면 바이트 반환 -> 일시적 실패면 기다렸다 재시도 -> 횟수를 넘기면 throw
export async function fetchWithRetry(url, { fetchFn = fetch, sleep = delay } = {}) {
  let lastError
  for (let attempt = 0; attempt < RETRY_ATTEMPTS; attempt += 1) {
    let response = null
    try {
      response = await fetchFn(url)
      if (response.ok) return Buffer.from(await response.arrayBuffer())
      lastError = new Error(`HTTP ${response.status}`)
      if (!isTransient(response.status)) throw lastError
    } catch (error) {
      if (error === lastError) throw error
      lastError = error
    }
    if (attempt < RETRY_ATTEMPTS - 1) await sleep(retryDelayMs(response, attempt))
  }
  throw lastError
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

// ── 모델 받기 ─────────────────────────────────────────────────────────
// 흐름: 출처를 차례로 시도 -> 받은 바이트의 해시 대조 -> 전부 실패면 사유를 모아 throw
// 해시가 다른 파일은 어느 출처에서 왔든 쓰지 않는다.
export async function downloadModel(model, options) {
  const failures = []
  for (const url of modelSources(model)) {
    try {
      const bytes = await fetchWithRetry(url, options)
      assertDigest(model.file, bytes, model.sha256)
      return bytes
    } catch (error) {
      failures.push(`${new URL(url).hostname}: ${error.message}`)
    }
  }
  throw new Error(`[fetch-ocr-assets] ${model.file} 받기 실패 (${failures.join(' / ')})`)
}

function hasValidCopy(path, model) {
  return existsSync(path) && sha256Hex(readFileSync(path)) === model.sha256
}

// ── 모델 준비 ─────────────────────────────────────────────────────────
// 흐름: public 사본 -> 빌드 캐시 사본 -> 받기(캐시에도 저장) 순서로 찾는다
// 캐시 파일 이름이 해시라 모델을 바꾸면 옛 사본을 쓸 일이 없다.
export async function ensureModel(model, modelDir, cacheDir, options) {
  const target = join(modelDir, model.file)
  if (hasValidCopy(target, model)) return 'public'
  const cached = join(cacheDir, model.sha256)
  if (hasValidCopy(cached, model)) {
    copyFileSync(cached, target)
    return 'build-cache'
  }
  const bytes = await downloadModel(model, options)
  writeFileSync(target, bytes)
  writeFileSync(cached, bytes)
  return 'downloaded'
}

// 버전을 올리면 옛 경로가 산출물에 남지 않게 지운다.
function removeOtherVersions(parent, keep) {
  for (const entry of readdirSync(parent)) {
    if (entry !== keep) rmSync(join(parent, entry), { recursive: true, force: true })
  }
}

// ── 빌드 산출물의 런타임 참조 대조 (--verify-build) ─────────────────
// 흐름: out/_next 청크에서 ort-wasm-* 파일 이름 수집 -> 하나도 없으면 실패(검사 대상이 사라짐)
//       -> 복사하지 않은 이름이 있으면 실패(운영에서 404 로 OCR 이 조용히 죽는다)
// 실제로 기본 진입점이 JSEP 변형(28MB, CF Pages 한도 초과)을 요청하는 채로 빌드가 초록이었다.
const RUNTIME_REFERENCE = /ort-wasm-[a-z-]+(?:\.[a-z]+)*\.(?:mjs|wasm)/g

export function findRuntimeReferences(text) {
  return [...new Set(text.match(RUNTIME_REFERENCE) ?? [])].sort()
}

export function assertRuntimeReferences(references, provided = ORT_RUNTIME_FILES) {
  if (references.length === 0) {
    throw new Error(
      '[fetch-ocr-assets] 빌드 청크에서 ORT 런타임 참조를 0개 찾았다 — 검사 대상이 사라졌다',
    )
  }
  const missing = references.filter((name) => !provided.includes(name))
  if (missing.length) {
    throw new Error(
      `[fetch-ocr-assets] 빌드가 복사하지 않은 런타임을 요청한다: ${missing.join(', ')}`,
    )
  }
}

function listChunkFiles(dir) {
  return readdirSync(dir, { recursive: true })
    .filter((name) => String(name).endsWith('.js'))
    .map((name) => join(dir, String(name)))
}

function verifyBuild(root) {
  const chunks = listChunkFiles(join(root, 'out', '_next', 'static'))
  const references = findRuntimeReferences(
    chunks.map((file) => readFileSync(file, 'utf8')).join('\n'),
  )
  assertRuntimeReferences(references)
  console.log(`[fetch-ocr-assets] 빌드 런타임 참조 ${references.join(', ')} — 복사본과 일치`)
}

// onnxruntime-web 은 exports 에 package.json 을 열어 두지 않아 require.resolve 로 못 찾는다 —
// 이 패키지가 직접 설치한 경로를 읽는다.
function copyOrtRuntime(root, ortParent) {
  const declared = JSON.parse(readFileSync(join(root, 'package.json'), 'utf8')).dependencies[
    'onnxruntime-web'
  ]
  const ortRoot = join(root, 'node_modules', 'onnxruntime-web')
  const installed = JSON.parse(readFileSync(join(ortRoot, 'package.json'), 'utf8')).version
  assertPinnedVersion('onnxruntime-web', declared, installed)
  const ortDir = join(ortParent, installed)
  mkdirSync(ortDir, { recursive: true })
  removeOtherVersions(ortParent, installed)
  for (const file of ORT_RUNTIME_FILES) {
    copyFileSync(join(ortRoot, 'dist', file), join(ortDir, file))
  }
  return installed
}

async function main() {
  const root = join(dirname(fileURLToPath(import.meta.url)), '..')
  if (process.argv.includes('--verify-build')) {
    verifyBuild(root)
    return
  }
  const modelParent = join(root, 'public', 'ocr', 'models')
  const modelDir = join(modelParent, MODEL_VERSION)
  const ortParent = join(root, 'public', 'ocr', 'ort')
  // Cloudflare Pages 는 .next/cache 를 빌드 사이에 보존한다(대시보드 설정). CI 는 actions/cache 가 맡는다.
  const cacheDir = join(root, '.next', 'cache', 'ocr-models')
  mkdirSync(modelDir, { recursive: true })
  mkdirSync(ortParent, { recursive: true })
  mkdirSync(cacheDir, { recursive: true })
  removeOtherVersions(modelParent, MODEL_VERSION)

  for (const model of MODELS) {
    const state = await ensureModel(model, modelDir, cacheDir)
    console.log(`[fetch-ocr-assets] ${model.file} ${state} (sha256 ok)`)
  }
  const version = copyOrtRuntime(root, ortParent)
  console.log(
    `[fetch-ocr-assets] onnxruntime-web ${version} WASM ${ORT_RUNTIME_FILES.length}개 복사`,
  )
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  main().catch((error) => {
    console.error(error.message)
    process.exit(1)
  })
}
