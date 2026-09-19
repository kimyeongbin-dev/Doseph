"""완료기록이 가리킨 PLAN 스냅샷이 실제로 있는지 센다.

`pre-commit` 의 ``pre-push`` 스테이지에서 실행된다.

왜 훅으로 세나
--------------
*"완료기록 + PLAN 스냅샷은 한 동작"* 이라는 규칙이 있었는데도
**한 세션에서 3번 연속** 완료기록만 쓰고 스냅샷을 빠뜨렸다(대장 **D27**, 실제 누적 6회).
체크리스트 1번을 하면 2번을 한 것 같은 감각이 생기기 때문이다.

> **"기록했다"는 감각을 점검 근거로 삼지 않는다. 센다.**

⚠️ 두 규약을 **동시에** 인정하는 과도기다 (2026-09-20 ~ 트랙 B-9 종료)
--------------------------------------------------------------------
- **새 규약**: 완료기록 ``doc-meta`` 의 ``plan:`` 필드 → ``plan/<슬러그>.md`` (FILING §9)
- **옛 규약**: 본문이 ``PLAN_XXX.md`` 를 언급 → ``_legacy/<날짜>_PLAN_XXX.snapshot.md``

B-9(문서 정독·분류)가 PLAN 을 한 건씩 새 이름으로 옮기는 중이라 **둘이 공존한다.**
옛 쪽 쌍이 **0 이 되면 그 분기를 제거**한다 — 성공 줄이 그 숫자를 인쇄하는 이유다.

🔴 **이 게이트는 한 번 조용히 죽을 뻔했다.** 옛 정규식만 보고 있었기 때문에,
정독 첫 건을 새 이름으로 옮기자 **18쌍 → 17쌍**이 되고도 *"빠진 스냅샷 0"* 으로 초록을 냈다.
B-9 를 끝까지 진행했으면 **0쌍이 되고도 초록**이었을 것이다(`check_utf8_guard` 11→1 과 같은 실패).
그래서 **바닥값**을 둔다 — *0건은 "누락이 없다" 가 아니라 "아무것도 못 봤다" 이다.*

`docs-private/` 는 git 미추적이지만 이 훅은 `pre-push` **로컬 전용**이라 CI 에서 돌지 않는다.
→ 대상이 없으면 **실패**한다(fail-closed, `docs/QUALITY_GATES.md` §2-5-1 · §2-9).
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
PLAN_DIR = PRIVATE_DIR / "plan"

RECORD_GLOB = "[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]_*-record.md"
#: 옛 규약 — 본문이 대문자 PLAN 파일명을 언급한다.
LEGACY_REFERENCE = re.compile(r"(PLAN_[A-Z0-9_]+)\.md")
#: 새 규약 — ``doc-meta`` 의 ``plan:`` 필드. 값이 빈 필드가 다음 줄을 삼키지 않게 줄 안으로 가둔다.
PLAN_FIELD = re.compile(r"^[ \t]*plan:[ \t]*(\S+)[ \t]*$", re.MULTILINE)

#: 바닥값 = **지금 세어지는 합계**. 이 아래로 떨어지면 *"누락이 없다"* 가 아니라 *"대상이 사라졌다"* 이다.
#:
#: 🔑 **왜 합계는 줄지 않는가**: B-9 는 PLAN 의 *이름만* 바꾼다. 옛 규약 1쌍이 빠지면
#: 같은 문서가 새 규약 1쌍으로 들어오므로 **합계는 단조 비감소**다. 줄었다면 전환이 아니라
#: **참조를 잃은 것**이다. 옛 쪽만 보는 바닥값(`>= 1`)으로는 옛 17쌍이 통째로 죽어도
#: 새 2쌍이 남아 통과한다 — 실제로 결핍 주입에서 그렇게 뚫렸다.
#:
#: ⚠️ 이 값은 **손으로 올린다**. `unlinked` 기록이 `plan:` 을 얻어 합계가 늘면 그때 올린다.
MIN_PAIRS = 19


# ── 완료기록 ↔ PLAN 스냅샷 대조 ───────────────────────────────────────
# 흐름: 완료기록 수집 -> 새 규약(plan: 필드)·옛 규약(본문 PLAN_XXX) 양쪽에서 짝 추출
#       -> 각 짝의 스냅샷 존재 확인 -> 없으면 보고하고 exit 1
def collect_records() -> list:
    """`_legacy/` 밖의 완료기록 전부. 축 폴더로 흩어져 있어도 `rglob` 으로 모은다."""
    return sorted(r for r in PRIVATE_DIR.rglob(RECORD_GLOB) if LEGACY_DIR not in r.parents)


def audit() -> tuple[list[tuple[str, str]], list[str], int, int]:
    """(빠진 짝, PLAN 을 안 가리키는 기록, 새 규약 쌍 수, 옛 규약 쌍 수)."""
    missing: list[tuple[str, str]] = []
    unlinked: list[str] = []
    new_pairs = old_pairs = 0

    for record in collect_records():
        body = record.read_text(encoding="utf-8", errors="replace")

        for slug in sorted(set(PLAN_FIELD.findall(body))):
            new_pairs += 1
            target = PLAN_DIR / (slug if slug.endswith(".md") else f"{slug}.md")
            if not target.exists():
                missing.append((record.name, f"plan/{target.name}"))

        date = record.name[:10]
        for plan in sorted(set(LEGACY_REFERENCE.findall(body))):
            old_pairs += 1
            snapshot = LEGACY_DIR / f"{date}_{plan}.snapshot.md"
            if not snapshot.exists():
                missing.append((record.name, f"_legacy/{snapshot.name}"))

        if not PLAN_FIELD.search(body) and not LEGACY_REFERENCE.search(body):
            unlinked.append(record.name)

    return missing, unlinked, new_pairs, old_pairs


def main() -> int:
    """pre-push 훅 진입점.

    Returns:
        빠진 스냅샷이 없으면 0, 있으면 1 (push 거부).
    """
    if not PRIVATE_DIR.is_dir():
        print(
            f"\n[거부] {PRIVATE_DIR} 가 없다. 이 훅은 로컬 전용이라 없을 이유가 없다(fail-closed).\n", file=sys.stderr
        )
        return 1

    if not collect_records():
        print(f"\n[거부] 완료기록을 한 건도 못 찾았다 — {PRIVATE_DIR}/{RECORD_GLOB}", file=sys.stderr)
        print("  경로 규약이 바뀌었거나 glob 이 어긋났다. 검사가 무력화된 상태다(fail-closed).\n", file=sys.stderr)
        return 1

    missing, unlinked, new_pairs, old_pairs = audit()

    if missing:
        print("\n[거부] 완료기록은 있는데 PLAN 스냅샷이 없다 (대장 D27)\n", file=sys.stderr)
        for record, target in missing:
            print(f"  {record}\n    → 없음: docs-private/{target}", file=sys.stderr)
        print(
            "\n  완료기록과 PLAN 스냅샷은 한 동작이다."
            "\n  새 규약: 기록의 `plan:` 필드가 가리키는 `plan/<슬러그>.md` 를 만든다(`mv`, 재작성 금지).\n",
            file=sys.stderr,
        )
        return 1

    # 🔴 대상이 사라지면 "누락 0" 은 의미가 없다. 옛 규약이 B-9 로 소멸하는 중이라
    #    합계로 세지 않으면 이 게이트는 조용히 0쌍이 된다.
    if new_pairs + old_pairs < MIN_PAIRS:
        print(f"\n[거부] PLAN 참조를 {new_pairs + old_pairs}쌍밖에 못 셌다 (기대 최소 {MIN_PAIRS}쌍).", file=sys.stderr)
        print(
            "  `plan:` 필드 파싱이 깨졌거나 경로 규약이 또 바뀌었다 — B-9 전환은 합계를 줄이지 않는다.", file=sys.stderr
        )
        print("  0쌍은 '누락이 없다' 가 아니라 '아무것도 못 봤다' 이다(fail-closed).\n", file=sys.stderr)
        return 1

    # 침묵은 *"문제없음"* 과 *"안 돌았음"* 을 구분하지 못한다. 통과할 때도 **센 것**을 남긴다.
    print(
        f"✅ PLAN 스냅샷 정합 — 완료기록 {len(collect_records())}건 · "
        f"새 규약 {new_pairs}쌍 · 옛 규약 {old_pairs}쌍 · 빠진 스냅샷 0."
    )
    if old_pairs == 0:
        print("   ⭐ 옛 규약 0쌍 — B-9 전환이 끝났다. LEGACY_REFERENCE 분기를 제거할 때다.")
    if unlinked:
        # 🟡 보고. B-9 가 끝나면 차단으로 승격한다 — 지금 막으면 옮기는 중인 20건이 전부 걸린다.
        print(f"   🟡 PLAN 을 가리키지 않는 완료기록 {len(unlinked)}건 (B-9 종료 후 차단으로 승격):")
        for name in unlinked[:8]:
            print(f"      - {name}")
        if len(unlinked) > 8:
            print(f"      … 외 {len(unlinked) - 8}건")
    return 0


if __name__ == "__main__":
    sys.exit(main())
