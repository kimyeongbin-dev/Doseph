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

    draft·in-progress·current  ⟺  파일명에 날짜 없음  ⟺  직하에 있다
    status: 그 외    ⟺   파일명에 날짜 있음   ⟺   축 폴더에 있다

세 신호가 **서로 독립**이라 하나만 어긋나도 잡힌다. 축 폴더에 있는데 ``in-progress``·``current`` 면
*닫으면서 상태를 안 고친 것*이고, 날짜가 있는데 그 값이면 *살아있는 판을 내려보낸 것*이다.

무엇을 차단하고 무엇을 보고만 하나
----------------------------------
차단은 **정밀도가 높고 지금 고칠 수 있는 것**만이다. 정밀도 낮은 게이트는 사람이 끄고,
그러면 옆의 정확한 게이트까지 죽는다(``docs/QUALITY_GATES.md`` §2-1).

* 🔴 **차단** — 직하 화이트리스트 위반 · 축 폴더 파일명 위반 · 접미사≠폴더 · 날짜↔위치↔status 불일치
* 🟡 **보고** — ``study/``·``portfolio/`` 의 날짜 누락(개명은 정독·분류 구간 몫).
  ⚠️ ``누적: true`` 를 선언한 누적형은 **날짜 없음이 정상**이라 제외한다(FILING §3-4) ·
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
SKIP_DIRS = frozenset({"__pycache__"})

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

#: 누적형(append-only) 선언 — **항목마다 자기 날짜를 갖는 문서**는 파일 전체의 "작성일" 이 없다
#: (FILING §3-4). 날짜를 붙이면 **붙이는 순간부터 거짓**이 되므로 날짜 없는 이름을 허용한다.
#: 🔴 파일명 화이트리스트로 하지 않는 이유 = §3-1 *"파일명으로 종류를 판정하지 않는다"*.
#: 문서가 `doc-meta` 로 **스스로 선언**해야 하고, 그 선언이 없으면 그냥 개명 누락이다.
APPEND_ONLY = re.compile(r"^\s*누적:\s*true\s*$", re.MULTILINE)

#: 🔴 누적형은 **자라면 안 되는 예외**다. 2026-09-21 전수 스윕(study+portfolio 62건)에서
#: 정확히 1건이었다. 0 이 되면 *"예외가 없어졌다"* 가 아니라 **선언 파싱이 깨졌다** 로 읽는다.
#: ⚠️ 늘어나면 예외가 아니라 **종류**다 — 그때는 축 폴더를 따로 내주는 게 맞다(손으로 올린다).
MIN_APPEND_ONLY = 1
ALL_SUFFIXES = SUFFIXES | CANONLESS

#: 직하에 있어도 되는 것 — **이 목록이 전부다** (FILING §5).
#: 🔴 상태 정본은 **없으면 결함**이고, 작업 버퍼는 없어도 정상이다.
#: ⚠️ 이관 중 이름: DEPLOYMENT→DEPLOY · AGENT_실수-오류-기록→MISTAKE 개명은 정독·분류 구간 몫.
WORK_BUFFERS = frozenset({"PLAN.md", "REPORT.md", "RECORD.md"})
# 🔴 2026-09-21: ``READING_LOG.md`` 를 여기서 뺐다. 상태 정본이 아니라 **작업 버퍼**였다 —
# 자기 ``doc-meta`` 가 ``kind: record`` 에 *"끝나면 record/ 로"* 라고 적고 있었는데
# 여기 있는 바람에 게이트가 *"없으면 결함"* 이라고 말했다. 트랙 B-9 가 끝나 닫히자 그 거짓이 드러났다.
# 🔑 **성격은 파일이 선언하고(`kind`/`status`), 목록은 그것을 따라간다** — 반대로 하면
#    목록이 문서더러 *"너는 죽으면 안 된다"* 고 말하게 된다.
STATE_CANONS = frozenset({
    "FILING.md",
    "ROADMAP.md",
    "DEPLOYMENT.md",
    "DOC_TRUTH_DRIFT.md",
    "FOLLOWUP_QUEUE.md",
    "AGENT_실수-오류-기록.md",
    "DTO_DESIGN_RULES.md",
    "LOCAL_RESIDUE.md",
    "ARCHITECTURE.md",  # 2026-09-21 루트에서 이관(B-9 S7)
    "FOLLOWUP_INDEX.md",  # 🤖 생성물 — build_followup_index.py 가 만든다
})
ALLOWED_TOP = WORK_BUFFERS | STATE_CANONS

DATED = re.compile(r"^(\d{4}-\d{2}-\d{2})_([a-z0-9]+(?:-[a-z0-9]+)*)-([a-z]+)\.md$")
STATUS = re.compile(r"^status:\s*(\S+)\s*$", re.MULTILINE)
META = re.compile(r"<!--\s*doc-meta\s*(.*?)-->", re.DOTALL)

#: 직하 정본이 가질 수 있는 status (FILING §8-1).
#: 직하에 있을 수 있는 status — 작업버퍼 2종 + 상태정본 1종.
#: ⚠️ `active` 는 2026-09-20 은퇴(한 단어를 두 뜻으로 썼다) → `in-progress`(작업버퍼) · `current`(상태정본).
#: 🔴 `check_doc_meta.py` 의 같은 이름 상수와 **반드시 같아야 한다** — 갈라지면 두 게이트가 서로 다른 규약을 강제한다.
TOP_STATUS = frozenset({"draft", "in-progress", "current"})


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
                Finding(name, f"직하인데 status 가 `{status}` 다 — 직하는 {sorted(TOP_STATUS)} 뿐이다 (FILING §8-2)")
            )

    missing = sorted(STATE_CANONS - {p.name for p in PRIVATE.glob("*.md")})
    errors.extend(
        Finding(name, "🔴 **상태 정본이 없다** — 작업 버퍼와 달리 없는 것 자체가 결함이다 (FILING §6)")
        for name in missing
    )


# ── 직하의 **문서가 아닌 것** ───────────────────────────────────────────
# 흐름: 직하 파일 순회 -> .md 가 아닌 것 수집 -> 🟡 보고
# 🔴 왜 있나: 위 `inspect_top` 은 `glob("*.md")` 라 **.md 만 본다.** 그래서 직하의
#    `.dbml`·`.tsv`·`.csv`·`.sh`·`.jpg` 는 *"화이트리스트 밖"* 판정을 **구조적으로 못 받았다.**
#    게이트는 매번 "직하 13종 규약 준수" 라고 초록을 냈는데, 그 13종은 **.md 만 센 수**였다.
#    2026-09-21 정독에서 직하에 비-md 7건이 있는 것이 드러났다.
# 🟡 **차단이 아니라 보고다**: 이것들은 대개 문서가 아니라 **데이터·임시 스크립트**라
#    문서 분류 체계(화이트리스트)에 등록할 대상이 아니다. 강제로 등록시키면 규약이
#    쓰레기로 채워진다. 기계가 할 일은 **보이게 만드는 것**까지다 — 옮길지 지울지는 사람이 정한다.
def inspect_top_nondoc() -> list[Finding]:
    """직하의 `.md` 아닌 파일 (폴더 제외). 보고용."""
    return [
        Finding(
            p.name,
            "직하에 있는데 문서가 아니다 — 데이터·임시 스크립트면 직하가 아니라 "
            "축 폴더/작업 폴더로 옮기거나 지운다 (문서면 `.md` 로 규약을 따른다)",
        )
        for p in sorted(PRIVATE.iterdir())
        if p.is_file() and p.suffix != ".md"
    ]


# ── 축 폴더 판정 ───────────────────────────────────────────────────────
# 흐름: 축 폴더 순회 -> 파일명 모양 -> 접미사==폴더명 -> 예약어 -> status 대조
def inspect_axes(errors: list[Finding], warnings: list[Finding]) -> int:
    """축 폴더의 파일들을 판정하고, 검사한 파일 수를 돌려준다."""
    seen = 0
    append_only: list[str] = []
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
                # 누적형은 날짜가 없는 것이 **정상**이다. 단, 스스로 선언해야 한다.
                if axis in CANONLESS and APPEND_ONLY.search(path.read_text(encoding="utf-8", errors="replace")):
                    append_only.append(f"{axis}/{name}")
                    continue
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
    return seen, append_only


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
    seen, append_only = inspect_axes(errors, warnings)

    # fail-closed: 대상을 한 건도 못 모으면 "깨끗하다"가 아니라 "못 셌다"이다.
    if seen == 0:
        print(f"❌ 축 폴더에서 문서를 한 건도 수집하지 못했다 — {PRIVATE}")
        print("   경로 규약이 바뀌었거나 glob 이 어긋났다. 검사 대상 0건은 통과가 아니다(fail-closed).")
        return 1

    # 🔴 `README.md` 는 그 폴더의 **분류 절차서**이지 분류 대상이 아니다.
    #    세면 잔량이 늘 +1 이라, 다 끝나도 계측기가 0 을 못 찍는다.
    #    PLAN(B-9) §2 의 완료 기준 명령도 `grep -v README` 로 거른다 — 둘이 같은 것을 세야 한다.
    nondoc = inspect_top_nondoc()
    warnings.extend(nondoc)

    unfiled = PRIVATE / "_unfiled"
    pending = len([p for p in unfiled.glob("*.md") if p.name != "README.md"]) if unfiled.is_dir() else 0
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
    if len(append_only) < MIN_APPEND_ONLY:
        print(f"❌ 누적형 선언을 {len(append_only)}건밖에 못 셌다 (기대 최소 {MIN_APPEND_ONLY}건).")
        print("   `누적: true` 파싱이 깨졌거나 그 문서가 사라졌다 — 0건은 '예외가 없다' 가 아니라")
        print("   '아무것도 못 봤다' 이고, 그러면 날짜 없는 이름이 조용히 통과한다(fail-closed).")
        return 1
    print(
        f"✅ 문서 배치 — 직하 {len(ALLOWED_TOP)}종(.md) 규약 준수 · "
        f"직하 비문서 {len(nondoc)}건 · 축 폴더 {seen}건 이름 정합 · "
        f"누적형 {len(append_only)}건({', '.join(append_only)})."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
