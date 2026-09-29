r"""표 모양 게이트 — **표가 렌더될 때 깨지는 것**을 막는다 (트랙 B-14 2판 · `문서-37`).

왜 필요한가
-----------
원장은 **표로 산다**. 그런데 표가 깨져도 **아무도 신호를 못 받는다**:

- 빌더(`build_followup_index`)는 **줄 단위**라 건수를 맞게 센다 — 통과한다.
- `check_doc_meta`·`check_doc_filing` 은 **머리말과 파일명**을 본다 — 통과한다.
- 깨지는 것은 **읽는 화면**뿐이다.

🔬 실측이 세 종류를 잡았다:

1. **칸 수 어긋남 4곳**(2026-09-27) — 셀 안의 **이스케이프 안 된 ``|``** 이 칸을 쪼개거나
   칸이 모자란다. 백틱 안이라도 GFM 은 칸 구분자로 읽는다(``\\|`` 만 예외).
2. **표를 쪼개는 빈 줄**(2026-09-28) — 표 행 사이에 빈 줄이 하나 들어가면 그 아래 행은
   **표 밖으로 떨어져 나간다.** 🔴 **하루에 3회 발생**했다. 원장에 항목을 «추가» 하는
   스크립트가 앵커 앞에 삽입하면서 매번 이 모양을 만들었다.
3. **끝 파이프 결손**(2026-09-29, `QA-59`) — 🔬 **렌더는 멀쩡하다.**
   ``markdown-it`` 으로 재니 ``| a | b`` 와 ``| a | b |`` 가 **똑같이** ``td`` 6개였다
   (GFM 에서 양끝 파이프는 선택이다). 그런데도 잡는 이유는 **우리 편집 방식** 때문이다 —
   행을 파이프로 잘라 **마지막 칸을 대입**하면 그 파이프가 **데이터째 사라진다.**
   🔴 **같은 날 3회 재발**했다.

🔑 **하나만 검사하면 나머지를 원리적으로 못 본다**
--------------------------------------------------
칸 수 검사는 *표 안의 행*을 본다. 그런데 ②는 **행이 표 밖으로 나간 것**이라
검사 대상 자체에서 사라진다 — **0건으로 초록**이 난다. 그래서 셋을 한 게이트에 둔다.

⚠️ **③은 앞 판이 «검사» 하기는커녕 «오보» 를 냈다.** 끝 파이프를 요구하던 ``cell_count``
가 그런 행을 «표 행이 아님» 으로 보고 **표를 거기서 끊었고**, 뒤따르는 멀쩡한 행들을
**고아로 보고**했다(실측 2건). 🔑 **모델이 GFM 과 어긋나면 «못 잡는 것» 으로 끝나지 않는다 —
«엉뚱한 것을 잡는다».** 오탐은 사람이 게이트를 끄는 경로이므로 더 비싸다.

🔴 왜 **직하 정본만** 보나 (범위 선언)
--------------------------------------
축 폴더 스냅샷(`plan/`·`record/`…)은 **그때의 사실**이고, 고치면 mtime 이 깨져
신선도 게이트의 입력이 오염된다(`FILING` §12-1 · 대장 `D41`).
⇒ **조치가 불가능한 대상을 검사하면 사람이 게이트를 끈다.** 고칠 수 있는 것만 본다.

🔴 **검사하는 것과 «세는» 것은 다르다**(`QA-58`)
-----------------------------------------------
직하의 **작업 버퍼**(``PLAN``·``REPORT``·``RECORD``)도 표가 깨지면 안 되므로 **검사는 한다.**
그러나 **바닥값에는 세지 않는다** — 있다가 없어지는 것이 정상이라, 세면 기준선이
**진행 중인 작업을 따라다닌다.** 실제로 앞 판이 그래서 상수 주석까지 거짓이 됐다.

🔴 이 게이트가 **못 하는 것** (한계 선언)
-----------------------------------------
- **내용이 맞는지 모른다.** 칸 수가 맞으면 통과한다.
- **정렬·너비**를 모른다. 렌더 결과를 보는 것이 아니라 구분자를 세는 것이다.
- 🔑 **③은 렌더 결함이 아니라 «우리 편집 도구가 깨지는 모양» 이다.** 다른 저장소에서는
  이 검사가 **순수한 스타일 규칙**이다 — 그 구분을 흐리면 «왜 막히나» 를 설명할 수 없다.
- **코드 펜스 안**은 통째로 건너뛴다 — 거기 있는 ``|`` 는 표가 아니다.

사용
----
    uv run python -m scripts.gates.doc.check_table_shape
"""

from dataclasses import dataclass, field
from pathlib import Path
import re
import sys

from scripts.gates._root import PRIVATE
from scripts.gates.doc.check_doc_filing import STATE_CANONS

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

#: 🔑 바닥값 — 표 머리를 **0개** 세면 «표가 없다» 가 아니라 **파서가 죽은 것**이다.
#:    그 상태에서는 어떤 어긋남도 0건이라 **조용히 초록**이 난다.
#:
#: 🔴 **무엇을 센 수인가** — `STATE_CANONS` **10건의 표 머리 수**다(작업 버퍼 제외).
#:    🔬 2026-09-29 실측 **115**. 여유 5.
#:
#: ⚠️ **앞 판 주석은 거짓이었다**(`QA-58`). *«직하 정본 10건에서 121개»* 라고 적혀 있었는데
#:    정본만 세면 그때도 `114` 였다. `121` 은 **틀린 수가 아니라 다른 모집단의 수**다(`D43`) —
#:    잴 때 직하에 `PLAN.md` 가 살아 있었고 그 스냅샷이 표 **8개**를 들고 있다.
#:
#: 🔑 **그래서 수만 고치면 안 된다.** 앞 판은 `PRIVATE.glob` 전부를 셌으므로
#:    **작업 버퍼가 열렸는지에 따라 기준선이 움직였다** — 버퍼가 열린 동안은 느슨해지고
#:    닫히면 갑자기 조여진다. 바닥값의 목적은 *«파서가 죽었나»* 인데 기준선이
#:    진행 중인 작업을 따라다니면 그 질문에 답할 수 없다.
#:    ⇒ **검사는 전부 하고, 세는 것은 정본만 한다.**
#:
#: 📉 **줄어들면 실패다** — 배출 등으로 표가 정말 줄었으면 이 값을 **의식적으로** 내리고
#:    사유를 여기 적는다. 조용히 내려가는 것을 막는 것이 이 상수의 존재 이유다.
MIN_TABLES = 110

#: 🔴 **모집단 바닥값.** 정본 파일이 줄면 표 머리도 같이 줄어 «표가 없다» 와 구별되지 않는다.
#:    `check_doc_filing` 도 «상태 정본이 없으면 결함» 을 보지만, **이 게이트의 바닥값이
#:    의미를 가지려면 이 게이트가 스스로 자기 모집단을 단언**해야 한다.
MIN_CANON_FILES = len(STATE_CANONS)

#: 코드 펜스 — 여는 줄과 닫는 줄. 안쪽의 ``|`` 는 표가 아니다(mermaid·표 예시).
FENCE = re.compile(r"^\s*(```|~~~)")

#: 구분선 — ``|---|:---:|`` 꼴. **하이픈이 하나는 있어야** 한다
#: (없으면 ``| a | b |`` 같은 평범한 행도 구분선으로 읽힌다).
#: 🔤 2026-09-29: **끝 파이프를 선택으로** 바꿨다 — GFM 이 그렇다(아래 ``cell_count``).
SEPARATOR = re.compile(r"^\|[\s:|-]*-[\s:|-]*$")

#: 이스케이프된 파이프. GFM 은 ``\|`` 만 칸을 안 쪼갠다 — **백틱 안이어도 쪼갠다.**
ESCAPED_PIPE = "\\|"
_PLACEHOLDER = "\x00"


def cell_count(line: str) -> int | None:
    """표 행의 칸 수. 표 행이 아니면 ``None``.

    🔬 **끝 파이프는 요구하지 않는다**(2026-09-29 실측, `QA-59`). GFM 에서 양끝 파이프는
    **선택**이라 ``| a | b`` 도 ``| a | b |`` 와 **똑같이 렌더된다**(``markdown-it`` 으로
    재니 둘 다 ``td`` 6개). 끝 파이프를 요구하던 앞 판은 그런 행을 «표 행이 아님» 으로 보고
    **거기서 표를 끊었고**, 뒤따르는 멀쩡한 행들을 **고아로 오보**했다(실측 2건).

    🔑 **앞 파이프는 여전히 요구한다.** GFM 은 그것도 선택이지만, 풀면 산문 ``a | b`` 가
    표 행으로 읽힌다 — **오탐은 사람이 게이트를 끄게 만든다.**

    Args:
        line: 원본 한 줄.

    Returns:
        칸 수, 또는 표 행이 아니면 ``None``.
    """
    body = line.strip()
    if len(body) < 2 or not body.startswith("|"):
        return None
    masked = body.replace(ESCAPED_PIPE, _PLACEHOLDER)
    return len(masked.strip("|").split("|"))


@dataclass
class Report:
    """한 파일의 검사 결과."""

    tables: int = 0
    mismatched: list[str] = field(default_factory=list)
    orphans: list[str] = field(default_factory=list)
    dangling: list[str] = field(default_factory=list)


def audit(path: Path) -> Report:
    """한 파일의 표를 훑어 칸 어긋남과 고아 행을 모은다.

    Args:
        path: 검사할 마크다운 파일.

    Returns:
        그 파일의 :class:`Report`.
    """
    report = Report()
    lines = path.read_text(encoding="utf-8").split("\n")

    def flag(text: str, at: int) -> None:
        """끝 파이프가 빠진 표 행을 모은다.

        Args:
            text: 그 줄.
            at: 0-기반 줄 번호.
        """
        if not text.strip().endswith("|"):
            report.dangling.append(f"{path.name}:{at + 1}  {text.strip()[:60]}")

    in_fence = False
    index = 0
    while index < len(lines):
        line = lines[index]
        if FENCE.match(line):
            in_fence = not in_fence
            index += 1
            continue
        if in_fence:
            index += 1
            continue

        head = cell_count(line)
        if head is None:
            index += 1
            continue

        # 표 행이다. 다음 줄이 구분선이어야 **표의 머리**다.
        following = lines[index + 1] if index + 1 < len(lines) else ""
        if not SEPARATOR.match(following.strip()):
            # 🔴 머리가 없는 표 행 = 표 밖으로 떨어져 나간 행.
            report.orphans.append(f"{path.name}:{index + 1}  {line.strip()[:60]}")
            index += 1
            continue

        report.tables += 1
        flag(line, index)
        flag(following, index + 1)
        separator_cells = cell_count(following)
        if separator_cells != head:
            report.mismatched.append(f"{path.name}:{index + 2}  구분선 {separator_cells}칸 vs 머리 {head}칸")
        index += 2
        while index < len(lines):
            body = cell_count(lines[index])
            if body is None or FENCE.match(lines[index]):
                break
            flag(lines[index], index)
            if body != head:
                report.mismatched.append(
                    f"{path.name}:{index + 1}  칸 {body} vs 머리 {head}  | {lines[index].strip()[:55]}"
                )
            index += 1
    return report


def counts_toward_floor(path: Path) -> bool:
    """바닥값에 세는 대상인가 — **상태 정본만**.

    🔑 작업 버퍼(`PLAN`·`REPORT`·`RECORD`)와 커밋하지 않는 생성물은 **검사는 받지만
    세지는 않는다.** 있다가 없어지는 것이 정상이라, 세면 기준선이 흔들린다(`QA-58`).

    Args:
        path: 검사 대상 파일.

    Returns:
        상태 정본이면 ``True``.
    """
    return path.name in STATE_CANONS


def targets(argv: list[str] | None = None) -> list[Path]:
    """검사 대상. 인자가 없으면 ``docs-private/`` **직하** 마크다운.

    Args:
        argv: 표본 경로들(결핍 주입 하네스가 쓴다). 비어 있으면 기본 대상.

    Returns:
        파일 경로 목록 (이름순).
    """
    if argv:
        return sorted(Path(a) for a in argv)
    return sorted(p for p in PRIVATE.glob("*.md") if p.is_file())


def main(argv: list[str] | None = None) -> int:
    """게이트 진입점.

    Args:
        argv: 표본 경로들. 없으면 정본을 본다.

    Returns:
        위반이 있으면 1, 없으면 0.
    """
    sample_mode = bool(argv)
    files = targets(argv)
    if not files:
        print("❌ 표 모양 검사 — 대상이 0건이다 (fail-closed: 경로가 바뀌었을 수 있다)")
        return 1

    tables = 0
    canon_tables = 0
    canon_files = 0
    mismatched: list[str] = []
    orphans: list[str] = []
    dangling: list[str] = []
    for path in files:
        report = audit(path)
        tables += report.tables
        if counts_toward_floor(path):
            canon_tables += report.tables
            canon_files += 1
        mismatched.extend(report.mismatched)
        orphans.extend(report.orphans)
        dangling.extend(report.dangling)

    # 🔑 표본 모드에서도 바닥값을 **0 으로 낮추지 않는다** — 0 이면 파서가 죽은 것이다.
    #    🔴 정본 모드에서는 **정본만** 센다(`QA-58`) — 작업 버퍼는 있다가 없어지는 것이 정상이라
    #    세면 기준선이 진행 중인 작업을 따라다닌다.
    floor = 1 if sample_mode else MIN_TABLES
    counted = tables if sample_mode else canon_tables
    problems: list[str] = []
    if counted < floor:
        problems.append(
            f"표 머리가 **{counted}개**로 바닥값 {floor} 아래다 — "
            "파서가 죽으면 어긋남이 0건으로 보인다(0은 «깨끗» 이 아니라 «못 셌다»)"
        )
    if not sample_mode and canon_files < MIN_CANON_FILES:
        missing = sorted(STATE_CANONS - {p.name for p in files})
        problems.append(
            f"상태 정본이 **{canon_files}건**으로 바닥값 {MIN_CANON_FILES} 아래다 — "
            f"모집단이 줄면 표 머리도 같이 줄어 «파서가 죽은 것» 과 구별되지 않는다: {', '.join(missing)}"
        )
    if mismatched:
        problems.append(f"**칸 수 어긋남 {len(mismatched)}건** — 렌더될 때 표가 깨진다")
    if orphans:
        problems.append(f"**표 밖으로 떨어진 행 {len(orphans)}건** — 표 행 사이에 빈 줄이 들어갔거나 구분선이 없다")
    if dangling:
        problems.append(
            f"**끝 파이프가 빠진 표 행 {len(dangling)}건** — 렌더는 멀쩡하다. "
            "행을 파이프로 잘라 마지막 칸을 대입하는 편집이 그 파이프를 데이터째 날린 것이다"
        )

    if problems:
        print("❌ 표 모양 검사 실패")
        for line in problems:
            print(f"   - {line}")
        for line in mismatched[:12]:
            print(f"     · {line}")
        for line in orphans[:12]:
            print(f"     · {line}")
        for line in dangling[:12]:
            print(f"     · {line}")
        print("   🔑 빌더도 게이트도 줄 단위라 통과한다 — 깨지는 것은 읽는 화면뿐이다.")
        return 1

    print(
        f"✅ 표 모양 — 검사 {len(files)}건(정본 {canon_files}) · "
        f"표 머리 {tables}개(정본 {canon_tables} · 바닥값 {floor}) · "
        "칸 어긋남 0 · 고아 행 0 · 끝 파이프 결손 0."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
