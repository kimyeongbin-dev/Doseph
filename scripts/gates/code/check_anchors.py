"""코드 주석의 ``QA-##`` 앵커가 실재하는 큐 항목을 가리키는지 센다.

`pre-commit` 의 ``pre-push`` 스테이지에서 실행된다.

왜 훅으로 세나
--------------
앵커는 **오류 ↔ 코드 위치**를 잇는 유일한 사람-작성 연결고리다
(CLAUDE.md 규약: *"코드 주석에 `QA-##` 를 적어 둔다. 주석 ↔ 문서가 양방향으로 찾아진다"*).
그런데 지금까지 **아무도 그 연결을 검증하지 않았다.** 오타 하나, 큐에서 지운 항목 하나면
연결이 조용히 끊어지고, 다음 사람은 없는 항목을 찾아 헤맨다.

무엇을 잡고 무엇을 안 잡나
--------------------------
- 잡는다: 코드가 **큐에 없는 ID** 를 달고 있는 경우 (오타 · 철회된 항목 · 오래된 참조)
- 안 잡는다: 큐에 있는데 코드에 앵커가 없는 경우 → **정상이다.** 미착수 항목은
  아직 코드에 손대지 않았으므로 앵커가 없는 게 당연하다. 이건 게이트가 아니라
  ``defect_map.py`` 의 보고 대상이다.

`docs-private/` 는 git 미추적이지만 이 훅은 `pre-push` **로컬 전용**이라 CI 에서 돌지 않는다.
→ 대상이 없으면 **실패**한다(fail-closed). *"검사 대상이 없다"* 와 *"문제가 없다"* 는 다른 사실이고,
구분하지 못하면 게이트가 **자기가 죽었다는 것을 초록으로 보고**한다(`docs/QUALITY_GATES.md` §2-5-1)
(로컬 개발자용 게이트지, 파이프라인 게이트가 아니다 — `check_plan_archives.py` 와 같은 결).

✅ **음성 대조 표본** — 이것들은 **통과해야** 한다:
  - 큐에 실재하는 ``QA-##`` 를 가리키는 코드 주석 (정상 앵커)
  - ``QA-`` 가 문장 안에 그냥 등장하는 산문 (앵커 아님 — 잡으면 오탐)
  전부 "끊김"으로만 확인하면 *"아무 주석이나 다 잡는"* 상태와 구분되지 않는다.
"""

from pathlib import Path
import re
import sys

# Windows 콘솔 기본 코드페이지(cp949)에서 한글 출력이 깨지거나 죽지 않도록 고정한다.
# 🔴 stdout 과 stderr 는 **서로를 보호하지 않는다** — 한쪽만 고정하면 다른 쪽이 크래시한다(대장 D36).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# stdout/stderr 방어가 import 보다 먼저여야 한다 — cp949 크래시 방지(대장 D36).
from scripts.gates._root import PRIVATE

#: 바닥값 — *0건*만이 아니라 **줄어든 것도 실패**다(`CLAUDE.md` §6-1, 대장 D31).
#: 실제로 `check_utf8_guard` 가 대상 11건 → 1건이 되고도 초록을 냈다.
#: 이 값은 **손으로 올린다** — 대상이 늘면 그때 올리는 것이 의식적인 결정이 된다.
MIN_ANCHORS = 12
MIN_QUEUE = 38

QUEUE_PATH = PRIVATE / "FOLLOWUP_QUEUE.md"

#: 앵커는 **소스 코드**에서만 읽는다. 문서까지 훑으면 큐 문서 자신이 잡혀
#: 모든 ID 가 "알려진 ID" 가 되고 게이트는 통과 기계가 된다.
SOURCE_SUFFIXES = frozenset({".py", ".js", ".jsx", ".ts", ".tsx"})

#: 스캔 제외 — 생성물·의존성·캐시.
SKIP_DIRS = frozenset({".git", "node_modules", "__pycache__", ".venv", "venv", "out", ".next", "htmlcov"})

ANCHOR = re.compile(r"\bQA-\d+\b")


# ── 소스 트리에서 앵커 수집 ───────────────────────────────────────────
# 흐름: 소스 파일 순회 -> 줄 단위 QA-## 추출 -> {ID: [경로:줄, ...]}
# 같은 ID 가 여러 곳에 있으면 전부 모은다 — 하나만 세면 영향 범위를 놓친다.
def find_anchors(root: Path) -> dict[str, list[str]]:
    """Collect ``QA-##`` anchors from source files under ``root``.

    Args:
        root: Directory to scan.

    Returns:
        Mapping of anchor ID to ``path:line`` locations, sorted by ID.
    """
    found: dict[str, list[str]] = {}
    for path in sorted(root.rglob("*")):
        if path.suffix not in SOURCE_SUFFIXES or not path.is_file():
            continue
        if SKIP_DIRS & set(path.parts):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        # 경로는 `/` 로 정규화한다 — Windows 에서 만든 출력이 CI·문서와 달라지면
        # 같은 위치를 두 가지로 부르게 된다(대장 D11, 교차플랫폼 축).
        location = path.as_posix()
        for lineno, line in enumerate(text.splitlines(), start=1):
            for anchor_id in ANCHOR.findall(line):
                found.setdefault(anchor_id, []).append(f"{location}:{lineno}")
    return dict(sorted(found.items()))


# ── 큐에서 알려진 ID 읽기 ─────────────────────────────────────────────
# 흐름: 큐 마크다운 읽기 -> QA-## 전부 추출 -> 집합
# 파일이 없으면 빈 집합을 준다. "전부 통과" 가 아니라 **판단을 호출자에게 넘기는** 것이다.
def read_known_ids(queue: Path) -> set[str]:
    """Read every ``QA-##`` id registered in the follow-up queue.

    Args:
        queue: Path to the queue markdown document.

    Returns:
        Set of known ids; empty when the queue is unavailable.
    """
    if not queue.is_file():
        return set()
    return set(ANCHOR.findall(queue.read_text(encoding="utf-8", errors="replace")))


# ── 대조 ──────────────────────────────────────────────────────────────
# 흐름: 수집한 앵커에서 알려진 ID 를 뺀다 -> 남은 것이 끊어진 연결
def find_unknown_anchors(anchors: dict[str, list[str]], known: set[str]) -> dict[str, list[str]]:
    """Find anchors pointing at ids the queue does not know.

    Args:
        anchors: Anchor id to locations, as returned by :func:`find_anchors`.
        known: Ids registered in the queue.

    Returns:
        Subset of ``anchors`` whose ids are not in ``known``.
    """
    return {anchor_id: places for anchor_id, places in anchors.items() if anchor_id not in known}


def main() -> int:
    """pre-push 훅 진입점.

    Returns:
        끊어진 앵커가 없으면 0, 있으면 1 (push 거부).
    """
    # fail-closed: 큐를 못 읽으면 "앵커가 깨끗하다"가 아니라 "검사하지 못했다"이다.
    # 이 훅은 pre-push 로컬 전용이라 docs-private 이 없을 이유가 없다 — 없으면 이상 상황.
    if not QUEUE_PATH.exists():
        print(f"\n[거부] 후속 큐가 없다 — {QUEUE_PATH}", file=sys.stderr)
        print("  검사 대상이 없는 것과 문제가 없는 것은 다르다(fail-closed).\n", file=sys.stderr)
        return 1

    known = read_known_ids(QUEUE_PATH)
    if not known:
        print(f"\n[거부] 후속 큐에서 QA 아이디를 한 건도 못 읽었다 — {QUEUE_PATH}", file=sys.stderr)
        print("  파서가 깨졌거나 큐 형식이 바뀌었다. 검사가 무력화된 상태다(fail-closed).\n", file=sys.stderr)
        return 1

    anchors = find_anchors(Path())
    unknown = find_unknown_anchors(anchors, known)
    if not unknown:
        # 침묵은 *"문제없음"* 과 *"안 돌았음"* 을 구분하지 못한다 — 이 저장소가 반복해서
        # 당한 실패 방식이라, 통과할 때도 **무엇을 셌는지** 한 줄로 남긴다.
        if len(anchors) < MIN_ANCHORS or len(known) < MIN_QUEUE:
            print(
                f"❌ 대상이 줄었다 — 코드 앵커 {len(anchors)}종(기대 ≥{MIN_ANCHORS}) · "
                f"큐 등재 {len(known)}건(기대 ≥{MIN_QUEUE}). glob·경로가 좁아졌거나 큐 파싱이 깨졌다.",
                file=sys.stderr,
            )
            return 1
        print(f"✅ QA 앵커 정합 — 코드 앵커 {len(anchors)}종 · 큐 등재 {len(known)}건 · 끊어진 연결 0.")
        return 0

    print("\n[거부] 코드가 큐에 없는 QA 앵커를 가리킨다\n", file=sys.stderr)
    for anchor_id, places in unknown.items():
        print(f"  {anchor_id}", file=sys.stderr)
        for place in places:
            print(f"    {place}", file=sys.stderr)
    print(
        f"\n  오타이거나, 큐에서 철회된 항목을 코드가 아직 가리키고 있다."
        f"\n  {QUEUE_PATH} 에 등재하거나 앵커를 고친다.\n",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
