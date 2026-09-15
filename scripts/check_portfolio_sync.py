"""포트폴리오 문서가 근거보다 낡았는지 추적한다.

**왜 이 검사가 있나** (2026-09-15):

`doseph-security-posture.md` 가 **끝난 일 5건을 "진행 예정" 으로 소개**하고 있었다
(CSP·WAF·CI 보안게이트·의심입력 로깅·로깅 정비 — 전부 완료 상태였다).
포트폴리오 문서에서 이건 틀린 정보일 뿐 아니라 **자기 성과를 깎아먹는다.**

포트폴리오 문서는 **저장소의 사실을 빌려다 쓴다.** 원본이 바뀌면 조용히 낡는데,
그 낡음을 알려 주는 장치가 없었다.

## 무엇을 차단하고 무엇을 보고만 하나

| 검사 | 성격 | 취급 |
|---|---|---|
| `portfolio-sync` 블록 자체가 없다 | 규약 위반(이분법) | 🔴 **실패** |
| `sources` 가 **없는 경로**를 가리킨다 | 파일 실재 여부(이분법) | 🔴 **실패** |
| `status: draft` | 아직 완료 아님 | 🟡 **보고** — 끝날 때까지 매번 |
| `sources` 중 하나가 `baseline` 보다 새롭다 | 동기화 필요 신호 | 🟡 **보고** |

**뒤의 둘을 차단하지 않는 이유**: 근거 문서는 자주 바뀐다. 차단하면 관계없는 작업이
막히고, 그러면 사람이 게이트를 끈다 — 옆의 정확한 검사까지 죽는다
(`docs/QUALITY_GATES.md` §2-1).

⚠️ `docs-private/` 는 git 밖이라 다른 머신·CI 에는 없다 → **없으면 조용히 통과**.
"""

from datetime import UTC, date, datetime
from pathlib import Path
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parents[1]
PORTFOLIO_DIR = REPO_ROOT / "docs-private" / "portfolio"

BLOCK = re.compile(r"<!--\s*portfolio-sync\s*(.*?)-->", re.DOTALL)
FIELD = re.compile(r"^(status|baseline|note):\s*(.+?)\s*$", re.MULTILINE)
SOURCE = re.compile(r"^\s*-\s*(\S+)\s*$", re.MULTILINE)

EXCLUDE = {"README.md"}


# ── 문서 하나의 동기화 상태 판정 ────────────────────────────────────────
# 흐름: portfolio-sync 블록 파싱 -> status/baseline/sources 추출
#       -> source 실재·mtime 을 baseline 과 비교
def inspect(path: Path) -> tuple[list[str], list[str]]:
    """Return (errors, warnings) for one portfolio document."""
    text = path.read_text(encoding="utf-8")
    name = path.name
    found = BLOCK.search(text)
    if not found:
        return ([f"{name}: `portfolio-sync` 블록이 없다 (portfolio/README.md 규약)"], [])

    body = found.group(1)
    fields = dict(FIELD.findall(body))
    sources = SOURCE.findall(body)

    errors: list[str] = []
    warnings: list[str] = []

    raw_baseline = fields.get("baseline", "")
    try:
        baseline = date.fromisoformat(raw_baseline)
    except ValueError:
        return ([f"{name}: baseline 이 `YYYY-MM-DD` 가 아니다 ({raw_baseline!r})"], [])

    if not sources:
        errors.append(f"{name}: `sources` 가 비어 있다 — 무엇을 근거로 쓴 문서인지 적어야 추적된다")

    stale: list[str] = []
    for source in sources:
        target = REPO_ROOT / source
        if not target.exists():
            errors.append(f"{name}: sources 가 없는 경로를 가리킨다 → {source}")
            continue
        # aware datetime -> 로컬 날짜. baseline 이 로컬 기준 날짜라 맞춰야 하루가 어긋나지 않는다.
        changed = datetime.fromtimestamp(target.stat().st_mtime, tz=UTC).astimezone().date()
        if changed > baseline:
            stale.append(f"{source} ({changed})")

    if stale:
        warnings.append(
            f"{name}: 근거가 baseline({baseline}) 보다 새롭다 — 동기화 필요\n"
            + "".join(f"        · {s}\n" for s in stale).rstrip(),
        )

    if fields.get("status") == "draft":
        note = fields.get("note", "")
        warnings.append(f"{name}: **draft** — 아직 완료된 문서가 아니다" + (f"\n        · {note}" if note else ""))

    return (errors, warnings)


# ── 게이트 본문 ─────────────────────────────────────────────────────────
# 흐름: portfolio/*.md 순회 -> 문서별 판정 -> 오류는 차단, 경고는 보고
def main() -> int:
    if not PORTFOLIO_DIR.exists():
        print("· 포트폴리오 폴더가 없는 환경 — 조용히 통과한다.")
        return 0

    docs = [p for p in sorted(PORTFOLIO_DIR.glob("*.md")) if p.name not in EXCLUDE]
    if not docs:
        print("· 추적할 포트폴리오 문서가 없다.")
        return 0

    all_errors: list[str] = []
    all_warnings: list[str] = []
    for doc in docs:
        errors, warnings = inspect(doc)
        all_errors += errors
        all_warnings += warnings

    if all_warnings:
        print(f"🟡 포트폴리오 동기화 보고 {len(all_warnings)}건 (차단 아님):")
        for item in all_warnings:
            print(f"   - {item}")
        print()

    if all_errors:
        print(f"❌ 포트폴리오 규약 위반 {len(all_errors)}건:")
        for item in all_errors:
            print(f"   - {item}")
        return 1

    print(f"✅ 포트폴리오 문서 {len(docs)}건 — 규약 준수 · 없는 근거 0.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
