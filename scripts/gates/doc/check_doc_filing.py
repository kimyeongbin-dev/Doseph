"""문서가 규약에 맞는 이름으로 규약에 맞는 자리에 있는지 센다.

규약 정본 = ``docs-private/FILING.md``. 이 스크립트는 그 문서의 §3·§4·§5·§8 을 기계로 옮긴 것이고,
**규약과 어긋나면 규약이 옳다** — 고칠 곳은 여기다.

왜 이게 있나 — 실측 근거
------------------------
2026-09-16 기준 ``docs-private/`` 의 파일명이 **7가지 형태**로 갈려 있었다
(``날짜_주제-종류`` 27 · ``날짜_주제`` 36 · ``PLAN_*`` 18 · 대문자 12 · 소문자 43 · 한글 8 · 기타 17).
규칙이 없어서가 아니라 **기계가 센 적이 없어서** 갈렸다 —
``CLAUDE.md`` §4.2 의 레이어 규칙이 한 번도 세어지지 않은 채 위반 72건이었던 것과 같은 실패다.

세 축이 서로를 검증한다 (FILING §8-2)
-------------------------------------
::

    status: active   ⟺   파일명에 날짜 없음   ⟺   직하에 있다
    status: 그 외    ⟺   파일명에 날짜 있음   ⟺   축 폴더에 있다

세 신호가 **서로 독립**이라 하나만 어긋나도 잡힌다. 축 폴더에 있는데 ``active`` 면
*닫으면서 상태를 안 고친 것*이고, 날짜가 있는데 ``active`` 면 *살아있는 판을 내려보낸 것*이다.

무엇을 차단하고 무엇을 보고만 하나
----------------------------------
차단은 **정밀도가 높고 지금 고칠 수 있는 것**만이다. 정밀도 낮은 게이트는 사람이 끄고,
그러면 옆의 정확한 게이트까지 죽는다(``docs/QUALITY_GATES.md`` §2-1).

* 🔴 **차단** — 직하 화이트리스트 위반 · 축 폴더 파일명 위반 · 접미사≠폴더 · 날짜↔위치↔status 불일치
* 🟡 **보고** — ``study/``·``portfolio/`` 의 날짜 누락(45+2건, 개명은 정독·분류 구간 몫) ·
  ``_unfiled/`` 잔량

⚠️ ``docs-private/`` 는 git 밖이지만 이 훅은 ``pre-push`` **로컬 전용**이라 CI 에서 돌지 않는다.
→ 대상이 없으면 **실패**한다(fail-closed). *"검사 대상이 없다"* 와 *"문제가 없다"* 는 다른 사실이다.

✅ **음성 대조 표본** — 이것들은 **통과해야** 한다:
  - ``_unfiled/`` · ``_legacy/`` 안의 파일 (``_`` 접두 = 규약 밖 구역)
  - 직하 화이트리스트에 있는 작업 버퍼·상태 정본 (날짜 없는 것이 정상)
  - ``study/`` · ``portfolio/`` 의 정상 이름 (정본 없는 축)
"""

from dataclasses import dataclass
from pathlib import Path
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# stdout/stderr 방어가 import 보다 먼저여야 한다 — cp949 크래시 방지(대장 D36).
from scripts.gates._root import PRIVATE  # noqa: E402

#: 바닥값 — *0건*만이 아니라 **줄어든 것도 실패**다(`CLAUDE.md` §6-1, 대장 D31).
#: 실제로 `check_utf8_guard` 가 대상 11건 → 1건이 되고도 초록을 냈다.
#: 이 값은 **손으로 올린다** — 대상이 늘면 그때 올리는 것이 의식적인 결정이 된다.
MIN_AXIS_DOCS = 80

#: 규약 밖 구역 — 이름을 강제하지 않는다(FILING §11).
#: ``_legacy`` 는 죽은 문서라 이름이 곧 역사이고, ``_unfiled`` 는 아직 분류 전이다.
EXEMPT_DIRS = frozenset({"_legacy", "_unfiled"})

#: 스캔하지 않는 것 — 문서가 아니다.
SKIP_DIRS = frozenset({"aerich_backup_20260911", "__pycache__"})

#: 접미사 ↔ 축 폴더는 1:1 이다 (FILING §5). 새 축을 만들면 여기에 한 줄 추가한다.
SUFFIXES = frozenset({
    "plan",
    "report",
    "record",
    "architecture",
    "deploy",
    "filing",
    "roadmap",
    "mistake",
    "queue",
    "drift",
})
#: 정본이 없는 축 — 날짜는 "작성일" 이고 직하에 있은 적이 없다.
CANONLESS = frozenset({"study", "portfolio"})
ALL_SUFFIXES = SUFFIXES | CANONLESS

#: 직하에 있어도 되는 것 — **이 목록이 전부다** (FILING §5).
#: 🔴 상태 정본은 **없으면 결함**이고, 작업 버퍼는 없어도 정상이다.
#: ⚠️ 이관 중 이름: DEPLOYMENT→DEPLOY · AGENT_실수-오류-기록→MISTAKE 개명은 정독·분류 구간 몫.
WORK_BUFFERS = frozenset({"PLAN.md", "REPORT.md", "RECORD.md"})
STATE_CANONS = frozenset({
    "FILING.md",
    "ROADMAP.md",
    "DEPLOYMENT.md",
    "DOC_TRUTH_DRIFT.md",
    "TEST_FOLLOWUP_QUEUE.md",
    "AGENT_실수-오류-기록.md",
    "READING_LOG.md",
    "DTO_DESIGN_RULES.md",
})
ALLOWED_TOP = WORK_BUFFERS | STATE_CANONS

DATED = re.compile(r"^(\d{4}-\d{2}-\d{2})_([a-z0-9]+(?:-[a-z0-9]+)*)-([a-z]+)\.md$")
STATUS = re.compile(r"^status:\s*(\S+)\s*$", re.MULTILINE)
META = re.compile(r"<!--\s*doc-meta\s*(.*?)-->", re.DOTALL)

#: 직하 정본이 가질 수 있는 status (FILING §8-1).
TOP_STATUS = frozenset({"draft", "active"})


@dataclass(frozen=True)
class Finding:
    """한 건의 규약 위반."""

    path: str
    reason: str


def read_status(path: Path) -> str | None:
    """``doc-meta`` 블록에서 status 를 읽는다. 없으면 None."""
    found = META.search(path.read_text(encoding="utf-8", errors="replace")[:2000])
    if not found:
        return None
    raw = STATUS.search(found.group(1))
    return raw.group(1) if raw else None


# ── 직하 판정 ──────────────────────────────────────────────────────────
# 흐름: 직하 .md 순회 -> 화이트리스트 대조 -> 날짜 유무 -> status 3중 검증
def inspect_top(errors: list[Finding]) -> None:
    """``docs-private/`` 직하의 파일들을 판정한다."""
    for path in sorted(PRIVATE.glob("*.md")):
        name = path.name
        if name not in ALLOWED_TOP:
            errors.append(Finding(name, "직하 화이트리스트 밖이다 — 축 폴더나 `_unfiled/` 로 간다 (FILING §5)"))
            continue
        if DATED.match(name):
            errors.append(Finding(name, "직하 정본에는 날짜가 없다 — 날짜가 붙었으면 축 폴더로 간 것이다 (FILING §4)"))
            continue
        status = read_status(path)
        if status is not None and status not in TOP_STATUS:
            errors.append(
                Finding(name, f"직하인데 status 가 `{status}` 다 — 직하는 `draft`/`active` 뿐이다 (FILING §8-2)")
            )

    missing = sorted(STATE_CANONS - {p.name for p in PRIVATE.glob("*.md")})
    errors.extend(
        Finding(name, "🔴 **상태 정본이 없다** — 작업 버퍼와 달리 없는 것 자체가 결함이다 (FILING §6)")
        for name in missing
    )


# ── 축 폴더 판정 ───────────────────────────────────────────────────────
# 흐름: 축 폴더 순회 -> 파일명 모양 -> 접미사==폴더명 -> 예약어 -> status 대조
def inspect_axes(errors: list[Finding], warnings: list[Finding]) -> int:
    """축 폴더의 파일들을 판정하고, 검사한 파일 수를 돌려준다."""
    seen = 0
    for folder in sorted(p for p in PRIVATE.iterdir() if p.is_dir()):
        axis = folder.name
        if axis in EXEMPT_DIRS or axis in SKIP_DIRS:
            continue
        if axis not in ALL_SUFFIXES:
            errors.append(Finding(f"{axis}/", f"예약된 축 폴더가 아니다 — 접미사 목록에 없다 {sorted(ALL_SUFFIXES)}"))
            continue

        for path in sorted(folder.glob("*.md")):
            seen += 1
            name = path.name
            if name == "README.md":
                continue
            found = DATED.match(name)
            if not found:
                bucket = warnings if axis in CANONLESS else errors
                bucket.append(
                    Finding(
                        f"{axis}/{name}",
                        "이름이 `YYYY-MM-DD_<슬러그>-<접미사>.md` 가 아니다 (FILING §3)"
                        + (" — 정독·분류 구간에서 일괄 개명" if axis in CANONLESS else ""),
                    )
                )
                continue

            _, slug, suffix = found.groups()
            if suffix != axis:
                errors.append(Finding(f"{axis}/{name}", f"접미사 `-{suffix}` 가 폴더 `{axis}/` 와 다르다 (FILING §3)"))
            if slug.rsplit("-", 1)[-1] in ALL_SUFFIXES:
                errors.append(
                    Finding(f"{axis}/{name}", f"예약어 `{slug.rsplit('-', 1)[-1]}` 가 슬러그 끝에 왔다 (FILING §3)")
                )
            status = read_status(path)
            if status in TOP_STATUS:
                reason = f"축 폴더인데 status 가 `{status}` 다 — 닫으면서 상태를 안 고쳤다 (FILING §8-2)"
                errors.append(Finding(f"{axis}/{name}", reason))
    return seen


def main() -> int:
    """pre-push 훅 진입점.

    Returns:
        규약 위반이 없으면 0, 있으면 1 (push 거부).
    """
    if not PRIVATE.is_dir():
        print(f"❌ {PRIVATE} 가 없다. 이 훅은 로컬 전용이라 없을 이유가 없다(fail-closed).")
        return 1

    errors: list[Finding] = []
    warnings: list[Finding] = []
    inspect_top(errors)
    seen = inspect_axes(errors, warnings)

    # fail-closed: 대상을 한 건도 못 모으면 "깨끗하다"가 아니라 "못 셌다"이다.
    if seen == 0:
        print(f"❌ 축 폴더에서 문서를 한 건도 수집하지 못했다 — {PRIVATE}")
        print("   경로 규약이 바뀌었거나 glob 이 어긋났다. 검사 대상 0건은 통과가 아니다(fail-closed).")
        return 1

    unfiled = PRIVATE / "_unfiled"
    pending = len(list(unfiled.glob("*.md"))) if unfiled.is_dir() else 0
    if pending:
        warnings.append(Finding("_unfiled/", f"미분류 **{pending}건** 남음 — 정독·분류 구간에서 처리한다"))

    if warnings:
        print(f"🟡 배치 보고 {len(warnings)}건 (차단 아님):")
        for item in warnings[:8]:
            print(f"   - {item.path}: {item.reason}")
        if len(warnings) > 8:
            print(f"   … 외 {len(warnings) - 8}건")
        print()

    if errors:
        print(f"❌ 문서 배치 규약 위반 {len(errors)}건 (정본 = docs-private/FILING.md):")
        for item in errors[:25]:
            print(f"   - {item.path}: {item.reason}")
        if len(errors) > 25:
            print(f"   … 외 {len(errors) - 25}건")
        return 1

    if seen < MIN_AXIS_DOCS:
        print(f"❌ 축 폴더 대상이 {seen}건이다 (기대 ≥{MIN_AXIS_DOCS}) — 경로 규약이 바뀌었거나 glob 이 좁아졌다.")
        print("   줄어든 것도 실패다(fail-closed, 대장 D31).")
        return 1
    print(f"✅ 문서 배치 — 직하 {len(ALLOWED_TOP)}종 규약 준수 · 축 폴더 {seen}건 이름 정합.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
