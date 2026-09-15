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

**막지 않는 것**: 이모지 접두(`✨ feat:`)·`[긴급]` 같은 대괄호 스타일.
팀 시절 규약(`.github/commit_template.txt`, 2026-09-15 삭제)이 실제로 그렇게 요구했다.
**소급해서 틀렸다고 판정하지 않는다.** prefix 규약 전체를 강제할지는 규약을 한 벌로
재작성하는 후속 항목(로드맵 후속 큐 `문서-3`)에서 정한다.

실측: 전체 1057 커밋 중 이 규칙에 걸리는 것 **12건** — 전부 진짜 오염이고,
이모지·대괄호 스타일 23건은 통과한다.
"""

from pathlib import Path
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# "﻿" = BOM. 소스에 날것으로 두면 눈에 안 보여 다음 사람이 지운다 -> 이스케이프로 고정.
BAD_LEADING = ("@", "﻿")


# ── 커밋 제목 위생 검사 (commit-msg 훅) ─────────────────────────────────
# 흐름: 커밋 메시지 파일 읽기 -> 주석·빈 줄을 건너뛰고 첫 실제 줄(제목)을 찾는다
#       -> 앞머리가 오염됐으면 non-zero 로 커밋 거부
def main() -> int:
    if len(sys.argv) < 2:
        print("[거부] 커밋 메시지 파일 경로가 없다.", file=sys.stderr)
        return 1

    message = Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace")

    subject = ""
    for line in message.split("\n"):
        if line.startswith("#") or not line.strip():
            continue
        subject = line
        break

    if not subject:
        print("[거부] 커밋 제목이 비어 있다.", file=sys.stderr)
        return 1

    first = subject[0]
    reason = ""
    if first in BAD_LEADING:
        reason = f"제목이 {first!r} 로 시작한다"
    elif first.isspace():
        reason = "제목이 공백으로 시작한다"

    if reason:
        print(f"\n[거부] 커밋 제목 앞머리가 오염됐다 — {reason}.\n", file=sys.stderr)
        print(f"  제목: {subject!r}", file=sys.stderr)
        print(
            "\n  2026-09-13 에 같은 이유로 8개 커밋이 '@ ' 로 시작한 채 박혔고,"
            "\n  원격 15개 브랜치에 퍼져 되돌릴 수 없게 됐다. 앞머리를 지우고 다시 커밋하라.\n",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
