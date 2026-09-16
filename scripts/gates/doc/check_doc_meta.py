"""문서 머리말 ``doc-meta`` 가 말한 것이 **사실인지** 센다.

규약 정본 = ``docs-private/FILING.md`` §9.

무엇을 검사하나
---------------
1. **블록 실재·필수 필드** — 규약 대상 문서에 ``doc-meta`` 와 ``kind``/``status`` 가 있는가
2. **``kind`` ↔ 위치·접미사 일치** — ``kind: record`` 인데 ``plan/`` 에 있으면 잡는다
3. **``status`` 가 그 ``kind`` 에 허용된 값인가** (FILING §8-1)
4. **``plan:`` 링크가 실재하는가** — 완료기록이 댄 PLAN 스냅샷이 실제로 있는가
5. ⭐ **``affects`` 가 거짓말하지 않는가** — 선언한 절이 **직전 스냅샷과 실제로 다른가**
6. **계승 링크가 양방향으로 맞는가** — ``supersedes`` ↔ ``superseded_by`` (FILING §8-4)
7. **``supersedes`` 를 아예 안 적었는가** — 계승 안 했으면 ``none`` 이라고 **명시**해야 한다
8. ⭐ **보류가 고아가 아닌가** — ``pending``/``suspended`` 를 ``ROADMAP.md`` 가 이름으로 가리키는가 (FILING §8-5)

왜 ⑤ 가 핵심인가
-----------------
``docs-private/`` 는 git 밖이라 **절 단위 변경 이력이 없다.** 가진 것은 문서 하나짜리
mtime 뿐이고, 그것으로는 *"§5 가 바뀌었나"* 를 **원리적으로 알 수 없다** —
실제로 ``ARCHITECTURE.md`` 는 오늘 갱신됐지만 RAG 절은 5개월 낡아 있었다.

> 🔑 **해법: 정본 §N ↔ 직전 스냅샷 §N 을 diff 한다.**
> 옛 판이 파일로 통째로 남아 있으므로 비교할 수 있다 — **축 폴더가 git 을 대신한다.**
> 사람이 *"고쳤다"* 고 적는 신뢰 단계가 없다.

이것이 은퇴한 ``check_canon_sync.py`` 를 대체한다. 그 게이트는
*"축 폴더가 정본보다 새로우면 낡은 것"* 으로 판정했는데, 새 규약에서 축 폴더는
**정의상 언제나 정본보다 과거**라 영원히 초록을 내는 통과 기계였다.

⚠️ ``pre-push`` **로컬 전용**이다. 대상이 없으면 **실패**한다(fail-closed).
"""

from dataclasses import dataclass
from functools import cache
from pathlib import Path
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# stdout/stderr 방어가 import 보다 먼저여야 한다 — cp949 크래시 방지(대장 D36).
from scripts.gates._root import PRIVATE  # noqa: E402

EXEMPT_DIRS = frozenset({"_legacy", "_unfiled", "aerich_backup_20260911", "__pycache__"})
#: 정본이 없는 축 — 직하에 있은 적이 없어 생애주기가 없다. ``doc-meta`` 를 요구하지 않는다.
CANONLESS = frozenset({"study", "portfolio"})

BLOCK = re.compile(r"<!--\s*doc-meta\s*(.*?)-->", re.DOTALL)
#: ``\s`` 는 줄바꿈을 포함하므로 값이 빈 필드가 **다음 줄을 값으로 삼킨다** —
#: 실제로 `supersedes:` 를 비웠더니 값이 ``affects:  FILING`` 으로 읽혔다. 줄 안으로 가둔다.
FIELD = re.compile(r"^[ 	]*([a-z_]+):[ 	]*(.+?)[ 	]*$", re.MULTILINE)
DATED = re.compile(r"^(\d{4}-\d{2}-\d{2})_([a-z0-9-]+)-([a-z]+)\.md$")

#: kind 별로 허용되는 status (FILING §8-1). 여기 없는 값은 오타이거나 규약 밖이다.
ALLOWED_STATUS: dict[str, frozenset[str]] = {
    "plan": frozenset({"draft", "active", "pending", "suspended", "done", "dropped", "superseded"}),
    "report": frozenset({"active", "done", "dropped"}),
    "record": frozenset({"active", "partial", "done"}),
    "architecture": frozenset({"active", "superseded"}),
    "deploy": frozenset({"active", "superseded"}),
    "filing": frozenset({"active", "superseded"}),
    "roadmap": frozenset({"active", "superseded"}),
    "mistake": frozenset({"active", "superseded"}),
    "queue": frozenset({"active", "superseded"}),
    "drift": frozenset({"active", "superseded"}),
}
TOP_STATUS = frozenset({"draft", "active"})

#: 하위 검사의 **바닥값**. 0건은 *"위반이 없다"* 가 아니라 *"대상이 사라져 아무것도 못 봤다"* 이다.
#: 실제로 ``check_utf8_guard`` 가 경로 이동 뒤 대상 11건 → 1건이 되고도 초록을 냈다(대장 **D31**).
#: 이 값을 낮춰야 할 상황이 오면 그건 **의식적인 결정**이어야 한다 — 조용히 0이 되는 것과 다르다.
MIN_AFFECTS = 1
MIN_SUCCESSION = 1
MIN_PLANS = 1

#: 계승하지 않았음을 **명시**하는 값. 빈칸을 허용하면 *"계승 안 했다"* 와 *"적는 걸 잊었다"* 가
#: 같은 모양이 되어, 게이트는 **선언이 사실인지**만 볼 뿐 **선언이 빠졌는지**를 못 본다.
NO_SUCCESSION = "none"

#: 보류를 **살려 두는** 문서. 여기서 이름이 불리지 않는 보류는 고아다(FILING §8-5).
ROADMAP = "ROADMAP.md"
RESUMABLE = frozenset({"pending", "suspended"})

#: ``affects: DEPLOY#5``(절) 또는 ``affects: DEPLOY``(문서 전체).
#: 절 단위가 기본이지만 **판을 통째로 새로 쓰는 경우**가 실재한다(규약 재작성 등) —
#: 그때 가짜 절 번호를 붙이게 하면 선언이 거짓이 된다. 절이 없으면 문서 전체를 대조한다.
AFFECT = re.compile(r"^([A-Z][A-Z_]*)(?:#(\S+))?$")


@dataclass(frozen=True)
class Finding:
    """한 건의 위반."""

    path: str
    reason: str


def parse_meta(path: Path) -> dict[str, str] | None:
    """``doc-meta`` 블록을 읽는다. 없으면 None."""
    found = BLOCK.search(path.read_text(encoding="utf-8", errors="replace")[:4000])
    return dict(FIELD.findall(found.group(1))) if found else None


def section_text(text: str, marker: str) -> str | None:
    """``§5`` / ``RAG`` 같은 표식이 가리키는 절의 본문을 잘라 낸다.

    절 번호(``5``)면 ``## 5.`` · ``## §5`` 형태를, 그 외에는 제목에 그 말이 든 절을 찾는다.
    찾지 못하면 None — 호출자가 *"선언한 절이 실재하지 않는다"* 로 판정한다.
    """
    lines = text.splitlines()
    start = None
    pattern = (
        re.compile(rf"^#{{2,3}}\s*§?\s*{re.escape(marker)}[.\s]")
        if marker.isdigit()
        else re.compile(rf"^#{{2,3}}\s.*{re.escape(marker)}", re.IGNORECASE)
    )
    for i, line in enumerate(lines):
        if pattern.match(line):
            start = i
            break
    if start is None:
        return None
    for j in range(start + 1, len(lines)):
        if re.match(r"^#{2,3}\s", lines[j]):
            return "\n".join(lines[start:j])
    return "\n".join(lines[start:])


# ── ⑤ affects 가 거짓말하는지 ──────────────────────────────────────────
# 흐름: affects 파싱 -> 정본 찾기 -> 절 잘라내기 -> 직전 스냅샷의 같은 절과 비교
# 스냅샷이 없으면(첫 판) 비교 대상이 없으므로 검사를 건너뛴다 — 거짓이 아니라 미지다.
def verify_affects(meta: dict[str, str], where: str, errors: list[Finding]) -> int:
    """``affects`` 선언을 검증하고 실제로 대조한 건수를 돌려준다."""
    raw = meta.get("affects", "")
    checked = 0
    for item in (x.strip() for x in raw.split(",") if x.strip()):
        matched = AFFECT.match(item)
        if not matched:
            errors.append(Finding(where, f"`affects` 항목이 `정본#절` 모양이 아니다 — `{item}` (FILING §9)"))
            continue
        canon_name, marker = matched.groups()
        canon = next((p for p in PRIVATE.glob("*.md") if p.stem.upper().startswith(canon_name)), None)
        if canon is None:
            errors.append(Finding(where, f"`affects` 가 없는 정본을 가리킨다 — `{canon_name}`"))
            continue
        body = canon.read_text(encoding="utf-8", errors="replace")
        current = body if marker is None else section_text(body, marker)
        if current is None:
            errors.append(Finding(where, f"`affects` 가 없는 절을 가리킨다 — `{canon.name}` 에 `{marker}` 없음"))
            continue

        axis = PRIVATE / canon.stem.lower()
        snaps = sorted(axis.glob("*.md")) if axis.is_dir() else []
        if not snaps:
            continue  # 첫 판이라 비교 대상이 없다. 미지이지 거짓이 아니다.
        snap_body = snaps[-1].read_text(encoding="utf-8", errors="replace")
        previous = snap_body if marker is None else section_text(snap_body, marker)
        checked += 1
        if previous is not None and previous.strip() == current.strip():
            errors.append(
                Finding(
                    where,
                    f"`affects: {item}` 라고 선언했는데 **그 절이 직전 판과 똑같다** "
                    f"({snaps[-1].name}) — 선언만 하고 안 고쳤다 (FILING §9-1)",
                )
            )
    return checked


# ── ⑥ 계승 링크가 양방향으로 맞는가 ──────────────────────────────────
# 흐름: supersedes 대조(앞→뒤) -> superseded_by 대조(뒤→앞) -> status 와의 정합
# 왜: 한쪽 방향만 두면 반대편은 사람이 고쳐야 하고, 사람은 잊는다. 잊힌 결과는
#     ①계승된 계획이 영원히 `pending`(살아있는 후보) 으로 남거나
#     ②옛 계획을 연 사람이 **후속을 찾지 못하는** 것이다 — 추적이 끊긴다(FILING §8-4).
#: 계승 시점에 새 PLAN 은 아직 직하라 파일명이 없다. 이 값이 그 구간의 유효한 좌표다.
OPEN_PLAN = "PLAN.md"


def plan_identity(path: Path, axis: str | None) -> str:
    """다른 문서가 이 PLAN 을 가리킬 때 쓰는 이름."""
    return OPEN_PLAN if axis is None else path.stem


def resolve_plan(ref: str) -> Path:
    """``supersedes``/``superseded_by`` 값이 가리키는 실제 파일."""
    if ref == OPEN_PLAN:
        return PRIVATE / OPEN_PLAN
    return PRIVATE / "plan" / (ref if ref.endswith(".md") else f"{ref}.md")


def links(meta: dict[str, str], field: str) -> list[str]:
    """쉼표로 나열된 링크 값. 괄호 주석은 값이 아니라 오류다(실제로 한 번 깨졌다)."""
    return [x.strip() for x in meta.get(field, "").split(",") if x.strip() and x.strip() != NO_SUCCESSION]


def verify_supersedes(meta: dict[str, str], path: Path, axis: str | None, where: str, errors: list[Finding]) -> None:
    """계승 링크를 **양쪽에서** 대조한다.

    ``kind: plan`` 에만 적용한다. **판 교체형 정본**(``filing/``·``deploy/`` …)은 후속이
    **폴더 이름으로 결정된다** — ``filing/`` 의 다음 판은 언제나 직하 ``FILING.md`` 이고,
    계보는 축 폴더를 날짜순으로 보면 된다(FILING §9-1). 도출되는 사실에 링크를 박으면
    판이 한 번 더 바뀔 때마다 **과거 스냅샷 전부를 고쳐야 한다.**
    역링크는 **후속이 결정론적으로 도출되지 않을 때만** 필요하다.

    Returns:
        대조한 링크 수. 호출자가 합산해 **0건이면 실패**로 본다(눈먼 검사 방지).
    """
    if meta.get("kind") != "plan":
        return 0
    me = plan_identity(path, axis)
    status = meta.get("status")
    checked = 0

    # 앞 → 뒤: 내가 계승한 것들이 실제로 닫혔고 나를 도로 가리키는가
    for item in links(meta, "supersedes"):
        checked += 1
        target = resolve_plan(item)
        if not target.exists():
            errors.append(Finding(where, f"`supersedes:` 가 없는 계획을 가리킨다 → `{item}`"))
            continue
        older = parse_meta(target) or {}
        if older.get("status") != "superseded":
            errors.append(
                Finding(
                    where,
                    f"`supersedes: {item}` 인데 그쪽 `status: {older.get('status')}` 다 — "
                    "계승당한 계획은 `superseded` 여야 한다. 안 바꾸면 미착수 재고로 남는다 (FILING §8-4)",
                )
            )
        back = links(older, "superseded_by")
        if me not in back:
            errors.append(
                Finding(
                    where,
                    f"`supersedes: {item}` 인데 그쪽 `superseded_by:` 가 나를 안 가리킨다 "
                    f"(`{back or '없음'}` ≠ `{me}`) — 역링크가 없으면 그 문서를 연 사람이 "
                    "후속을 찾지 못한다 (FILING §8-4)",
                )
            )

    # 뒤 → 앞: 내가 계승당했으면 누가 가져갔는지 적혀 있고, 그게 실재하며 나를 가리키는가
    back = links(meta, "superseded_by")
    if status == "superseded" and not back:
        errors.append(
            Finding(where, "`status: superseded` 인데 `superseded_by:` 가 없다 — 후속을 찾을 길이 없다 (FILING §8-4)")
        )
    if back and status != "superseded":
        errors.append(Finding(where, f"`superseded_by:` 가 있는데 `status: {status}` 다 — `superseded` 여야 한다"))
    for item in back:
        checked += 1
        target = resolve_plan(item)
        if not target.exists():
            hint = (
                " — 직하 `PLAN.md` 가 닫히면 이 값을 그 스냅샷 파일명으로 바꿔야 한다 (FILING §8-4 ④)"
                if item == OPEN_PLAN
                else ""
            )
            errors.append(Finding(where, f"`superseded_by:` 가 없는 계획을 가리킨다 → `{item}`{hint}"))
            continue
        newer = parse_meta(target) or {}
        if me not in links(newer, "supersedes"):
            errors.append(
                Finding(
                    where,
                    f"`superseded_by: {item}` 인데 그쪽 `supersedes:` 가 나를 안 가리킨다 — 링크가 한쪽만 있다",
                )
            )
    return checked


@cache
def roadmap_text() -> str:
    """보류를 살려 두는 문서. 한 번만 읽는다."""
    target = PRIVATE / ROADMAP
    return target.read_text(encoding="utf-8", errors="replace") if target.exists() else ""


# ── ⑧ 보류가 고아인가 ────────────────────────────────────────────────
# 흐름: pending/suspended 인가 -> ROADMAP 이 그 파일명을 부르는가
# 왜 나이로 판정하지 않나: *"오래된 보류"* 와 *"아직 유효한 보류"* 를 가르는 것은 **판단**이다.
#     날짜 상수를 두면 살아 있는 계획을 죽었다고 말한다. 보류는 **죽지 않는다** —
#     대신 **아무도 가리키지 않게 되는 것**을 막는다. 그건 판단 없이 셀 수 있다(FILING §8-5).
def verify_not_orphaned(meta: dict[str, str], path: Path, axis: str | None, where: str, errors: list[Finding]) -> int:
    """재개 가능한 보류가 ``ROADMAP.md`` 에서 불리는지 본다. 검사했으면 1."""
    if meta.get("kind") != "plan" or meta.get("status") not in RESUMABLE or axis is None:
        return 0
    if path.stem not in roadmap_text():
        errors.append(
            Finding(
                where,
                f"`status: {meta.get('status')}` 인데 `{ROADMAP}` 이 이 파일을 이름으로 부르지 않는다 — "
                "아무도 가리키지 않는 보류는 재개되지 않는다(고아). 로드맵 단계에 경로를 적거나, "
                "되살릴 생각이 없으면 `dropped` 로 닫는다 (FILING §8-5)",
            )
        )
    return 1


def inspect(path: Path, axis: str | None, errors: list[Finding]) -> tuple[int, int]:
    """문서 하나를 판정하고, **(affects 절 대조 수, 계승 링크 대조 수)** 를 돌려준다."""
    where = f"{axis}/{path.name}" if axis else path.name
    meta = parse_meta(path)
    if meta is None:
        errors.append(Finding(where, "`doc-meta` 블록이 없다 (FILING §9)"))
        return 0, 0

    kind, status = meta.get("kind"), meta.get("status")
    if not kind:
        errors.append(Finding(where, "`doc-meta` 에 `kind` 가 없다"))
    if not status:
        errors.append(Finding(where, "`doc-meta` 에 `status` 가 없다 — 없으면 생애주기를 판정할 수 없다"))

    if kind and status:
        allowed = ALLOWED_STATUS.get(kind)
        if allowed is None:
            errors.append(Finding(where, f"`kind: {kind}` 는 예약 목록에 없다 {sorted(ALLOWED_STATUS)}"))
        elif status not in allowed:
            errors.append(Finding(where, f"`status: {status}` 는 `kind: {kind}` 에 허용되지 않는다 {sorted(allowed)}"))

    if axis and kind and kind != axis:
        errors.append(Finding(where, f"`kind: {kind}` 가 폴더 `{axis}/` 와 다르다"))
    if axis is None and status and status not in TOP_STATUS:
        errors.append(Finding(where, f"직하인데 `status: {status}` 다 — 직하는 `draft`/`active` 뿐이다"))

    plan_ref = meta.get("plan")
    if plan_ref and not plan_ref.startswith("("):
        target = PRIVATE / "plan" / (plan_ref if plan_ref.endswith(".md") else f"{plan_ref}.md")
        if not target.exists():
            errors.append(Finding(where, f"`plan:` 이 없는 스냅샷을 가리킨다 → `plan/{target.name}`"))

    if kind == "plan" and "supersedes" not in meta:
        errors.append(
            Finding(
                where,
                f"`kind: plan` 인데 `supersedes:` 가 없다 — 계승하지 않았으면 `{NO_SUCCESSION}` 이라고 "
                "명시한다. 빈칸이면 '계승 안 함' 과 '적는 걸 잊음' 이 구분되지 않는다 (FILING §8-4)",
            )
        )
    verify_not_orphaned(meta, path, axis, where, errors)
    links_checked = verify_supersedes(meta, path, axis, where, errors)
    return verify_affects(meta, where, errors), links_checked


def main() -> int:
    """pre-push 훅 진입점.

    Returns:
        위반이 없으면 0, 있으면 1 (push 거부).
    """
    if not PRIVATE.is_dir():
        print(f"❌ {PRIVATE} 가 없다. 이 훅은 로컬 전용이라 없을 이유가 없다(fail-closed).")
        return 1

    errors: list[Finding] = []
    seen = affects_checked = links_checked = plans_seen = 0

    for path in sorted(PRIVATE.glob("*.md")):
        seen += 1
        got_affects, got_links = inspect(path, None, errors)
        affects_checked += got_affects
        links_checked += got_links
        plans_seen += "kind:     plan" in path.read_text(encoding="utf-8", errors="replace")[:600]

    for folder in sorted(p for p in PRIVATE.iterdir() if p.is_dir()):
        axis = folder.name
        if axis in EXEMPT_DIRS or axis in CANONLESS:
            continue
        for path in sorted(folder.glob("*.md")):
            if path.name == "README.md":
                continue
            seen += 1
            got_affects, got_links = inspect(path, axis, errors)
            affects_checked += got_affects
            links_checked += got_links
            plans_seen += axis == "plan"

    # fail-closed: 한 건도 못 모으면 "깨끗하다"가 아니라 "못 셌다"이다.
    if seen == 0:
        print(f"❌ `doc-meta` 검사 대상을 한 건도 수집하지 못했다 — {PRIVATE}")
        print("   경로 규약이 바뀌었거나 glob 이 어긋났다. 0건은 통과가 아니다(fail-closed).")
        return 1

    # ⭐ 하위 검사도 각각 fail-closed 다. 전체 대상이 많아도 **특정 검사만 눈이 멀 수 있다** —
    #    문서는 36건인데 계승 링크를 0건 봤다면 그 검사는 아무 일도 안 한 것이다.
    for label, count, floor, why in (
        ("affects 절 대조", affects_checked, MIN_AFFECTS, "affects 선언이 사라졌거나 비교할 스냅샷이 없다"),
        ("계승 링크 대조", links_checked, MIN_SUCCESSION, "supersedes/superseded_by 파싱이 깨졌거나 필드명이 바뀌었다"),
        ("PLAN 모집단", plans_seen, MIN_PLANS, "plan/ 경로가 바뀌었거나 kind 파싱이 깨졌다"),
    ):
        if count < floor:
            print(f"❌ {label} 대상이 {count}건이다 (기대 최소 {floor}건) — {why}.")
            print("   0건은 '위반이 없다' 가 아니라 '아무것도 못 봤다' 이다(fail-closed, 대장 D31).")
            return 1

    if errors:
        print(f"❌ `doc-meta` 위반 {len(errors)}건 (정본 = docs-private/FILING.md §9):")
        for item in errors[:25]:
            print(f"   - {item.path}: {item.reason}")
        if len(errors) > 25:
            print(f"   … 외 {len(errors) - 25}건")
        return 1

    print(
        f"✅ doc-meta 정합 — 문서 {seen}건 · affects 절 대조 {affects_checked}건 · "
        f"계승 링크 대조 {links_checked}건 · PLAN {plans_seen}건(고아 0) · 위반 0."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
