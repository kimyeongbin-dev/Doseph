// ── 브라우저 OCR 자산 준비 (빌드·dev 전 단계) ─────────────────────────
// 흐름: 모델 3종 -> 있으면 SHA-256 대조, 없거나 다르면 고정 리비전에서 받기 -> 대조 실패면 빌드 중단
//       -> onnxruntime-web 설치본 버전 확인 -> WASM 런타임 2종을 public/ocr/ort/ 로 복사
// 전제: 결과물(public/ocr/)은 커밋하지 않는다(.gitignore) — 18MB 바이너리를 저장소에 넣지 않으려고.
//       같은 출처로 내보내므로 런타임에 제3자(Hugging Face)로 요청이 나가지 않는다.

import { createHash } from 'node:crypto'
import {
  copyFileSync,
  existsSync,
  mkdirSync,
  readdirSync,
  readFileSync,
  writeFileSync,
} from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

// 모델 저장소의 커밋을 고정한다 — main 을 가리키면 저쪽이 바뀔 때 조용히 다른 모델을 받는다.
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

async function ensureModel(model, modelDir) {
  const target = join(modelDir, model.file)
  if (existsSync(target) && sha256Hex(readFileSync(target)) === model.sha256) return 'cached'
  const response = await fetch(modelUrl(model))
  if (!response.ok)
    throw new Error(`[fetch-ocr-assets] ${model.file} 받기 실패: HTTP ${response.status}`)
  const bytes = Buffer.from(await response.arrayBuffer())
  assertDigest(model.file, bytes, model.sha256)
  writeFileSync(target, bytes)
  return 'downloaded'
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
function copyOrtRuntime(root, ortDir) {
  const declared = JSON.parse(readFileSync(join(root, 'package.json'), 'utf8')).dependencies[
    'onnxruntime-web'
  ]
  const ortRoot = join(root, 'node_modules', 'onnxruntime-web')
  const installed = JSON.parse(readFileSync(join(ortRoot, 'package.json'), 'utf8')).version
  assertPinnedVersion('onnxruntime-web', declared, installed)
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
  const modelDir = join(root, 'public', 'ocr', 'models')
  const ortDir = join(root, 'public', 'ocr', 'ort')
  mkdirSync(modelDir, { recursive: true })
  mkdirSync(ortDir, { recursive: true })

  for (const model of MODELS) {
    const state = await ensureModel(model, modelDir)
    console.log(`[fetch-ocr-assets] ${model.file} ${state} (sha256 ok)`)
  }
  const version = copyOrtRuntime(root, ortDir)
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
