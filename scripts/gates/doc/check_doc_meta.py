"""문서 머리말 ``doc-meta`` 가 말한 것이 **사실인지** 센다.

규약 정본 = ``docs-private/FILING.md`` §9.

무엇을 검사하나
---------------
1. **블록 실재·필수 필드** — 규약 대상 문서에 ``doc-meta`` 와 ``kind``/``status`` 가 있는가
2. **``kind`` ↔ 위치·접미사 일치** — ``kind: record`` 인데 ``plan/`` 에 있으면 잡는다
3. **``status`` 가 그 ``kind`` 에 허용된 값인가** (FILING §8-1)
4. **``plan:`` 링크가 실재하는가** — 완료기록이 댄 PLAN 스냅샷이 실제로 있는가
5. ⭐ **``affects`` 가 거짓말하지 않는가** — 선언한 절이 **직전 스냅샷과 실제로 다른가**
6. **``supersedes`` 의 반대편** — 계승당한 PLAN 이 실제로 ``status: superseded`` 인가 (FILING §8-4)

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
FIELD = re.compile(r"^\s*([a-z_]+):\s*(.+?)\s*$", re.MULTILINE)
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


# ── ⑥ supersedes 의 반대편이 실제로 닫혔는가 ────────────────────────
# 흐름: supersedes 파싱 -> plan/ 에서 대상 찾기 -> 그 문서의 status 확인
# 왜: `supersedes:` 는 **뒤에서 앞으로만** 간다. 반대편을 사람이 고치게 두면 잊고,
#     계승된 계획이 영원히 `pending`(= 살아있는 후보) 으로 남아 거짓 재고가 된다(FILING §8-4).
def verify_supersedes(meta: dict[str, str], where: str, errors: list[Finding]) -> None:
    """``supersedes`` 가 가리킨 PLAN 이 실제로 ``superseded`` 인지 대조한다."""
    for item in (x.strip() for x in meta.get("supersedes", "").split(",") if x.strip()):
        if item.startswith("("):
            continue
        target = PRIVATE / "plan" / (item if item.endswith(".md") else f"{item}.md")
        if not target.exists():
            errors.append(Finding(where, f"`supersedes:` 가 없는 스냅샷을 가리킨다 → `plan/{target.name}`"))
            continue
        older = parse_meta(target) or {}
        was = older.get("status")
        if was != "superseded":
            errors.append(
                Finding(
                    where,
                    f"`supersedes: {item}` 인데 그쪽 `status: {was}` 다 — "
                    "계승당한 계획은 `superseded` 여야 한다 (FILING §8-4). "
                    "안 바꾸면 계승된 계획이 미착수 재고로 남는다",
                )
            )


def inspect(path: Path, axis: str | None, errors: list[Finding]) -> int:
    """문서 하나를 판정하고, affects 로 대조한 절 수를 돌려준다."""
    where = f"{axis}/{path.name}" if axis else path.name
    meta = parse_meta(path)
    if meta is None:
        errors.append(Finding(where, "`doc-meta` 블록이 없다 (FILING §9)"))
        return 0

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

    verify_supersedes(meta, where, errors)
    return verify_affects(meta, where, errors)


def main() -> int:
    """pre-push 훅 진입점.

    Returns:
        위반이 없으면 0, 있으면 1 (push 거부).
    """
    if not PRIVATE.is_dir():
        print(f"❌ {PRIVATE} 가 없다. 이 훅은 로컬 전용이라 없을 이유가 없다(fail-closed).")
        return 1

    errors: list[Finding] = []
    seen = affects_checked = 0

    for path in sorted(PRIVATE.glob("*.md")):
        seen += 1
        affects_checked += inspect(path, None, errors)

    for folder in sorted(p for p in PRIVATE.iterdir() if p.is_dir()):
        axis = folder.name
        if axis in EXEMPT_DIRS or axis in CANONLESS:
            continue
        for path in sorted(folder.glob("*.md")):
            if path.name == "README.md":
                continue
            seen += 1
            affects_checked += inspect(path, axis, errors)

    # fail-closed: 한 건도 못 모으면 "깨끗하다"가 아니라 "못 셌다"이다.
    if seen == 0:
        print(f"❌ `doc-meta` 검사 대상을 한 건도 수집하지 못했다 — {PRIVATE}")
        print("   경로 규약이 바뀌었거나 glob 이 어긋났다. 0건은 통과가 아니다(fail-closed).")
        return 1

    if errors:
        print(f"❌ `doc-meta` 위반 {len(errors)}건 (정본 = docs-private/FILING.md §9):")
        for item in errors[:25]:
            print(f"   - {item.path}: {item.reason}")
        if len(errors) > 25:
            print(f"   … 외 {len(errors) - 25}건")
        return 1

    print(f"✅ doc-meta 정합 — 문서 {seen}건 · affects 절 대조 {affects_checked}건 · 위반 0.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
