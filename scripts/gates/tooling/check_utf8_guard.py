r"""UTF-8 방어 누락 검사 — 한글·이모지를 찍는 스크립트가 cp949 에서 죽지 않게 한다.

**왜 이 게이트가 있나**: 2026-09-15 하루에 **같은 크래시를 세 번** 밟았다(대장 D36).

    UnicodeEncodeError: 'cp949' codec can't encode character '\\u2014'

셋 다 원인이 같은데 **표면이 달라서** "그건 이미 처리했다"는 감각이 생겼다:

    ① 자식 프로세스의 출력   -> 부모가 `PYTHONIOENCODING=utf-8` 을 넘겨야 한다
    ② 스크립트 자신의 print  -> 자기 stdout 을 `reconfigure` 해야 한다
    ③ 일회성 python 명령     -> 세션 환경(.claude/settings.local.json 의 env)이 덮는다

이 게이트는 **②를 기계로 막는다.** ①은 각 실행기가, ③은 세션 환경이 맡는다.

**왜 위험한가**: 이 크래시는 *하려던 일을 다 끝낸 뒤 출력 단계에서* 터진다.
종료코드는 "위반"과 "크래시"를 구분하지 못하므로 **성공이 실패로 보인다**(거짓 빨강).
반대로 출력만 깨지고 통과하는 경우엔 **아무도 눈치채지 못한다**.

⚠️ 검사 대상은 `scripts/` **전체**(하위 폴더 포함)다. `app/`·`ai_worker/` 는 `print` 가
금지돼 있고(CLAUDE.md §9) 로깅 핸들러가 인코딩을 따로 잡는다.

✅ **음성 대조 표본** — 이것들은 **통과해야** 한다:
  - 비-ASCII 를 **출력하지 않는** 스크립트 (방어가 없어도 깨질 일이 없다)
  - ``stdout``·``stderr`` 를 **둘 다** 고정한 스크립트 (한쪽만이면 잡혀야 한다)
"""

import ast
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# stdout/stderr 방어가 import 보다 먼저여야 한다 — cp949 크래시 방지(대장 D36).
from scripts.gates._root import REPO_ROOT  # noqa: E402

SCRIPTS_DIR = REPO_ROOT / "scripts"

# 목적지별 방어. **stdout 과 stderr 는 서로를 지켜주지 않는다** —
# 기존 게이트 4종은 전부 `file=sys.stderr` 로 찍고 stderr 만 방어하고 있었는데,
# 문자열 `reconfigure` 만 보는 즉석 검사는 그걸 "stdout 도 안전"으로 잘못 읽었다(D31).
GUARD = {
    "stdout": "sys.stdout.reconfigure",
    "stderr": "sys.stderr.reconfigure",
}

# 이 게이트 자신과, 검사 대상이 아닌 것.
EXCLUDE = {"__init__.py"}


# ── 비-ASCII 출력의 목적지 판정 ─────────────────────────────────────────
# 흐름: AST 파싱 -> print() 호출을 찾아 인자에 비-ASCII 상수가 있나 검사
#       -> `file=sys.stderr` 면 stderr, 아니면 stdout 으로 분류
# 주석·docstring 은 세지 않는다 — 출력되지 않으므로 크래시와 무관하다.
def non_ascii_targets(source: str) -> set[str]:
    targets: set[str] = set()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return targets
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print"):
            continue
        has_non_ascii = any(
            isinstance(chunk, ast.Constant) and isinstance(chunk.value, str) and not chunk.value.isascii()
            for chunk in ast.walk(node)
        )
        if not has_non_ascii:
            continue
        target = "stdout"
        for keyword in node.keywords:
            if keyword.arg == "file" and ast.unparse(keyword.value).endswith("stderr"):
                target = "stderr"
        targets.add(target)
    return targets


# ── 게이트 본문 ─────────────────────────────────────────────────────────
# 흐름: scripts/**.py 순회 -> 비-ASCII 를 찍나 -> 방어가 있나 -> 없으면 실패
#
# 🔴 **rglob 이어야 한다.** 2026-09-16 게이트를 `scripts/gates/<분류>/` 로 재편했을 때
# 이 함수가 `glob("*.py")`(직하만) 라서 **게이트 11개가 통째로 검사 범위에서 빠졌는데
# "1건 전부 방어됨" 이라고 초록을 냈다.** 대상이 줄어든 것을 스스로 보고하지 못한 것이
# 진짜 결함이다 — `check_plan_archives` 가 같은 glob 함정에 빠질 뻔했던 것과 같다.
# 그래서 아래 하한선 검사를 함께 둔다.
MIN_EXPECTED = 5


def main() -> int:
    offenders: list[str] = []
    checked = 0

    for path in sorted(SCRIPTS_DIR.rglob("*.py")):
        if path.name in EXCLUDE or "__pycache__" in path.parts:
            continue
        source = path.read_text(encoding="utf-8")
        targets = non_ascii_targets(source)
        if not targets:
            continue
        checked += 1
        missing = sorted(t for t in targets if GUARD[t] not in source)
        if missing:
            name = path.relative_to(REPO_ROOT).as_posix()
            offenders.append(f"{name}  (방어 없는 출력: {' · '.join(missing)})")

    if checked < MIN_EXPECTED:
        # 0건만이 아니라 **줄어든 것**도 실패로 본다. 폴더를 재편하거나 glob 을 좁히면
        # 검사 범위가 조용히 사라지는데, 그때 게이트는 "깨끗하다"고 초록을 낸다.
        # 실제로 이 게이트가 그렇게 눈이 멀었다(2026-09-16, 11건 → 1건).
        print(f"❌ 검사 대상이 {checked}건뿐이다 (기대 최소 {MIN_EXPECTED}건).")
        print("   경로·glob 이 좁아져 검사 범위가 사라졌을 가능성이 높다 — 줄어든 것도 실패다(fail-closed).")
        return 1

    if offenders:
        print(f"❌ 한글·이모지를 출력하는데 UTF-8 방어가 없는 스크립트 {len(offenders)}건:")
        for name in offenders:
            print(f"   - {name}")
        print()
        print("   고치는 법 — 파일 첫머리(import 직후)에 두 줄을 넣는다:")
        print('     sys.stdout.reconfigure(encoding="utf-8", errors="replace")')
        print('     sys.stderr.reconfigure(encoding="utf-8", errors="replace")')
        print("   자식 프로세스를 띄운다면 env 에 PYTHONIOENCODING=utf-8 도 함께 넘긴다.")
        return 1

    print(f"✅ UTF-8 방어 검사 통과 — 비-ASCII 를 출력하는 스크립트 {checked}건 전부 방어됨.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
