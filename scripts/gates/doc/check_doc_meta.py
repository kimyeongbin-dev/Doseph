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
8. ⭐ **보류가 고아가 아닌가** — ``pending`` 을 ``ROADMAP.md`` 가 이름으로 가리키는가 (FILING §8-5)
9. ⭐ **``partial`` 이 나머지를 가리키는가** — ``remainder:`` 존재 + 대상 실재 (FILING §8-6)
10. 🔴 **``ROADMAP.md`` §지금 위치가 직하 ``PLAN.md`` 와 맞는가** — 진행 중인 계획이 있는데
   *"없다"* 라고 적혀 있으면(또는 그 반대) 다음 세션이 **거짓을 읽는다**

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

✅ **음성 대조 표본** — 이것들은 **통과해야** 한다:
  - ``done`` · ``rejected`` · ``withdrawn`` — **종결 상태라 아무것도 안 가리켜도 된다**
  - 판 교체형 정본 스냅샷(``filing/`` 등)의 ``superseded`` — 후속이 폴더로 도출되므로 역링크가 없다
  - ``_legacy/`` · ``_unfiled/`` · ``study/`` · ``portfolio/`` — ``doc-meta`` 를 요구하지 않는다
  - PLAN 이 없을 때 §지금 위치가 *"없다"* 라고 말하는 정상 쌍
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

EXEMPT_DIRS = frozenset({"_legacy", "_unfiled", "__pycache__"})
#: 정본이 없는 축 — 직하에 있은 적이 없어 생애주기가 없다. ``doc-meta`` 를 요구하지 않는다.
CANONLESS = frozenset({"study", "portfolio"})

BLOCK = re.compile(r"<!--\s*doc-meta\s*(.*?)-->", re.DOTALL)
#: ``\s`` 는 줄바꿈을 포함하므로 값이 빈 필드가 **다음 줄을 값으로 삼킨다** —
#: 실제로 `supersedes:` 를 비웠더니 값이 ``affects:  FILING`` 으로 읽혔다. 줄 안으로 가둔다.
FIELD = re.compile(r"^[ 	]*([a-z_]+):[ 	]*(.+?)[ 	]*$", re.MULTILINE)
DATED = re.compile(r"^(\d{4}-\d{2}-\d{2})_([a-z0-9-]+)-([a-z]+)\.md$")

#: kind 별로 허용되는 status (FILING §8-1). 여기 없는 값은 오타이거나 규약 밖이다.
#: 🔴 ``active`` 는 **은퇴했다**(2026-09-20). 한 단어를 두 뜻으로 쓰고 있었다 —
#: 작업버퍼의 *"진행 중"* 과 상태정본의 *"현재 유효한 판"*. 후자는 Apache Geode 의 ``active``
#: (*구현이 끝난 유효 결정*)와 뜻이 겹치고 전자와는 거의 반대라, 둘을 갈랐다.
#:   작업버퍼(plan·report·record) → ``in-progress``
#:   상태정본(architecture·deploy·…) → ``current``
#: ``dropped`` 도 갈랐다 — RFC 관행대로 ``rejected``(검토 후 기각)와 ``withdrawn``(철회).
ALLOWED_STATUS: dict[str, frozenset[str]] = {
    "plan": frozenset(
        {"draft", "in-progress", "pending", "done", "rejected", "withdrawn", "superseded", "partial"},
    ),
    "report": frozenset({"in-progress", "done", "rejected", "withdrawn", "partial"}),
    "record": frozenset({"in-progress", "partial", "done"}),
    "architecture": frozenset({"current", "superseded"}),
    "deploy": frozenset({"current", "superseded"}),
    "filing": frozenset({"current", "superseded"}),
    "roadmap": frozenset({"current", "superseded"}),
    "mistake": frozenset({"current", "superseded"}),
    "queue": frozenset({"current", "superseded"}),
    "drift": frozenset({"current", "superseded"}),
}
#: 직하 작업버퍼 — `closes:` 선언을 요구하는 종류(FILING §9 · 문서-32).
BUFFER_KINDS = frozenset({"plan", "report", "record"})

#: 직하에 있을 수 있는 status — 작업버퍼 2종 + 상태정본 1종.
TOP_STATUS = frozenset({"draft", "in-progress", "current"})

#: 하위 검사의 **바닥값**. 0건은 *"위반이 없다"* 가 아니라 *"대상이 사라져 아무것도 못 봤다"* 이다.
#: 실제로 ``check_utf8_guard`` 가 경로 이동 뒤 대상 11건 → 1건이 되고도 초록을 냈다(대장 **D31**).
#: 이 값을 낮춰야 할 상황이 오면 그건 **의식적인 결정**이어야 한다 — 조용히 0이 되는 것과 다르다.
MIN_AFFECTS = 1
MIN_SUCCESSION = 1
MIN_PLANS = 1
MIN_DONE_MARKS = 1

#: 완료 판정 체크박스. ``- [ ]`` / ``- [x]`` 를 **줄 머리 앵커**로 센다 —
#: 본문 산문에 섞인 대괄호를 줍지 않기 위해서다(대장 D47: 구조를 문자열로 세지 않는다).
UNCHECKED = re.compile(r"^[ 	]*- \[ \]", re.MULTILINE)
CHECKED = re.compile(r"^[ 	]*- \[[xX]\]", re.MULTILINE)

#: ``status: done`` 인데 완료 판정을 **하나도** 안 채운 채 닫힌 과거 스냅샷.
#: 🔴 면제는 *"괜찮다"* 가 아니라 **"정보가 이미 소실됐다"** 는 선언이다 — 무엇을 못 하고
#: 닫았는지 복구할 길이 없어 지금 채우면 그게 거짓이 된다. 사유 없는 면제는 막는다.
#: ⚠️ **이 표는 자라면 안 된다.** 새 이름이 여기 들어가려 하면 그건 면제가 아니라 규칙 위반이다.
DONE_MARK_EXEMPT: dict[str, str] = {
    "2026-09-08_gcp-login-mvp-plan.md": "2026-09-08 종료. 판정 5개 미체크 — 당시 실측이 남아 있지 않다.",
    "2026-09-12_budget-autostop-plan.md": (
        "2026-09-12 종료. 판정 4개 미체크. 킬스위치 자동배선은 org 정책으로 기각됐고 그 사실은 배너에만 남았다."
    ),
    "2026-09-12_schema-cleanup-dto-hardening-plan.md": "2026-09-12 종료. 판정 4개 미체크.",
    "2026-09-15_qa04-vector-tests-plan.md": "2026-09-15 종료. 판정 5개 미체크.",
    "2026-09-16_filing-convention-plan.md": "2026-09-16 종료. 판정 7개 미체크.",
}

#: 계승하지 않았음을 **명시**하는 값. 빈칸을 허용하면 *"계승 안 했다"* 와 *"적는 걸 잊었다"* 가
#: 같은 모양이 되어, 게이트는 **선언이 사실인지**만 볼 뿐 **선언이 빠졌는지**를 못 본다.
NO_SUCCESSION = "none"

#: 보류를 **살려 두는** 문서. 여기서 이름이 불리지 않는 보류는 고아다(FILING §8-5).
ROADMAP = "ROADMAP.md"
#: 🔑 `suspended` 는 2026-09-23 에 `pending` 으로 통합됐다(FILING §8-1 · 문서-20).
RESUMABLE = frozenset({"pending"})

#: ``remainder:`` 가 가리킬 수 있는 곳. **살아서 갱신되는 자리**여야 한다 — 스냅샷을 가리키면
#: 그 자체가 또 안 바뀌므로 추적이 한 칸 옮겨졌을 뿐이다(FILING §8-6).
REMAINDER_TARGETS = (
    (re.compile(r"^ROADMAP#(\S+)$"), ROADMAP),
    (re.compile(r"^(QA-\d+)$"), "FOLLOWUP_QUEUE.md"),
    (re.compile(r"^(문서-\d+)$"), "DOC_TRUTH_DRIFT.md"),
)

#: ``ROADMAP.md`` §지금 위치의 "진행 중인 계획" 줄. 이 한 줄이 *"어디까지 왔나"* 의 단일 답이다.
POSITION_ROW = re.compile(r"^\|\s*\*\*진행 중인 계획\*\*\s*\|(.+?)\|\s*$", re.MULTILINE)
#: 그 줄이 *"없다"* 고 주장하는 형태.
#: 🔴 «없다» 와 «없음» 은 같은 뜻인데 하나만 받으면 **정상 문장이 위반으로 잡힌다**
#:    (2026-09-23 실측: `⬜ **없음**` 이 막혔다). 어휘가 아니라 **뜻**을 받는다.
CLAIMS_NONE = re.compile(r"\*\*없다\.?\*\*|없다\.|\*\*없음\*\*|없음")

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
# 흐름: pending 인가 -> ROADMAP 이 그 파일명을 부르는가
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
                "되살릴 생각이 없으면 `rejected`(기각) 또는 `withdrawn`(철회)으로 닫는다 (FILING §8-5)",
            )
        )
    return 1


#: ``inspect`` 가 세는 ``partial`` 대조 건수. 모듈 수준 누산기(시그니처를 더 늘리지 않는다).
remainder_checked = [0]
parent_checked = [0]
done_marks_checked = [0]


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
        errors.append(
            Finding(where, f"직하인데 `status: {status}` 다 — 직하는 {sorted(TOP_STATUS)} 뿐이다"),
        )

    # 🔴 `closes:` 선언 강제 — **직하 작업버퍼에만** (FILING §9 · 문서-32).
    #    빈칸을 허용하면 «닫는 게 없다» 와 «적는 걸 잊었다» 가 같은 모양이 된다(§8-4 논리).
    #    ⚠️ 소급하지 않는다 — 닫힌 스냅샷 58건에 필드를 넣으면 **mtime 이 깨진다**(§12-1).
    #    선언 강제는 **작성자가 그 자리에 있을 때만** 값이 있다.
    if axis is None and kind in BUFFER_KINDS and not meta.get("closes"):
        errors.append(
            Finding(
                where,
                "직하 작업버퍼인데 `closes:` 가 비었다 — 닫는 게 없으면 `none` 이라고 **적는다**(FILING §9)",
            ),
        )

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
    remainder_checked[0] += verify_remainder(meta, where, errors)
    parent_checked[0] += verify_parent(meta, path, axis, where, errors)
    done_marks_checked[0] += verify_done_marks(meta, path, where, errors)
    links_checked = verify_supersedes(meta, path, axis, where, errors)
    return verify_affects(meta, where, errors), links_checked


# ── ⑨ partial 이 나머지를 가리키는가 ─────────────────────────────────
# 흐름: status == partial 인가 -> remainder: 가 있는가 -> 그 대상이 실재하는가
# 왜: 스냅샷은 갱신되지 않는다. `partial` 을 그냥 허용하면 그 문서는 **영원히 미완**인 채
#     남고 나머지가 어디 갔는지 아무도 모른다 — `pending` 이 고아가 되는 것과 같은 실패다.
#     문제는 *"영원히 partial"* 이 아니라 ***"가리키는 데가 없는 partial"*** 이다(FILING §8-6).
# ── ⑩ parent 가 실재하는 상위 PLAN 을 가리키는가 ─────────────────────
# 흐름: parent 값 -> plan/ 에서 대상 찾기 -> 자기 자신이 아닌가
# 왜: 축소판·1단계는 상위를 **대신하지 않고 일부를 먼저 끝낸 것**이라 `supersedes` 로 적으면
#     거짓이 된다. 역링크(`children:`)는 두지 않는다 — 1:N 이라 하위가 늘 때마다 상위가
#     낡는다. 반대편은 `grep` 으로 도출된다(FILING §9-2).
# ── ⑪ done 이 완료 판정을 통과한 결과인가 ────────────────────────────
# 흐름: status == done 인가 -> 본문에 완료 판정 체크박스가 있나 -> 채운 것이 하나라도 있나
# 왜: 닫기 절차가 요구하는 `doc-meta`·배너는 **문서 머리**에 있고 완료 판정은 **문서 끝**에 있다.
#     머리를 고치면 닫은 것 같은 감각이 생겨 꼬리를 안 본다 — D27(완료기록을 쓰면 스냅샷도
#     쓴 것 같다)과 같은 모양이고, 실측하니 **done 7건 중 6건이 체크 0개**였다(대장 **D51**).
#     기존 검사는 전부 *필드*를 본다. 이것만이 **본문이 자기 메타와 모순인지**를 본다.
# 🔑 일부만 채운 것은 **정상이다.** `qa01-hard-delete` 는 8/10 을 채우고 미체크 2건에
#     *"달성 못 함 — soft_delete 13개가 이름을 유지한 채 남아 있다"* 를 적었다(→ QA-30).
#     체크박스는 자랑하는 칸이 아니라 **"done 이지만 이건 못 했다"가 파일에 남는 유일한 자리**다.
def verify_done_marks(meta: dict[str, str], path: Path, where: str, errors: list[Finding]) -> int:
    """``status: done`` 인 PLAN 의 완료 판정이 채워졌는지 본다. 검사했으면 1.

    Returns:
        검사 대상이었으면 1, 아니면 0 (바닥값 입력).
    """
    if meta.get("kind") != "plan" or meta.get("status") != "done":
        return 0
    text = path.read_text(encoding="utf-8", errors="replace")
    unchecked, checked = len(UNCHECKED.findall(text)), len(CHECKED.findall(text))
    if unchecked + checked == 0:
        return 0  # 완료 판정 절이 없는 PLAN — 검사 대상이 아니다
    if checked:
        return 1  # 하나라도 채웠으면 통과. 미체크는 "못 했다"를 남긴 정당한 형태다
    reason = DONE_MARK_EXEMPT.get(path.name)
    if reason is not None:
        if not reason.strip():
            errors.append(Finding(where, "`DONE_MARK_EXEMPT` 항목에 사유가 비었다 — 사유 없는 면제는 면제가 아니다"))
        return 1
    errors.append(
        Finding(
            where,
            f"`status: done` 인데 완료 판정 {unchecked}개가 **하나도** 채워지지 않았다 — "
            "메타는 완료라 하고 본문은 아무것도 안 했다고 한다. 한 줄씩 보고 `- [x]` 로 바꾸거나, "
            "못 한 것은 `- [ ]` 로 두고 **왜 못 했는지 그 자리에 적는다** (대장 D51)",
        )
    )
    return 1


def verify_parent(meta: dict[str, str], path: Path, axis: str | None, where: str, errors: list[Finding]) -> int:
    """``parent:`` 가 실재하는 상위 PLAN 을 가리키는지 본다. 검사했으면 1."""
    target = (meta.get("parent") or "").strip()
    if not target:
        return 0
    if target == plan_identity(path, axis):
        errors.append(Finding(where, "`parent:` 가 자기 자신을 가리킨다"))
        return 1
    if not resolve_plan(target).exists():
        errors.append(
            Finding(where, f"`parent:` 가 없는 상위 PLAN 을 가리킨다 → `{target}` (FILING §9-2)"),
        )
    return 1


def verify_remainder(meta: dict[str, str], where: str, errors: list[Finding]) -> int:
    """``partial`` 의 ``remainder:`` 를 대조한다. 검사했으면 1."""
    if meta.get("status") != "partial":
        if meta.get("remainder"):
            errors.append(
                Finding(where, f"`remainder:` 가 있는데 `status: {meta.get('status')}` 다 — `partial` 일 때만 쓴다")
            )
        return 0

    target = (meta.get("remainder") or "").strip()
    if not target:
        errors.append(
            Finding(
                where,
                "`status: partial` 인데 `remainder:` 가 없다 — 남은 범위가 어디로 갔는지 "
                "가리키지 않으면 **영원히 미완인 채 잊힌다** (FILING §8-6)",
            )
        )
        return 1

    for pattern, canon in REMAINDER_TARGETS:
        matched = pattern.match(target)
        if not matched:
            continue
        body = (PRIVATE / canon).read_text(encoding="utf-8", errors="replace") if (PRIVATE / canon).exists() else ""
        if matched.group(1) not in body:
            errors.append(
                Finding(where, f"`remainder: {target}` 가 `{canon}` 에 없다 — 살아 있는 자리를 가리켜야 한다")
            )
        return 1

    # 남은 형태 = PLAN 슬러그
    plan = resolve_plan(target)
    if not plan.exists():
        errors.append(
            Finding(
                where,
                f"`remainder: {target}` 를 해석하지 못했다 — "
                "`ROADMAP#단계` · `QA-##` · `문서-N` · PLAN 슬러그 중 하나여야 한다 (FILING §8-6)",
            )
        )
    return 1


# ── ⑨ ROADMAP §지금 위치 ↔ 직하 PLAN.md ──────────────────────────────
# 흐름: PLAN.md 실재 여부 -> ROADMAP 의 "진행 중인 계획" 줄이 그것과 맞는가
# 왜: 이 한 줄은 `MEMORY.md` 가 *"어디까지 왔나 = ROADMAP 맨 위 §지금 위치"* 라고
#     가리키는 **단일 답**이다. 여기가 거짓이면 **다음 세션이 통째로 거짓을 읽고 시작한다**
#     — 압축·`/clear` 를 넘어 살아남는 층이라 손상 범위가 가장 넓다.
#     실제로 2026-09-20 에 PLAN.md 가 `active` 인데 이 줄이 *"없다"* 였다.
def verify_roadmap_position(errors: list[Finding]) -> int:
    """§지금 위치의 "진행 중인 계획" 줄이 직하 ``PLAN.md`` 와 맞는지 본다. 검사했으면 1."""
    text = roadmap_text()
    if not text:
        errors.append(Finding(ROADMAP, "정본을 읽지 못했다 — §지금 위치를 대조할 수 없다(fail-closed)"))
        return 0
    matched = POSITION_ROW.search(text)
    if not matched:
        errors.append(
            Finding(ROADMAP, "§지금 위치에 `| **진행 중인 계획** |` 줄이 없다 — 표 모양이 바뀌면 이 검사가 눈이 먼다")
        )
        return 0

    cell = matched.group(1)
    says_none = bool(CLAIMS_NONE.search(cell))
    plan = PRIVATE / OPEN_PLAN
    if plan.exists() and says_none:
        errors.append(
            Finding(
                ROADMAP,
                f'§지금 위치가 *"진행 중인 계획 없다"* 라는데 `{OPEN_PLAN}` 이 실재한다 — '
                "다음 세션이 거짓을 읽는다. PLAN 을 열거나 닫으면 이 줄도 **같은 동작으로** 고친다 (CLAUDE.md §1.1)",
            )
        )
    elif not plan.exists() and not says_none:
        errors.append(
            Finding(
                ROADMAP,
                f"§지금 위치가 진행 중인 계획을 말하는데 `{OPEN_PLAN}` 이 없다 — "
                "닫으면서 이 줄을 안 고쳤다. 구식 PLAN 을 현재로 읽게 만드는 것과 같은 실패",
            )
        )
    elif plan.exists() and OPEN_PLAN not in cell:
        errors.append(
            Finding(ROADMAP, f"§지금 위치가 진행 중이라고는 하는데 `{OPEN_PLAN}` 을 **경로로 가리키지 않는다**")
        )
    return 1


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
        plans_seen += (parse_meta(path) or {}).get("kind") == "plan"

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
    position_checked = verify_roadmap_position(errors)

    for label, count, floor, why in (
        ("affects 절 대조", affects_checked, MIN_AFFECTS, "affects 선언이 사라졌거나 비교할 스냅샷이 없다"),
        ("계승 링크 대조", links_checked, MIN_SUCCESSION, "supersedes/superseded_by 파싱이 깨졌거나 필드명이 바뀌었다"),
        ("PLAN 모집단", plans_seen, MIN_PLANS, "plan/ 경로가 바뀌었거나 kind 파싱이 깨졌다"),
        (
            "done 완료 판정",
            done_marks_checked[0],
            MIN_DONE_MARKS,
            "체크박스 정규식이 깨졌거나 done 스냅샷이 사라졌다 — 0건은 '위반 없음' 이 아니라 '아무것도 못 봤음' 이다",
        ),
        ("§지금 위치 대조", position_checked, 1, "ROADMAP.md 가 없거나 §지금 위치 표 모양이 바뀌었다"),
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
        f"계승 링크 대조 {links_checked}건 · PLAN {plans_seen}건(고아 0) · "
        f"partial {remainder_checked[0]}건 · parent {parent_checked[0]}건 · "
        f"done 판정 {done_marks_checked[0]}건(면제 {len(DONE_MARK_EXEMPT)}) · §지금 위치 ✅ · 위반 0."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
