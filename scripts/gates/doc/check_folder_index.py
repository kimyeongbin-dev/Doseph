"""폴더 색인 게이트 — **색인이 폴더보다 오래 사는 것**을 막는다 (트랙 B-14 · `문서-14`).

왜 필요한가
-----------
색인(`README.md`)은 **처음 오는 사람이 먼저 읽는 자리**다. 그런데 **아무 게이트도 안 봤다** —
`check_doc_filing` 은 이름 규약을 적용할 수 없어 ``README.md`` 를 통째로 건너뛴다(`L-7`).

그래서 이런 일이 실제로 났다:

- 2026-09-20 개명에서 **참조 152회**를 고치고도 **색인 29줄이 그대로** 남았다(수동 발견).
  게이트는 **전부 초록**이었다.
- 새 공부노트를 만들고 색인을 빠뜨린 것이 **3건 중 3건**이다(대장 **D39**).
- `_legacy/…/README.md` 가 나열한 **10건 중 9건이 이미 없었다**(`L-7`).

🔑 형식이 셋이고, **셋 다 앵커가 있다**
---------------------------------------
``- **이름**`` (굵게·확장자 없음) · ``- `이름.md` `` (백틱) · 표 행 ``| `이름.md` |``.

🔴 **앵커 없이 긁으면 안 된다.** 처음엔 본문 전체에서 굵게·백틱을 긁었는데,
설명 안의 **중첩 굵게**(``**식당 비유**``)에 ``**`` 짝짓기가 밀려 **6건을 조용히 놓쳤다**
(54 를 34 로 셌다 — 대장 **D47**). 색인 항목은 **목록 항목의 맨 앞**이나 **표의 첫 칸**에만
오므로 거기에 앵커를 단다.

🔴 산문이 **다른 폴더 파일**을 언급하는 것과 가르는 기준은 **접미사**다
(``-study`` · ``-portfolio``). 안 그러면 ``DEPLOYMENT.md`` 같은 언급이 전부 dangling 으로
잡혀 **오탐 게이트**가 된다 — 사람이 끄면 옆의 정확한 게이트까지 죽는다(`QUALITY_GATES` §2-1).

🔴 이 게이트가 **못 하는 것** (한계 선언)
-----------------------------------------
- **요약이 맞는지 모른다.** 이름이 있고 파일이 있으면 통과한다. 내용은 사람이 본다.
- **색인의 «분류» 가 맞는지 모른다** — *요약이 있는 노트* 절에 요약 없이 적어도 통과한다.

사용
----
    ... check_folder_index
"""

from dataclasses import dataclass, field
from pathlib import Path
import re
import sys

from scripts.gates._root import PRIVATE

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

#: 볼 폴더와 그 폴더의 접미사. **접미사가 «이 폴더 것인가» 를 가른다.**
TARGETS = {"study": "-study", "portfolio": "-portfolio"}

#: 🔑 바닥값 — 0건은 *"어긋남이 없다"* 가 아니라 *"못 셌다"* 다. 손으로 올린다.
#: ⚠️ 2026-09-23 실측: study 54 · portfolio 11.
MIN_LISTED = {"study": 54, "portfolio": 11}

#: 🔴 **줄머리·칸머리에 앵커를 단다.** 색인 항목은 **목록 항목의 맨 앞** 또는
#:    **표의 첫 칸**에만 온다 — 산문 한가운데에는 안 온다.
#:    ⚠️ 앵커를 빼면 설명 안의 **중첩 굵게**(`**식당 비유**`)에 `**` 짝짓기가 밀려
#:    **6건을 조용히 놓친다**(실측 2026-09-23 — 54 를 34 로 셌다). 대장 `D47` 그대로다.
_ENTRY_PATTERNS = (
    re.compile(r"(?m)^\s*[-*]\s+\*\*`?([^*`]+?)`?\*\*"),  # - **이름**(요약)
    re.compile(r"(?m)^\s*[-*]\s+`([^`]+?)`"),  # - `이름.md`
    # ⚠️ 첫 칸에 이름 뒤 글자가 더 붙는다: `이름.md` (+ 짝 `.tsv`) — 칸 끝까지 허용한다.
    #    좁게 잡아 **정상 2건을 고아로 오탐**했다(실측 2026-09-23).
    re.compile(r"(?m)^\|\s*`([^`]+?)`[^|]*\|"),  # | `이름.md` (…) | … |
)


@dataclass
class IndexReport:
    """한 폴더의 색인 ↔ 실물 대조 결과.

    Attributes:
        folder: 검사한 폴더 이름.
        files: 실물 노트 수(`README.md` 제외).
        listed: 색인이 **그 폴더 것으로** 언급한 이름 수.
        dangling: 색인에만 있고 파일이 없다.
        orphan: 파일은 있는데 색인이 안 부른다.
        problem: 셀 수 없는 상태(색인 부재·바닥값 미달). `None` 이면 셀 수 있었다.
    """

    folder: str
    files: int = 0
    listed: int = 0
    dangling: list[str] = field(default_factory=list)
    orphan: list[str] = field(default_factory=list)
    problem: str | None = None


# ── 색인이 «이 폴더 것» 으로 언급한 이름 ─────────────────────────────
# 흐름: 굵게·백틱을 모두 긁는다 -> 접미사로 이 폴더 것만 남긴다
def mentioned_names(readme: str, suffix: str, files: set[str] | None = None) -> set[str]:
    """색인 본문이 언급한 **이 폴더 소속** 이름을 모은다.

    Args:
        readme: `README.md` 전문.
        suffix: 이 폴더의 파일명 접미사(`-study` 등).
        files: 그 폴더의 실물 이름. 주면 **접미사가 없어도 실물이면 소속**으로 본다.

    Returns:
        확장자를 뗀 이름 집합.
    """
    raw: set[str] = set()
    for pattern in _ENTRY_PATTERNS:
        raw |= set(pattern.findall(readme))
    cleaned = {name.strip().removesuffix(".md") for name in raw}
    # 🔴 경로가 붙은 언급(`docs-private/study/x.md`)은 파일명만 남긴다.
    cleaned = {name.rsplit("/", 1)[-1] for name in cleaned}
    # 🔴 «이 폴더 것인가» 는 **접미사 또는 실물**로 가른다.
    #    접미사만 보면 누적형(`dev-english-terms` — `FILING` §3-4 예외)이 **고아로 오탐**된다.
    #    실물만 보면 색인이 부르는 **없는 파일**(dangling)을 못 본다. 둘 다 필요하다.
    known = files or set()
    return {name for name in cleaned if name.endswith(suffix) or name in known}


# ── 폴더 하나 대조 ───────────────────────────────────────────────────
# 흐름: README 존재 -> 실물 수집 -> 언급 수집 -> 차집합 둘
def audit_folder(folder: Path, suffix: str) -> IndexReport:
    """색인과 실물을 양방향으로 대조한다.

    Args:
        folder: 검사할 폴더.
        suffix: 그 폴더의 파일명 접미사.

    Returns:
        대조 결과.
    """
    report = IndexReport(folder=folder.name)
    readme = folder / "README.md"
    if not readme.is_file():
        report.problem = f"`{folder.name}/README.md` 가 없다 — 색인이 없으면 **어긋남 0 이 아니라 못 센 것**이다"
        return report

    files = {p.stem for p in folder.glob("*.md") if p.name != "README.md"}
    listed = mentioned_names(readme.read_text(encoding="utf-8", errors="replace"), suffix, files)

    report.files = len(files)
    report.listed = len(listed)
    report.dangling = sorted(listed - files)
    report.orphan = sorted(files - listed)
    return report


def main() -> int:
    """대상 폴더들의 색인을 대조한다.

    Returns:
        종료코드 — 0 이면 통과.
    """
    problems: list[str] = []
    lines: list[str] = []

    for name, suffix in TARGETS.items():
        report = audit_folder(PRIVATE / name, suffix)
        if report.problem:
            problems.append(report.problem)
            continue
        floor = MIN_LISTED.get(name, 0)
        if report.listed < floor:
            problems.append(
                f"`{name}/` 색인이 **{report.listed}건**으로 바닥값 {floor} 아래다 — "
                "형식이 바뀌어 파서가 못 읽었을 수 있다(0건은 «없다» 가 아니라 «못 셌다»)"
            )
        if report.dangling:
            head = " · ".join(report.dangling[:6]) + (" …" if len(report.dangling) > 6 else "")
            problems.append(f"`{name}/` 색인이 **없는 파일 {len(report.dangling)}건**을 부른다: {head}")
        if report.orphan:
            head = " · ".join(report.orphan[:6]) + (" …" if len(report.orphan) > 6 else "")
            problems.append(f"`{name}/` 에 **색인이 안 부르는 파일 {len(report.orphan)}건**: {head}")
        lines.append(f"{name} {report.files}건(색인 {report.listed})")

    if problems:
        print("❌ 폴더 색인 검사 실패")
        for line in problems:
            print(f"   - {line}")
        print("   🔑 색인은 처음 오는 사람이 먼저 읽는 자리다 — 틀리면 없는 파일을 찾아 헤매게 한다.")
        return 1

    print(f"✅ 폴더 색인 — {' · '.join(lines)} · dangling 0 · orphan 0.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
