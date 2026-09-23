r"""커밋 제목 위생 검사 — 붙여넣기 잔재가 히스토리에 박히는 것을 막는다.

**왜 이 게이트가 있나**: 2026-09-13 하루에 **8개 커밋 제목이 `@ ` 로 시작**했다.

    @ fix(mypy): python_executable 미지정 - venv 타입해석 정상화
    @ ci(mypy): MyPy baseline 게이트 도입 - 신규 타입오류만 차단

의미 없는 두 글자인데, 히스토리는 **되돌리기가 비싸다.** 이 8건은 `HEAD~119` 근처이고
`origin/main` 을 포함한 **원격 15개 브랜치**에 들어 있어, 고치려면 121개 커밋 재작성 +
force push 가 필요하다(2026-09-15 사용자 판단: **고치지 않는다**).
→ 남은 수단은 **다음 것을 막는 것**뿐이다.

## 무엇을 막고 무엇을 막지 않나

| 막는다 | 이유 |
|---|---|
| 제목이 `@` 로 시작 | 실제로 8번 일어난 붙여넣기 잔재 |
| 제목이 **공백**으로 시작 | 같은 종류(실측 2건) |
| 제목이 **BOM**(`\\ufeff`)으로 시작 | 같은 종류(실측 2건). 눈에 안 보여 더 위험하다 |
| 제목이 **비어 있음** | — |
| 제목이 **이모지**로 시작 (`✨ feat:`) | 팀 시절 규약의 잔재. **규약이 완전히 바뀌었다**(2026-09-15 사용자 확인) |
| 제목이 **대괄호**로 시작 (`[긴급]`) | 같은 이유 |
| 제목이 **한글**로 시작 | 제목은 `<type>: <한국어 요약>` — 타입 접두가 앞에 온다 |

규칙을 한 줄로 줄이면 **"제목은 ASCII 영문자로 시작한다"** 이다.
`feat:`·`fix:`·`Merge ...` 는 통과하고, 이모지·대괄호·`@`·공백·BOM·한글 시작은 거부된다.

⚠️ **아직 강제하지 않는 것**: *어떤* 타입 접두를 허용할지(`feat`/`fix`/... 목록)와
`<type>(scope): ` 형식 자체는 이 게이트가 보지 않는다. `CLAUDE.md` §6.2 의 6종과
실제 히스토리(`ci`·`revert` 등)가 아직 어긋나 있어, **규약을 한 벌로 재작성한 뒤**
(로드맵 후속 큐 `문서-3`) 그때 형식 검사를 붙인다. 지금 붙이면 정당한 커밋이 막힌다.

실측(2026-09-15, 전체 1057 커밋): 이 규칙에 걸리는 것 **60건** — 전부 팀 시절
스타일이거나 붙여넣기 오염이다. 히스토리는 고치지 않는다(되돌리기 비용 > 이득).

✅ **음성 대조 표본** — 이것들은 **통과해야** 한다:
  - ``feat: ...`` · ``fix(fe): ...`` 처럼 ASCII 영문자로 시작하는 정상 제목
  - 본문 첫 줄이 ``#`` 주석이고 그 다음 줄이 정상 제목인 경우 (주석은 건너뛴다)
"""

from pathlib import Path
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# 규약 한 줄: **제목은 ASCII 영문자로 시작한다.** 그 외는 전부 거부다 —
# 이모지·대괄호·`@`·공백·BOM·한글 접두. (2026-09-15 규약 전환: 팀 시절 이모지 규약 폐기)
ASCII_LETTERS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")

#: 🔴 **허용 타입 — Conventional Commits 표준 11종 + `merge`**(2026-09-23, `문서-3`).
#:
#: 규약이 6종만 말하는 동안 **히스토리에는 16종이 더 있었다**(실측 2026-09-23):
#: `merge` 24 · `ci` 13 · `design` 6 · `ux` 5 · `security` 5 · `style` 4 · `perf` 3 …
#: 그중 `ci`·`perf`·`style`·`revert` 는 **표준인데 규약이 빠뜨린 것**이었고,
#: `mypage`·`ocr`·`chatbot`·`mainpage` 는 **기능명을 앞머리로 쓴 것**(scope 자리다), `paln` 은 오타다.
#:
#: 🔑 **어휘를 넓히되 기계가 잡게 한다** — 문서에만 두면 또 갈린다. 그게 `문서-3` 이었다.
#: ⚠️ `merge` 는 git 이 만드는 제목이라 사람이 고르는 타입이 아니다. 그래서 별도로 허용한다.
ALLOWED_TYPES = frozenset({
    "feat",
    "fix",
    "docs",
    "style",
    "refactor",
    "perf",
    "test",
    "build",
    "ci",
    "chore",
    "revert",
    "merge",
})

#: `type(scope): 설명` 또는 `type: 설명`. scope 는 선택이고 `!`(breaking)도 받는다.
CONVENTIONAL = re.compile(r"^([a-z]+)(\([^)]+\))?!?: ")

# BOM 은 소스에 날것으로 두면 눈에 안 보여 다음 사람이 지운다 -> 이름을 붙여 고정한다.
BOM = "﻿"


# ── 앞머리 위생 ───────────────────────────────────────────────────────
# 흐름: 첫 글자가 ASCII 영문자인가 -> 아니면 «왜» 인지 이름을 붙인다
# 🔑 «깨끗한가» 와 «약속한 타입인가» 는 다른 질문이라 함수를 나눈다.
def hygiene_reason(subject: str) -> str:
    """앞머리가 오염됐으면 그 이유를, 깨끗하면 빈 문자열을 돌려준다.

    Args:
        subject: 커밋 제목.

    Returns:
        오염 이유. 깨끗하면 `""`.
    """
    first = subject[0]
    if first in ASCII_LETTERS:
        return ""
    if first.isspace():
        return "제목이 공백으로 시작한다"
    if first == BOM:
        return "제목이 BOM(보이지 않는 문자)으로 시작한다"
    if first == "@":
        return "제목이 '@' 로 시작한다 (붙여넣기 잔재)"
    if first == "[":
        return "제목이 대괄호로 시작한다 — 팀 시절 스타일이고 지금 규약이 아니다"
    if not first.isascii():
        return f"제목이 ASCII 가 아닌 문자({first!r})로 시작한다 — 이모지·한글 접두 금지"
    return f"제목이 영문자가 아닌 {first!r} 로 시작한다"


# ── 커밋 제목 위생 검사 (commit-msg 훅) ─────────────────────────────────
# 흐름: 커밋 메시지 파일 읽기 -> 주석·빈 줄을 건너뛰고 첫 실제 줄(제목)을 찾는다
#       -> 앞머리가 오염됐으면 non-zero 로 커밋 거부
def main() -> int:
    """커밋 메시지 파일을 읽어 제목 규약을 검사한다."""
    if len(sys.argv) < 2:
        print("[거부] 커밋 메시지 파일 경로가 없다.", file=sys.stderr)
        return 1

    # 🔴 fail-closed: 파일이 없거나 비어 있으면 *"위반이 없다"* 가 아니라 *"검사하지 못했다"* 이다.
    #    훅 배선이 어긋나 빈 경로가 넘어와도 조용히 통과하면, 게이트가 있는 줄 알면서 없는 상태가 된다.
    target = Path(sys.argv[1])
    if not target.is_file():
        print(f"[거부] 커밋 메시지 파일이 없다 — {target}", file=sys.stderr)
        print("  훅 배선이 어긋났을 수 있다. 검사하지 못했으므로 통과시키지 않는다(fail-closed).", file=sys.stderr)
        return 1

    message = target.read_text(encoding="utf-8", errors="replace")

    subject = ""
    for line in message.split("\n"):
        if line.startswith("#") or not line.strip():
            continue
        subject = line
        break

    if not subject:
        print("[거부] 커밋 제목이 비어 있다.", file=sys.stderr)
        return 1

    reason = hygiene_reason(subject)

    if reason:
        print(f"\n[거부] 커밋 제목 앞머리가 오염됐다 — {reason}.\n", file=sys.stderr)
        print(f"  제목: {subject!r}", file=sys.stderr)
        print(
            "\n  규약: 제목은 ASCII 영문자로 시작한다 (예: 'feat: ...', 'fix(fe): ...')."
            "\n  이모지 접두는 팀 시절 규약이고 지금은 금지다(2026-09-15 규약 전환)."
            "\n  2026-09-13 에 8개 커밋이 '@ ' 로 시작한 채 박혔고 원격 15개 브랜치에 퍼져"
            "\n  되돌릴 수 없게 됐다. 앞머리를 지우고 다시 커밋하라.\n",
            file=sys.stderr,
        )
        return 1

    # ── 타입 어휘 (2026-09-23 신설, `문서-3`) ──────────────────────────
    # 🔴 앞머리가 «깨끗한가» 와 «약속한 타입인가» 는 다른 질문이다.
    #    전자는 2026-09-15 부터 봤고, 후자는 아무도 안 봐서 16종이 새로 생겼다.
    # 🔴 git 이 **스스로 만드는** 제목은 사람이 고른 타입이 아니다 — 면제한다.
    #    `Merge branch 'x'` · `Revert "..."` 는 대문자로 시작하고 콜론이 없다.
    #    ⚠️ 이걸 안 빼면 **모든 머지가 막힌다** — 과잉 차단하는 게이트는 사람이 끄고,
    #    그러면 옆의 정확한 게이트까지 죽는다(`QUALITY_GATES` §2-1).
    if subject.startswith(("Merge ", "Revert ")):
        return 0

    matched = CONVENTIONAL.match(subject)
    if matched is None:
        print("\n[거부] 커밋 제목이 `type: 설명` 꼴이 아니다.\n", file=sys.stderr)
        print(f"  제목: {subject!r}", file=sys.stderr)
        print(
            "\n  꼴: `type: 설명` 또는 `type(scope): 설명` (예: `fix(fe): ...`)."
            f"\n  타입: {' · '.join(sorted(ALLOWED_TYPES))}\n",
            file=sys.stderr,
        )
        return 1

    kind = matched.group(1)
    if kind not in ALLOWED_TYPES:
        print(f"\n[거부] `{kind}` 은 약속한 타입이 아니다.\n", file=sys.stderr)
        print(f"  제목: {subject!r}", file=sys.stderr)
        print(
            f"\n  타입: {' · '.join(sorted(ALLOWED_TYPES))}"
            "\n  🔑 **기능명은 앞머리가 아니라 scope 다** — `ocr: ...` 이 아니라 `feat(ocr): ...`."
            "\n  정본 = `CLAUDE.md` §6 · 경위 = `DOC_TRUTH_DRIFT` §C-2(`문서-3`).\n",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
