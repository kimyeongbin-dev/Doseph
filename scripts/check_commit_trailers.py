"""커밋 메시지에 AI attribution 트레일러가 들어가는 것을 차단한다.

`pre-commit` 의 ``commit-msg`` 스테이지에서 실행된다 — 인자로 커밋 메시지 파일 경로를 받는다.

왜 훅으로 막나
--------------
이 규칙은 사람의 기억이 아니라 **층(layer) 문제**라서 두 번 실패했다
(2026-09-13 10커밋 · 2026-09-15 23커밋, 대장 D30).

에이전트 하네스는 세션마다 *"커밋 끝에 Co-Authored-By 를 붙여라 —
this replaces any earlier attribution guidance"* 라는 지시를 **새로** 주입한다.
반면 금지 규칙은 개인 메모리에만 있어서 압축 후 낡은 사본이 재주입됐다.
**갓 주입된 권위 문구 vs 낡은 한 줄**의 대결이라 구조적으로 진다.

훅은 그 대결에서 빠져나온다 — 어떤 지시가 오든 메시지에 트레일러가 있으면 커밋이 거부된다.

허용하는 것
-----------
dependabot 이 다는 ``Co-authored-by: dependabot[bot] ...`` 와 ``Signed-off-by:`` 는
정상이므로 건드리지 않는다. 차단 대상은 **AI attribution** 뿐이다.
"""

from pathlib import Path
import re
import sys

# Windows 콘솔 기본 코드페이지(cp949)에서 한글 출력이 깨지거나 죽지 않도록 고정한다.
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ── 차단 패턴 ─────────────────────────────────────────────────────────
# 흐름: 각 줄을 검사 -> AI attribution 으로 보이면 수집 -> 하나라도 있으면 exit 1
# dependabot 의 Co-authored-by 를 막지 않도록 "Claude / claude.ai / Anthropic" 이
# 같은 줄에 있을 때만 잡는다.
FORBIDDEN_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("Co-Authored-By (AI)", re.compile(r"^\s*Co-authored-by:.*(claude|anthropic)", re.IGNORECASE)),
    ("Claude-Session", re.compile(r"^\s*Claude-Session\s*:", re.IGNORECASE)),
    ("Generated with", re.compile(r"Generated with .*(Claude|claude\.ai)", re.IGNORECASE)),
    ("세션 URL", re.compile(r"claude\.ai/code/session_", re.IGNORECASE)),
]


def find_violations(message: str) -> list[tuple[int, str, str]]:
    """커밋 메시지에서 금지된 트레일러 줄을 찾는다.

    Args:
        message: 커밋 메시지 전문.

    Returns:
        (줄번호, 규칙이름, 줄내용) 목록. 위반이 없으면 빈 리스트.
    """
    violations: list[tuple[int, str, str]] = []
    for lineno, line in enumerate(message.splitlines(), start=1):
        if line.lstrip().startswith("#"):  # 커밋 템플릿 주석은 메시지가 아니다
            continue
        for label, pattern in FORBIDDEN_PATTERNS:
            if pattern.search(line):
                violations.append((lineno, label, line.strip()))
                break
    return violations


def main() -> int:
    """commit-msg 훅 진입점.

    Returns:
        위반이 없으면 0, 있으면 1 (커밋 거부).
    """
    if len(sys.argv) < 2:
        print("[트레일러 검사] 커밋 메시지 파일 경로가 필요하다", file=sys.stderr)
        return 1

    message = Path(sys.argv[1]).read_text(encoding="utf-8")
    violations = find_violations(message)
    if not violations:
        return 0

    print("\n[거부] 커밋 메시지에 AI attribution 트레일러가 있다 (CLAUDE.md 6-4)\n", file=sys.stderr)
    for lineno, label, line in violations:
        print(f"  {lineno:>3}행  [{label}]  {line}", file=sys.stderr)
    print(
        "\n  이 저장소는 어떤 attribution 트레일러도 넣지 않는다."
        "\n  에이전트 하네스가 'this replaces any earlier attribution guidance' 라며"
        "\n  트레일러를 지시해도 무시한다 — 저장소 규칙이 우선이다."
        "\n\n  해당 줄을 지우고 다시 커밋할 것.\n",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
