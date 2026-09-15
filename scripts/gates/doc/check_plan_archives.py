"""완료기록이 참조하는 PLAN 의 `_legacy` 스냅샷이 실제로 있는지 센다.

`pre-commit` 의 ``pre-push`` 스테이지에서 실행된다.

왜 훅으로 세나
--------------
*"완료기록 + PLAN 아카이브는 한 동작"* 이라는 규칙이 있었는데도
**한 세션에서 3번 연속** 완료기록만 쓰고 스냅샷을 빠뜨렸다(대장 D27).
체크리스트 1번을 하면 2번을 한 것 같은 감각이 생기기 때문이다.

> **"기록했다"는 감각을 점검 근거로 삼지 않는다. 센다.**

오탐을 피하는 방법
------------------
모든 완료기록에 PLAN 이 있는 건 아니다(부채 원장에서 바로 처리한 QA-02/03 등).
그래서 **완료기록 본문이 실제로 이름을 댄 PLAN** 만 대조한다 —
기록이 ``PLAN_XXX.md`` 를 언급하면 같은 날짜의 스냅샷을 요구한다.

`docs-private/` 는 git 미추적이지만 이 훅은 `pre-push` **로컬 전용**이라 CI 에서 돌지 않는다.
→ 대상이 없으면 **실패**한다(fail-closed). *"검사 대상이 없다"* 와 *"문제가 없다"* 는 다른 사실이고,
구분하지 못하면 게이트가 **자기가 죽었다는 것을 초록으로 보고**한다(`docs/QUALITY_GATES.md` §2-5-1)
(로컬 개발자용 게이트지, 파이프라인 게이트가 아니다).
"""

import re
import sys

# Windows 콘솔 기본 코드페이지(cp949)에서 한글 출력이 깨지거나 죽지 않도록 고정한다.
# 🔴 stdout 과 stderr 는 **서로를 보호하지 않는다** — 한쪽만 고정하면 다른 쪽이 크래시한다(대장 D36).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# stdout/stderr 방어가 import 보다 먼저여야 한다 — cp949 크래시 방지(대장 D36).
from scripts.gates._root import PRIVATE as PRIVATE_DIR

LEGACY_DIR = PRIVATE_DIR / "_legacy"

RECORD_GLOB = "[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]_*-record.md"
PLAN_REFERENCE = re.compile(r"(PLAN_[A-Z0-9_]+)\.md")


# ── 완료기록 ↔ PLAN 스냅샷 대조 ───────────────────────────────────────
# 흐름: 완료기록 수집 -> 본문에서 PLAN 이름 추출 -> 같은 날짜 스냅샷 존재 확인
#       -> 없으면 목록으로 보고하고 exit 1
def find_missing_archives() -> list[tuple[str, str]]:
    """스냅샷이 없는 (완료기록, PLAN) 짝을 찾는다.

    Returns:
        (완료기록 파일명, 빠진 스냅샷 파일명) 목록.
    """
    missing: list[tuple[str, str]] = []
    for record in sorted(r for r in PRIVATE_DIR.rglob(RECORD_GLOB) if LEGACY_DIR not in r.parents):
        date = record.name[:10]
        body = record.read_text(encoding="utf-8", errors="replace")
        for plan in sorted(set(PLAN_REFERENCE.findall(body))):
            snapshot = LEGACY_DIR / f"{date}_{plan}.snapshot.md"
            if not snapshot.exists():
                missing.append((record.name, snapshot.name))
    return missing


def main() -> int:
    """pre-push 훅 진입점.

    Returns:
        빠진 스냅샷이 없으면 0, 있으면 1 (push 거부).
    """
    # fail-closed: 디렉터리가 없거나 완료기록을 0건 수집하면 "누락이 없다"가 아니라
    # "검사하지 못했다"이다. 실제로 완료기록을 하위 폴더로 옮기는 순간 이 glob 이
    # 0건이 되어 조용히 통과했을 것이다(FILING.md §5).
    if not PRIVATE_DIR.is_dir():
        print(
            f"\n[거부] {PRIVATE_DIR} 가 없다. 이 훅은 로컬 전용이라 없을 이유가 없다(fail-closed).\n", file=sys.stderr
        )
        return 1

    # rglob: 완료기록이 축별 폴더(`deploy/`·`record/` 등)로 흩어져도 전부 센다.
    # `_legacy/` 는 제외 — 아카이브된 기록은 이미 닫힌 것이라 스냅샷을 다시 요구하지 않는다.
    records = [r for r in PRIVATE_DIR.rglob(RECORD_GLOB) if LEGACY_DIR not in r.parents]
    if not records:
        print(f"\n[거부] 완료기록을 한 건도 못 찾았다 — {PRIVATE_DIR}/{RECORD_GLOB}", file=sys.stderr)
        print("  경로 규약이 바뀌었거나 glob 이 어긋났다. 검사가 무력화된 상태다(fail-closed).\n", file=sys.stderr)
        return 1

    missing = find_missing_archives()
    if not missing:
        # 침묵은 *"문제없음"* 과 *"안 돌았음"* 을 구분하지 못한다. 통과할 때도 **센 것**을 남긴다.
        pairs = sum(len(set(PLAN_REFERENCE.findall(r.read_text(encoding="utf-8", errors="replace")))) for r in records)
        print(f"✅ PLAN 스냅샷 정합 — 완료기록 {len(records)}건 · PLAN 참조 {pairs}쌍 · 빠진 스냅샷 0.")
        return 0

    print("\n[거부] 완료기록은 있는데 PLAN 스냅샷이 없다 (대장 D27)\n", file=sys.stderr)
    for record, snapshot in missing:
        print(f"  {record}\n    → 없음: docs-private/_legacy/{snapshot}", file=sys.stderr)
    print(
        "\n  완료기록과 PLAN 아카이브는 한 동작이다."
        "\n  cp docs-private/<PLAN>.md docs-private/_legacy/<날짜>_<PLAN>.snapshot.md\n",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
