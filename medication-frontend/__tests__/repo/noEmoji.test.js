// FE 코드·주석 이모지 금지(FE CLAUDE.md 필수 12번)를 기계로 잠근다 — QA-67
//
// 규칙만 있고 검사기가 없어서 19줄이 쌓였다. 판정은 «기본으로 그림으로 그려지는 문자»
// (Emoji_Presentation)와 «이모지 표시 선택자(U+FE0F)가 붙은 문자» 다. 그래서 ★(U+2605)·©·✓·→ 같은
// 글자 기호는 통과한다 — Extended_Pictographic 은 ★·© 까지 잡아 과잉 차단이라 쓰지 않았다.

import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'

import { describe, expect, it } from 'vitest'

const ROOT = join(__dirname, '..', '..')
const SCAN_DIRS = ['src', '__tests__', 'scripts', 'e2e']
const SOURCE = /\.(js|jsx|mjs)$/
const EMOJI = /\p{Emoji_Presentation}|\p{Extended_Pictographic}️/u
// 이 파일은 판정 예시를 들어야 해서 스스로를 뺀다.
const SELF = relative(ROOT, __filename).replaceAll('\\', '/')

function listSources(dir) {
  return readdirSync(dir).flatMap((name) => {
    const full = join(dir, name)
    if (statSync(full).isDirectory()) return name === 'node_modules' ? [] : listSources(full)
    return SOURCE.test(name) ? [full] : []
  })
}

const files = SCAN_DIRS.flatMap((dir) => listSources(join(ROOT, dir))).filter(
  (file) => relative(ROOT, file).replaceAll('\\', '/') !== SELF,
)

describe('FE 코드 이모지 금지', () => {
  it('검사 대상이 줄지 않았다 (glob 이 좁아지면 0건으로 통과한다)', () => {
    expect(files.length).toBeGreaterThanOrEqual(100)
  })

  it('판정식이 이모지는 잡고 글자 기호는 놓아준다', () => {
    for (const emoji of ['⚠️', '💡', '🔥', '✅']) expect(EMOJI.test(emoji)).toBe(true)
    for (const symbol of ['★', '©', '✓', '→', '⚠']) expect(EMOJI.test(symbol)).toBe(false)
  })

  it('코드·주석에 이모지가 없다', () => {
    const hits = files.flatMap((file) =>
      readFileSync(file, 'utf8')
        .split('\n')
        .flatMap((line, i) =>
          EMOJI.test(line) ? [`${relative(ROOT, file).replaceAll('\\', '/')}:${i + 1}`] : [],
        ),
    )
    expect(hits).toEqual([])
  })
})
