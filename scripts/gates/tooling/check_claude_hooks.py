"""Claude 훅 배선 게이트 — **훅이 조용히 사라지는 것**을 막는다 (B-10 · §0-3 ①).

왜 필요한가
-----------
`PreToolUse` 훅(`scripts/hooks/read_precondition.py`)이 **상시 세트를 주입**하고
`docs-private/` 편집 전 `FILING.md` 읽기를 **전제조건**으로 만든다. 그 설계는
**훅이 실제로 배선돼 있을 때만** 성립한다.

🔴 그런데 **훅은 조용히 없어진다**:

- `.claude/settings.json` 은 **`.gitignore` 안**이다(2026-09-22 사용자 결정 = A안).
  git 이 안 보므로 **사라져도 diff 에 안 뜨고 히스토리에도 없다** → `LOCAL_RESIDUE` **L-9**.
- JSON 이 깨지면 **그 파일의 설정이 통째로** 죽는다.
- 훅 스크립트를 옮기거나 이름을 바꾸면 설정은 **옛 경로를 가리킨 채 조용히 실패**한다.

그리고 **성공은 보이지 않는다** — UI 는 훅이 실패하거나 느릴 때만 표시한다.
*"돌고 있겠지"* 를 확인으로 쓰면 `D61`(감시기의 침묵을 «이상 없음» 으로 읽었다)이 재현된다.

🔴 이 게이트가 **못 하는 것** (한계 선언)
------------------------------------------
- **훅이 «실제로 발동하는지» 모른다.** 설정과 스크립트가 제자리에 있는지만 본다.
  설정 감시자가 그 세션에서 파일을 안 읽었을 수도 있다(그럴 땐 `/hooks` 를 열거나 재시작).
- **`disableAllHooks`·관리 정책으로 통째 비활성된 것은 못 본다** — 그 층은 이 파일 밖이다.
  그래서 **최소 핵 8줄은 `CLAUDE.md` 본문에 상주**시켜 훅과 무관하게 살게 했다.
- **훅의 판정이 옳은지 모른다** — 그건 검출률·오탐 측정의 몫이다(완료기록에 실측).

사용
----
    ... check_claude_hooks
"""

import json
from pathlib import Path
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parents[3]
SETTINGS = REPO_ROOT / ".claude" / "settings.json"
HOOK_SCRIPT = REPO_ROOT / "scripts" / "hooks" / "read_precondition.py"

# 🔑 실측이다. 2026-09-22 기준 `PreToolUse` 1종 — 계승 계획의 정지 규칙이 «1종으로 시작» 이다.
MIN_HOOK_ENTRIES = 1
REQUIRED_EVENT = "PreToolUse"
REQUIRED_FRAGMENT = "read_precondition"


# ── 훅 배선을 센다 ────────────────────────────────────────────────────
# 흐름: 설정 존재 -> JSON 파싱 -> PreToolUse 항목 -> command 가 스크립트를 가리키나
#       -> 그 스크립트가 실재하나
# 🔴 «설정에 적혀 있다» 와 «가리키는 것이 있다» 는 다른 사실이다. 둘 다 본다.
def main() -> int:
    """훅 설정과 스크립트가 짝을 이루는지 검사한다.

    Returns:
        종료코드 — 0 이면 통과.
    """
    problems: list[str] = []

    if not SETTINGS.exists():
        print(f"❌ Claude 훅 설정이 없다: {SETTINGS.relative_to(REPO_ROOT).as_posix()}")
        print("   `.claude/` 는 gitignore 라 **사라져도 diff 에 안 뜬다**(LOCAL_RESIDUE L-9).")
        print("   복원법은 `docs-private/LOCAL_RESIDUE.md` 의 L-9 항목에 있다.")
        return 1

    try:
        data = json.loads(SETTINGS.read_text(encoding="utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        print(f"❌ `.claude/settings.json` 이 깨졌다 — **그 파일의 설정이 통째로 죽는다**: {exc}")
        return 1

    entries = data.get("hooks", {}).get(REQUIRED_EVENT, [])
    if len(entries) < MIN_HOOK_ENTRIES:
        problems.append(f"`{REQUIRED_EVENT}` 훅이 **{len(entries)}개**로 바닥값 {MIN_HOOK_ENTRIES} 아래다")

    commands = [str(h.get("command", "")) for entry in entries for h in entry.get("hooks", []) if isinstance(h, dict)]
    if not any(REQUIRED_FRAGMENT in c for c in commands):
        problems.append(
            f"`{REQUIRED_EVENT}` 훅이 **`{REQUIRED_FRAGMENT}` 를 부르지 않는다** — "
            f"읽기 전제조건이 돌지 않는다. 실제 명령: {commands or '없음'}"
        )

    if not HOOK_SCRIPT.exists():
        problems.append(
            f"설정은 있는데 **스크립트가 없다**: {HOOK_SCRIPT.relative_to(REPO_ROOT).as_posix()} — "
            "설정이 옛 경로를 가리킨 채 **조용히 실패**한다"
        )

    if problems:
        print("❌ Claude 훅 배선 검사 실패")
        for line in problems:
            print(f"   - {line}")
        return 1

    print(
        f"✅ Claude 훅 배선 — `{REQUIRED_EVENT}` {len(entries)}종(바닥값 {MIN_HOOK_ENTRIES}) · "
        "스크립트 실재. ⚠️ **발동 여부는 여기서 못 본다**(한계 선언)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
